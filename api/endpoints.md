# Endpoints

データプレーンの全エンドポイント。すべて `Authorization: Bearer <accessToken>` が必要です。
レスポンスは概ね `{ message, data, code }`（`code: 0` が成功）の形です。エラーは `{ message, code }` と適切な HTTP ステータス。

Base URL (sandbox): `https://api-staging.pay-3.io/functions/v1/external-service`

## Users

### POST /users/register
ユーザーを作成し、御社クライアントに紐づける。
- body: `{ signup_type, signup_type_id, first_name, last_name?, email?, phone_number?, telegram_id? }`
  - **`signup_type`（必須）**: `"EMAIL"` | `"PHONE"` | `"TELEGRAM"`
  - **`signup_type_id`（必須）**: signup_type に対応する識別子（EMAIL ならメールアドレス、PHONE なら電話番号、TELEGRAM なら telegram id）
- 200: `{ data: { userId, first_name, last_name, card_issued }, code: 0 }`
- 例: `{ "signup_type": "EMAIL", "signup_type_id": "taro@example.com", "email": "taro@example.com", "first_name": "Taro" }`
- **冪等**（`Idempotency-Key` は不要）: 同じ `(signup_type, signup_type_id)` を再送すると
  **同じ `userId`** を 200 で返し、人は増えません。`EMAIL` / `PHONE` / `TELEGRAM` のどれでも同じです。
  `?ref=` 付きリンク経由で登録済みの方も同じ集合として引き当てます（[users.md](users.md)）
  同一判定は `signup_type_id` の**バイト完全一致**です（Pay3 側で正規化しません。
  EMAIL は小文字・PHONE は E.164 に固定して送ってください）
- 400: リクエストの内容の誤り。**入力の誤りが `500` になることはありません**
  - **ボディが JSON として読めない**（末尾カンマ・閉じ括弧漏れ・空ボディなど。
    `{ message: "Invalid JSON body", code: 400 }`）
  - `signup_type` が `EMAIL` / `PHONE` / `TELEGRAM` 以外（`{ message: "Unsupported signup_type", code: 400 }`）
  - `signup_type_id` の欠落・空文字（`{ message: "User data missing", code: 400 }`）
  - `referral_code` の形式不正、または御社が発行したコードでない
    （`{ message: "referral_code is unknown or disabled", code: 400 }`）
- 409: その `signup_type_id` が**御社の外**で既に使われている
  （`{ message: "This signup_type_id is already registered outside your account", code: 409 }`）。
  本文は `message` と `code` だけで、`userId` も氏名も返しません。**再送しても変わりません**

### GET /users?id=<userId>
ユーザー情報を取得（テナント分離。自社ユーザーのみ）。
- 200: `{ data: { id, first_name, last_name, email, phone_number, telegram_id, client_id, created_at, updated_at, signup_type_id, signup_type, card_issued, kyc_verified }, code: 0 }`
  — 返るのは**この 13 項目ちょうど**です（Pay3 内部の識別子は含みません）

## KYC

### POST /kyc/access-token
Sumsub のアクセストークンを発行。御社UIで本人確認フローを起動するために使う。
- body: `{ userId }`
- 200: `{ data: { accessToken, userId }, code: 0 }`

### POST /kyc/submit
本人確認完了後に呼び、口座/カード基盤のセットアップを起動する。**冪等**（[Idempotency-Key](idempotency.md) 推奨）。
- headers: `Idempotency-Key: <unique>`
- body: `{ userId, applicantId }`
- 200: `{ data: { applicantId }, code: 0 }`

## Card

### POST /card/application/start
カード申込を開始。
- body: `{ userId }`

### POST /card/application
カード申込の状態を取得。
- body: `{ userId }`

### POST /card/quote
発行前の見積もり。**金銭は動かない**（純粋な参照）。
- body: `{ userId, type?, bin?, country? }`
  - `type`（任意, 既定 `"physical"`）: `"virtual"` | `"physical"`。**virtual を見積もるときは必ず指定する**
  - `bin`（任意）: 下記「カード BIN の値域」。省略時はその種別を出せる先頭 BIN
  - `country`（任意）: 送り先。`physical` のとき標準配送を超える分の目安を返す
