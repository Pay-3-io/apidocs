# Webhooks

Pay3 で発生したイベント（カード発行など）を、御社のエンドポイントへ **push 配信**します。ポーリング不要でリアルタイムに状態を同期できます。

## 設定

受信エンドポイントと署名鍵は、**コンソールの「開発者 → Webhook」**（または API `PUT /developer/webhook` /
`GET|POST /developer/webhook/secret`、[endpoints.md](endpoints.md)）で御社自身が登録・表示・再発行できます。
- 受信エンドポイント（HTTPS）と任意の説明（例: 本番の受信サーバー）
- 購読するイベント（下の「イベント種別」から選択。既定は全部。`ping` は購読設定に関係なく届きます）
- 署名検証用シークレット（登録時に発行。コンソールの鍵アイコン / `GET /developer/webhook/secret` で**いつでも表示**でき、再発行すると旧鍵は即時失効）
- 購読していないイベントは配信されず、配信ログにも載りません

## 配信フォーマット

`webhook_url` に対し `POST`（JSON）で配信されます。

ヘッダ:
- `X-Pay3-Event`: イベント種別（例 `card.issued`）
- `X-Pay3-Delivery`: 配信ID（再送時も同一）
- `X-Pay3-Signature`: 署名（後述）

ボディ:
```json
{
  "id": "<delivery-uuid>",
  "type": "card.issued",
  "created_at": "2026-09-15T01:50:00.000Z",
  "data": { "userId": "<uuid>", "cardId": "<uuid>", "cardType": "virtual", "issuedAt": "2026-09-15T01:50:00.000Z" }
}
```

`data` の項目は**イベントごとに定義された項目のみ**です（下表）。カード基盤・本人確認基盤の
生レスポンスを中継することはありません。

## 署名検証（必須）

`X-Pay3-Signature` は **受信した生ボディ**に対する HMAC-SHA256（hex）です。鍵は `webhook_secret`。

検証例（Node.js）:
```js
import crypto from "node:crypto";

function verify(rawBody, signature, secret) {
  const expected = crypto.createHmac("sha256", secret).update(rawBody).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signature));
}
```

検証に失敗したリクエストは破棄してください（なりすまし防止）。

## リトライ

- 2xx 応答（200 / 204 など）で配信成功とみなします。
- **5xx・10 秒のタイムアウト・接続不能**は一時的な失敗として、**指数バックオフ**で**最大 6 回まで自動再送**します。
  再送は Pay3 側のスケジューラが **5 分周期**で実行するため、実際の到着は下表の目安から最大 5 分遅れることがあります。
- **4xx（400 / 401 / 404 / 409 など）は再送しません**。同じ内容を送り直しても結果は変わらないため、その場で
  `failed` として確定します（408 / 425 / 429 だけは一時的とみなして再送します）。
  受信側で署名検証や送信元の確認に失敗している場合は、設定を直してから API で状態を照会してください。

  | 再送 | 直前の失敗からの待ち時間 |
  |---|---|
  | 1 回目 | 30 秒 |
  | 2 回目 | 60 秒 |
  | 3 回目 | 2 分 |
  | 4 回目 | 4 分 |
  | 5 回目 | 8 分 |
  | 6 回目（最終） | 16 分 |

  待ち時間は 30 秒 × 2^(再送回数 − 1) で、上限は 1 時間です。**6 回の再送とも失敗**した配信は
  そこで打ち切られ（`failed`）、以降は自動再送されません（初回配送を含めた配信試行は最大 7 回です）。
  **取りこぼした分の正本は API 側で**照会してください
  （`GET /pool/ledger`・`GET /pool/transfers`・`GET /users/list`）。
- 受信側は**冪等に**処理してください（ボディの `id` = `X-Pay3-Delivery` で重複排除）。再送は
  **同じ `id`・同じバイト列**で届きます。`created_at` は再送時刻ではなく**元の状態が変わった時刻**（初回送出時に固定）なので、
  再送で変わりません。

## 配信状態（status）の語彙

Pay3 側は配信ごとに以下の状態を記録しています。お問い合わせの際もこの語でご回答します。

| 状態 | 意味 |
|---|---|
| `pending` | 配信待ち（初回、または再試行の待機中） |
| `delivered` | 2xx を受け取った（配信成功） |
| `failed` | **実際に配信を試みて**失敗し、再送の上限（6 回）に達した |
| `skipped_no_endpoint` | `webhook_url` が未登録だったため、**一度も配信を試みていない** |