- 200: `{ data: { bin, form_factor, country, currency, price, estimated_shipping, total }, code: 0 }`
  - `total` が発行時に実際に請求される確定価格
  - **`price` / `total` / `estimated_shipping` は小数 2 桁固定の文字列**（`"5.00"`。他の金額フィールドと同じ表記）
  - `estimated_shipping` は該当しないとき（virtual、または `country` 未指定）`null`。**`null` は「無料」ではなく「対象外」**
  - 実例: `{ "bin": "45492418", "form_factor": "virtual", "country": null, "currency": "USD", "price": "5.00", "estimated_shipping": null, "total": "5.00" }`
- 400: 未対応の `bin` / `type` の組み合わせ（`{ message: "Unsupported card bin/form factor: <bin>/<form factor>", code: 400 }`）

### POST /card/issue_card
カードを発行。**冪等**（[Idempotency-Key](idempotency.md) 必須推奨）。KYC 完了が前提。
- headers: `Idempotency-Key: <unique>`
- body: `{ userId, type, amount?, bin? }`
  - `type`: `"virtual"` | `"physical"`
  - `amount`（任意, 既定 0）: 発行と同時にユーザー残高へ載せる入金額。**発行価格そのものではない**（価格は Pay3 側で一元管理）。
  - `bin`（任意）: 発行する BIN。**省略時はその種別を出せる先頭 BIN**（サンドボックスの virtual では `537100`）。
- 200: `{ data: { id, cardType, status, last4 }, code: 0 }`
  - `id`: カード ID。`card.issued` Webhook の `cardId` と同じ値
  - `cardType`: `"virtual"` | `"physical"` / `status`: `"active"` | `"issued"` | `"shipped"` | `"activated"` | `"frozen"`
  - `last4`: カード番号の下 4 桁。**PAN・CVV・有効期限・請求先住所・メールアドレスは返しません**
  - **返す項目はこの 4 つだけです**（カード基盤の生レスポンスは中継しません）。項目の追加ご要望はお知らせください
- 400: カタログに無い / 無効 / その種別を許可していない `bin`。**ユーザー残高が発行価格に満たない場合もこの 400**（下の「残高が足りないときは 400 と 402 の 2 系統があります」）
- 402: **発行の途中で徴収が尽きた**（作成済みカードは Pay3 が閉じます。同上）
- 403: **2 系統あります。`message` で識別してください**（どちらも `code: 403`）
  | message | 意味 | 対処 |
  |---|---|---|
  | `This card is not available for your account` | その口座に許可されていない `bin` | 許可された `bin`（上表）を指定する |
  | `Card limit reached for your account` / `Card limit reached for this card type` | **発行枚数の上限**に達している | 既存カードを確認する。枚数を増やす必要があれば Pay3 へご連絡ください |

  > **枚数上限について**: 既定は 1 ユーザーあたり virtual 1 枚・physical 1 枚ですが、これは
  > **Pay3 側の安全弁としての既定値であり、設定により変わりえます**（貴社ごとの変更も可能です）。
  > 貴社実装では**枚数をハードコードせず**、403 の `message` で分岐してください。
  > `bin` を差し替えても枚数上限は解消しません（原因が別のため）。
- 409: **カードが作られないまま発行処理が終わった**
  （`{ message: "Card issuance did not complete: no card was created. ...", code: 409 }`）。
  ほとんどの場合、**口座/カード基盤のセットアップがまだ終わっていない**のが原因です
  （`kyc/submit` はセットアップを**起動**する非同期処理なので、完了を待たずに発行を叩くとこの窓に入ります）。
  **カードは 1 枚も作られておらず、`card.issued` Webhook も送られません。**
  `GET /users/{userId}` の `kycStatus` / `cards` か `user.kyc.updated` Webhook でセットアップ完了を確認し、
  **新しい `Idempotency-Key` で再実行**してください。繰り返し 409 になる場合は Pay3 へご連絡ください

#### 残高が足りないときは 400 と 402 の 2 系統があります

**どちらもカードは残りません**が、**止まった場所が違います**。`status`（＋ `code`）で分岐してください。

| status | 意味 | 何が起きたか | レスポンス本文 |
|---|---|---|---|
| **400** | **残高が発行価格に満たない（事前拒否）** | 発行を**始める前**に Pay3 が断りました。**カードは作られていません** | `{ "message": "Not enough balance to issue card", "code": 400 }` |
| **402** | **発行の途中で徴収が尽きた** | カードは一度作られましたが価格を引けず、**Pay3 がそのカードを閉じました（void 済み）**。`card_issued` も false のままです | `{ "message": "Not enough balance to issue card. The issuance was rolled back and no card was created.", "code": 402 }` |