`skipped_no_endpoint` は配信の失敗ではありません。`webhook_url` の登録**前**に発生した
イベントがこれに当たります。**登録後にまとめて再送されることはありません**（下記の
イベント種別の注記を参照）。

## イベント種別

| イベント | 送出タイミング | `data` の項目 | 状況 |
|---|---|---|---|
| `user.registered` | 貴社経由の新規登録 | `userId, email, name, partnerRefCode, registeredAt` | 提供中 |
| `user.kyc.updated` | 本人確認のいずれかの段の結果が変わった | `userId, kycStatus, stage, stageStatus, updatedAt` | 提供中 |
| `card.issued` | バーチャルカード発行 | `userId, cardId, cardType, issuedAt` | 提供中 |
| `card.activated` | リアルカードのアクティブ化 | `userId, cardId, cardType, activatedAt` | 提供中 |
| `pool.deposit.credited` | プール入金の反映 | `referenceId, grossAmount, feeAmount, netAmount, available, currency, transactionHash, chain, sourceAddress, creditedAt` | 提供中 |
| `pool.transfer.completed` | チャージ反映完了 | `transferId, userId, amount, settledAt` | 提供中 |
| `pool.transfer.failed` | チャージ失敗・残高返還 | `transferId, userId, amount, reason, compensatedAt` | 提供中 |

- `user.registered` は**ブラウザの `?ref=` サインアップ経路でのみ発火します**。`POST /users/register`
  経由の登録は同期レスポンスで `userId` が返るため、本イベントは発火しません
- `user.registered` の `partnerRefCode` は、`GET /users/list` が同じユーザーに対して返す
  `referralCode` と**同じ値**です（登録時に確定した貴社の紹介コード）。名前が二形あるのは
  経路ごとの綴りの違いで、突き合わせは値でそのまま行えます
- `user.kyc.updated` は本人確認の **2 段**（一次本人確認 `identity` / カード発行体の審査 `card_issuer`）の
  どちらかの結果が変わるたびに送られます。`stage` がどの段か、`stageStatus` がその段の新しい状態
  （`approved` / `rejected` / `pending`）、`kycStatus` が**総合**（`approved` = チャージ指示・カード発行が
  通る状態。[users.md](users.md#kycstatus-と-kyc段ごとの状態) の判定表と同じ）です。
  一次が承認された時点では `stage=identity, stageStatus=approved` でも **`kycStatus` は `pending`** です。
  カードを発行できるようになったことを知りたい場合は **`kycStatus` が `approved` になったイベント**を待ってください
  ```json
  { "userId": "<uuid>", "kycStatus": "pending",  "stage": "identity",    "stageStatus": "approved", "updatedAt": "..." }
  { "userId": "<uuid>", "kycStatus": "approved", "stage": "card_issuer", "stageStatus": "approved", "updatedAt": "..." }
  ```
- `pool.deposit.credited` はユーザーに紐づかないので `data.userId` はありません。`referenceId` は `<chain>:<transactionHash>`
  （台帳 `GET /pool/ledger` の `deposit` 行の `referenceId` と同じ値）。`available` は反映直後のプール残高です
- `card.activated` はリアルカードのみ（`cardType` は `physical` 固定）。バーチャルカードは
  発行 = 即利用可能のため `card.issued` のみが送られます
- **サンドボックスでの `card.activated` の扱い**: リアルカード用 BIN がサンドボックスで未解放の
  ため、`card.activated` はサンドボックスでは**実発火を確認できません**（発火点は物理カードの
  アクティブ化成功時のみで、再アクティブ化では送出しません）。ペイロード形状と発火条件は単体
  テストで固定してありますが、**実配信の確認は本番の BIN 解放後**に行います
- 配信されるのは **`webhook_url` を登録した以降に発生したイベント**のみです。登録前に発生した
  分は `skipped_no_endpoint` として記録され、**登録後も再送されません**（過去分は
  `GET /pool/ledger`・`GET /users/list` 等の API で照会できます）

## 再配信・テスト

- テスト配信: コンソール「開発者 → Webhook」の「テスト送信」、または `POST /developer/webhook/test` で
  `ping` イベントを 1 通配信します。到達は同じ画面の配信ログ（`GET /developer/webhook/deliveries`）で確認できます。
- 失敗した配信は Pay3 側が **5 分周期で自動再送**します（上記のリトライ回数まで）。手動での再配信が必要な場合は
  配信ログの `id` を添えて Pay3 にご連絡ください。