- 対処はどちらも同じです: **チャージしてから、新しい `Idempotency-Key` で再実行**してください
  （同じキーで再送すると初回のレスポンスがそのまま再生されます → [idempotency.md](idempotency.md)）
- **貴社実装では必要額をハードコードせず、`status` / `code` で分岐してください** — 発行時に
  実際に控除される金額は Pay3 側の設定で変わりえます（サンドボックスと本番でも異なります）。
  `if (status === 402)` だけを見ると、最も素直な「残高が足りない」ケース（**400**）を取りこぼします

### カード BIN の値域

`bin` の値域は Pay3 側のカード BIN カタログで決まり、**カタログに無い値は発行・見積もりとも拒否される**（フェイルクローズ）。
サンドボックス（dev）で有効な値:

| BIN | ブランド / 名称 | 発行できる種別 |
|---|---|---|
| `537100` | Mastercard / Virtual Card | virtual（`bin` 省略時の既定） |
| `45492418` | Visa / Pay3 Card | virtual |
| `49387519` | Visa / White Card | physical |

BIN ごとに出せる種別が違うため、**`bin` と `type` の組み合わせ**がカタログで許可されていない場合は 400（500 ではない）。
本番の値域は引き渡し時に別途案内する。

### POST /card/issuance_events
発行進捗イベントを取得（ローディングUI / 状態同期用）。
- body: `{ userId, applicationId?, since? }`（`since` は ISO timestamp）
- 200: `{ data: { events: [{ phase, meta, created_at, application_id }] }, code: 0 }`
- `phase`: `validating → provider_call → db_committed → card_fetched → funds_settled → shipping_requested → done`（失敗時 `failed`）

### POST /card/fetch_cards
ユーザーのカード一覧。
- body: `{ userId }`
- 200: `{ data: [{ id, cardType, status, last4, currency, balance }], code: 0 }`
  - `balance` は**小数 2 桁固定の文字列**（`"2.60"`。他の金額フィールドと同じ表記）。
    取得できなかった場合は `null`（`"0.00"` には丸めません — 残高 0 と区別するため）
  - `currency` は ISO 通貨コード（例 `"USD"`）。`last4` はカード番号の下 4 桁
  - **返す項目はこの 6 つだけです**。カード基盤の内部識別子（口座 ID・budget ID・cardholder ID 等）、
    請求先住所、メールアドレス、価格表・機能フラグは含みません
  - ⚠️ **スコープはカード基盤側の口座で決まります。** sandbox ではテスト用口座を複数のテストユーザーで
    共有しているため、**他のテストユーザーのカードが混ざって返ることがあります**
    （2026-09-16 実測: 同じ口座を共有する 2 ユーザーで叩くと、どちらも同一の 2 枚を返した）。
    **本番では各ユーザーが自分の口座を持つので発生しません。**
    本人のカードだけを見たい場合は `GET /users/{userId}` の `cards` を使ってください
    （こちらは本人スコープです）

### POST /card/fetch_card_details
- body: `{ userId, cardId }`
- ⚠️ **この面は 2 要素の追加認証（step-up）が必須**で、パートナー OAuth で発行した
  トークンはそれを持たないため **`401`** が返ります
- **カード番号・CVV・有効期限はパートナー境界を越えません。** 200 の `data` は空です。
  カードの種別・状態・下 4 桁は `POST /card/fetch_cards` か `GET /users/{userId}` を使ってください

### POST /card/fetch_deposit_address
暗号資産の入金アドレスを取得。
- body: `{ userId, token, network }`

### POST /card/set_card_pin
ATM PIN を設定。
- body: `{ userId, cardId, pin }`

### POST /card/lock_card  /  unlock_card
カードのロック/解除。
- body: `{ userId, cardId }`

### POST /card/fetch_transactions
取引履歴。
- body: `{ userId, page, limit }`

## Partner Pool

プール入金を原資にユーザー残高へチャージする経路（残高照会・チャージ指示・台帳）。
→ **[pool.md](pool.md)**

- `GET /pool/balance` / `GET /pool/deposit_address`
- `POST /pool/transfer`（`Idempotency-Key` 必須）
- `GET /pool/transfer/{transferId}` / `GET /pool/transfers`（`status` / `userId` / `from` / `to` / `limit` / `offset`）
- `GET /pool/ledger`（`type` / `from` / `to` / `limit` / `offset`）

一覧系 GET（`/pool/transfers`・`/pool/ledger`・`/users/list`・`GET /referral-codes`）は
**受け付ける引数名が決まっており、それ以外は 400** です（綴り違いを「絞り込めていない全件
200」で返さないため）。一覧 → [pool.md の「クエリ引数の検証」](pool.md#クエリ引数の検証)。

`from` / `to` は `createdAt` 基準です。**日付のみの指定は UTC 基準で、`to` はその日を
丸ごと含みます** — 1 日ぶんは `?from=2026-09-15&to=2026-09-15` で取れます
（→ [pool.md の「日付の指定」](pool.md#日付の指定from--to-の境界)）。

## Referral Codes

紹介コードの登録・有効化切替・削除と、ユーザーへの紐付け。
→ **[referral-codes.md](referral-codes.md)**

- `GET /referral-codes` / `POST /referral-codes`
- `PATCH /referral-codes/{code}` / `DELETE /referral-codes/{code}`

`POST /users/register` は `referral_code` を受け付けます。

## User Status

自社ユーザーの一覧と、KYC 完了状況・カード発行ステータス（仕様書 §8・§10-3）。
→ **[users.md](users.md)**

- `GET /users/list`（スコープ `users:status`。引数は `limit` 1〜200 / `offset` のみ）
- `GET /users/{userId}`（スコープ `users:status`。帰属外・不存在はいずれも 404）

一覧・照会・`POST /pool/transfer` の対象になるユーザーの集合は**同一**です。

`GET /users/list` が返す `referralCode` と、Webhook `user.registered` の `partnerRefCode` は
**同じ値**（そのユーザーの登録時に確定した貴社の紹介コード）です。名前が二形あるのは経路ごとの
綴りの違いで、突き合わせは値でそのまま行えます。

## 資格情報・Webhook・送信元 IP の管理

API キーの発行・取り消し、Webhook 宛先と署名鍵、送信元 IP のホワイトリストは、**パートナーコンソールの
「開発者」メニュー**で操作します。

秘密値（API キー・署名鍵）が平文で表示されるのは「発行した瞬間の 1 回」だけです。控えを失った場合はコンソールで再発行してください。

## 未知のパス

認識できないパス・未対応の HTTP メソッドは **JSON の 404** を返します。
この約束が掛かる範囲は **`/pool/*`・`/referral-codes*`・`/users/*`・`/oauth/*`** です。

> **仕様書 §3 との差分（正直に書きます）**: 仕様書 §3 は「認識できないパス・未対応メソッドは
> JSON の 404」を**全面的に**約束していますが、**この形で 404 が確実に返るのは上記 4 サブツリー**です。
> `/kyc/*`・`/card/*` は**ボディの `userId` を分岐より先に解決する**構造のため、未知サブパス・
> 未対応メソッドに対して返るものが送ったボディで変わります（2026-09-16 実測）:
>
> | 送ったボディ | `/card/<未知>`・`/kyc/<未知>` の応答 |
> |---|---|
> | 正しい JSON ＋ 御社に帰属する `userId` | `404 {"message":"Unknown endpoint. …","code":404}`（仕様書どおり） |
> | 正しい JSON ＋ 不明な `userId` | `404 {"message":"User not found","code":-1}`（`code` が HTTP ステータスと一致しません） |
> | 正しい JSON ＋ `userId` なし | `400 {"message":"User ID is required","code":400}` |
> | **JSON として読めない・ボディなし** | `400 {"message":"Invalid JSON body","code":400}` |
>
> つまりこの 2 サブツリーでは「パスの綴り違い」が**パスの誤りとして返ってこないことがあります**。
> **パスの綴りは docs の逐語どおりに**お使いください。分岐をボディの読み取りより前へ出す
> 修正は引き渡し後に入れます。
>
> **一方、ボディが JSON として読めないときの出口は全サブツリーで揃っています。**
> `/kyc/*`・`/card/*` でも、壊れた JSON・空ボディ・JSON オブジェクトでない本文
> （`null` / 文字列 / 数値 / 配列）は **`400 {"message":"Invalid JSON body","code":400}`** です。
> **`text/plain` の `500` は返りません** — 「入力の誤りが `500` になることはありません」
> （[authentication.md](authentication.md)）はこの 2 サブツリーでも守られています。

→ [pool.md の「未知のパス・エラー本文の形式」](pool.md#未知のパスエラー本文の形式)

---
正規の機械可読仕様は [openapi.yaml](../openapi.yaml) を参照。
環境ごとの接続先は [environments.md](environments.md)、コピペで通る最短手順は [quickstart.md](quickstart.md)。
