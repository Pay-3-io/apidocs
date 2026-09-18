# Partner Pool（プール台帳・チャージ指示）

御社が事前に USDT で入金した残高（プール）を原資に、御社の指示で Pay3 ユーザーの
カード残高へチャージする経路です。

すべて `Authorization: Bearer <accessToken>` が必要です。
Base URL (sandbox): `https://api-staging.pay-3.io/functions/v1/external-service`

> **ベース URL は末尾の `/external-service` まで含みます**（仕様書 §2 と同じ定義です）。
> API のパスはすべてそのベース URL の直下に置いてください（例: `GET {BASE_URL}/pool/balance`）。
> `/external-service` を落とした `…/functions/v1/pool/balance` は
> 「pool という関数が無い」という 404 になり、二重に付けた
> `…/external-service/external-service/pool/balance` も通りません。
> **展開後の URL に `/external-service` がちょうど 1 回**現れるのが正しい形です。

## 必要なスコープ

| スコープ | 範囲 |
|---|---|
| `pool:read` | 残高・台帳・指示の照会 |
| `pool:transfer` | チャージ指示の作成（`pool:read` を含む） |

スコープ不足は `403 Insufficient scope: <scope> required` を返します。

## 送信元 IP（ホワイトリスト）

API キーで取得したトークンでの呼び出しは、**コンソール「開発者 → 送信元 IP」（または `PUT /developer/ip-allowlist`）に
登録した IP からのみ**受け付けます。sandbox / 本番とも同じです。

- 1 件も登録していない間は、どのエンドポイントも `403 ip_not_registered` です（コンソールの操作は対象外なので、
  登録・修正はいつでもコンソールから行えます）。
- 登録外の IP からの呼び出しは `403 ip_not_allowed` です。
- 送信元は Cloudflare が付与する `cf-connecting-ip` で判定します。
  `x-forwarded-for` / `x-real-ip` は**リクエスト側が自由に付けられるため参照しません**。
- IPv4 / IPv6 / CIDR、最大 20 件。

---

## 資金の流れ

```
御社 → USDT をプール入金アドレスへ送金
     → Pay3 が着金を確認し、0.5% を控除して USD でプール残高に反映
     → 御社が POST /pool/transfer で「このユーザーに $X」と指示
     → プール残高から差引き、ユーザーのカード残高へ反映
```

- 入金時の控除率は `GET /pool/deposit_address` の `feeRate` で確認できます（既定 0.5%）。
- **金額の上限・下限チェックは御社側の責務**です。Pay3 は指示された金額をそのまま USD でチャージします。
- ADUSD / ROY の区別は行いません。同一の枠組みで扱います。

---

## GET /pool/balance

> **`?currency=USD` を付けられます（任意）。** 現在プールは 1 社 1 通貨なので、付けても
> 付けなくても返る値は同じです。将来プールが複数通貨になったときに御社のコードを
> 変えずに済むよう、**今のうちに付けておくことをお勧めします**。
> 3 文字の通貨コード以外は `400`、プールの通貨と違う指定は `404`（未開設と同じ応答）です。


プール残高。補充判断に使ってください。

- 200:
  ```json
  {
    "balance": "9950.00",
    "pendingTransfers": "300.00",
    "available": "9650.00",
    "currency": "USD"
  }
  ```
- `available` … いますぐチャージ指示に使える額
- `pendingTransfers` … 受理済みで反映確定待ちの拘束分
- `balance` … 上記の合計
- 404: プール口座が未開設
- 400: クエリ引数を付けた場合（このエンドポイントは**引数を取りません**。常に現在の残高を返します）
  ```bash
  $ curl -s "$BASE_URL/pool/balance?to=2026-09-15" -H "Authorization: Bearer $TOKEN"
  {"message":"Unknown query parameter \"to\". Accepted: (none)","code":400}
  ```
  過去の時点の残高は `GET /pool/ledger` の `balanceAfter`（走行残高）で辿ってください。

## GET /pool/deposit_address

プール入金用のアドレス。**何を送るかは `currency`、どのチェーンかは `network`** で返します
（どちらも口座ごとの設定です。本番は USDT / TRON、サンドボックスは USDC / Ethereum Sepolia）。

- 200: `{ "address": "T...", "network": "TRON", "currency": "USDT", "feeRate": "0.0050" }`
- **`currency` と `network` の組をそのまま使ってください。** 表示された通貨以外を送ると着金しません
  （別のトークンを同じアドレスへ送った場合、Pay3 からは検知も返金もできません）。
- 409: アドレス未発行（この場合は送金しないでください）
- 400: クエリ引数を付けた場合（このエンドポイントは**引数を取りません**。常に登録済みの 1 本を返します）
  ```bash
  $ curl -s "$BASE_URL/pool/deposit_address?to=2026-09-15" -H "Authorization: Bearer $TOKEN"
  {"message":"Unknown query parameter \"to\". Accepted: (none)","code":400}
  ```
  `?network=TRON` のように絞り込んだつもりの引数を付けても、返るのは常に登録済みのアドレスです。
  黙って捨てると「TRON のアドレスを確認した」と読めてしまうため、`400` で明示的に返します。

> **サンドボックス（dev）の注意**: サンドボックスの入金レールは **USDC / Ethereum Sepolia**（テストネット）です。
> 返る `currency` は `USDC`、`network` は `ETH_SEPOLIA`（メインネットの `ETH` と取り違えないよう明示しています）。
> テストネット USDC は Circle の faucet などで入手できます。**本番のレール（USDT / TRON）とは別物**なので、
> サンドボックスで確認できるのは配管（アドレス取得 → 着金 → 台帳反映 → Webhook）であり、
> 本番レール固有の挙動は本番前に別途確認します。
>
> `network` が `SANDBOX`・`address` が `0xSANDBOX_` で始まる場合は、**まだ実アドレスが発行されていない**
> プレースホルダです（**送金しないでください**）。

## POST /pool/transfer

チャージ指示。**`Idempotency-Key` ヘッダは必須**です。

- headers: `Idempotency-Key: <unique>`
- body: `{ "userId": "<uuid>", "amount": "300.00" }`
  - `amount` は小数 2 桁までの文字列。`"300.00"` のように送ってください。
- 202: `{ "transferId": "pt_...", "status": "pending" }`

反映完了は同期では返りません。`pool.transfer.completed` / `pool.transfer.failed`
Webhook（[webhooks.md](webhooks.md)）、または `GET /pool/transfer/{transferId}` で確認します。

### 対象にできるユーザー

チャージを打てるのは**御社に属するユーザー**だけです。属するとは、次のどちらかを満たすことです:

1. **紹介コード経由で登録したユーザー** — 御社の紹介コード付き登録リンク
   （[referral-codes.md](referral-codes.md)）からサインアップしたユーザー。帰属は
   **登録時点で確定し、以後変わりません**（コードを無効化・削除しても過去の帰属は維持されます）。
2. **`POST /users/register` で御社が作成したユーザー**。

この集合は `GET /users/{userId}`（[users.md](users.md)）で照会できる集合と**同一**です
（照会できるユーザーにはチャージでき、チャージできるユーザーは照会できます）。
これ以外の userId — 他社のユーザー・どこにも属さないユーザー・存在しない userId — は
**区別せずすべて 404** です（他社ユーザーの実在を推測できないようにするため）。

### エラー

| ステータス | 意味 |
|---|---|
| 400 | `Idempotency-Key` 未指定 / `userId` 欠落 / `amount` の形式不正 |
| 402 | プール残高不足 |
| 404 | ユーザーが見つからない（他社のユーザーは存在しても 404） |
| 409 | 同一キーで**異なるボディ**が送られた / 同一キーの処理が進行中 |
| 412 | ユーザーの KYC が未承認 |
| 429 | レート制限超過 |
| 503 | この環境ではチャージ指示が未設定（下記「決済モード」参照） |

受理拒否（402 / 404 / 412 / 409 `pool_not_found`）も理由付きで記録され、
`GET /pool/transfers` とコンソールから確認できます。拒否が無言で消えることはありません。

**拒否のレスポンスにも `transferId` が入ります。** 記録された拒否行の ID なので、
そのまま `GET /pool/transfer/{transferId}` で理由まで引けます（時刻で突き合わせる必要は
ありません）。御社側の指示 ID と Pay3 の `transferId` を 1:1 で記録できます。

```json
// 412（KYC 未承認）
{ "message": "User KYC is not approved", "code": 412, "transferId": "pt_9f0c..." }
// 402（残高不足）
{ "message": "Insufficient pool balance", "code": 402, "transferId": "pt_1a7d..." }
```

```bash
curl -s "$BASE_URL/pool/transfer/pt_9f0c..." -H "Authorization: Bearer $TOKEN"
# => 200 { "transferId": "pt_9f0c...", "status": "rejected", "reason": "kyc_not_approved", ... }
```

> 記録そのものに失敗した稀なケースでは `transferId` を**載せません**（引けない ID を
> 返さないため）。その場合もサーバ側にはエラーログが残ります。

### 冪等性

同じ `Idempotency-Key` で再送しても**指示は 1 件しか作られません**。
同一キーで金額やユーザーを変えて送った場合は `409` で拒否します
（`$300` の結果を `$3000` のリクエストに返さないため）。詳細は [idempotency.md](idempotency.md)。

## GET /pool/transfer/{transferId}

指示 1 件の状態照会。

- 200:
  ```json
  {
    "transferId": "pt_...",
    "userId": "<uuid>",
    "amount": "300.00",
    "currency": "USD",
    "status": "settled",
    "reason": null,
    "settlementMode": "simulate",
    "createdAt": "...",
    "settledAt": "...",
    "failedAt": null
  }
  ```
- `status` … `pending` | `settled` | `failed` | `rejected`
- `settlementMode` … サンドボックスでは `simulate` です（下記「決済モード（sandbox と本番の違い）」を参照）。
  本番モードの値は本番環境のご案内時に別途お知らせします。
- 404: 見つからない（他社の指示は存在しても 404）

## GET /pool/transfers

指示の一覧。

- query: `status`, `userId`, `from`, `to`（ISO 8601）, `limit`（1..200, 既定 50）, `offset`（0 以上, 既定 0）
- 200: `{ "data": [ ...GET /pool/transfer と同じ形... ], "paging": { limit, offset, total } }`
- 400: `status` / `userId` / `limit` / `offset` / `from` / `to` が不正、または**受け付けない引数名**（下記「クエリ引数の検証」）

`userId` は **uuid**（`GET /users/list` の `userId` と同じ値）だけを受け付けます。
`status` は `pending` / `settled` / `failed` / `rejected` のいずれかです。
**いずれも形式・語彙が違えば `400`** で、`0` 件の `200` にはなりません
（絞り込めていない一覧・該当なしの一覧と、御社側のタイポを区別できるようにするためです）。

```bash
# uuid でない userId
$ curl -s "$BASE_URL/pool/transfers?userId=abc" -H "Authorization: Bearer $TOKEN"
{"message":"userId must be a uuid (e.g. \"3f8c1e2a-5b47-4d9e-8a10-2c6b7d0e4f51\")","code":400}

# 語彙外の status
$ curl -s "$BASE_URL/pool/transfers?status=abc" -H "Authorization: Bearer $TOKEN"
{"message":"status must be one of: pending, settled, failed, rejected","code":400}
```

形式が正しく、その uuid のユーザーが御社に属していない（または存在しない）場合は
`200` で `"total": 0` を返します — **「形式が違う」と「該当が無い」は別の応答**です。

#### 却下された指示の `userId`

`userId` に御社が知らないユーザーを指定した指示は `unknown_user` で却下されますが、
**却下の記録自体は残り**、一覧・`GET /pool/transfer/{transferId}` のどちらにも
**御社が指定した `userId` がそのまま** 入って返ります（Pay3 側のユーザーには紐付いていません）。

`?userId=` はこの**却下行も一緒に**絞り込みます。つまり **一覧・詳細・コンソールが
`userId` として表示している値をそのまま `?userId=` に渡せば、その指示が引けます** —
誤った `userId` でチャージ指示を出したときの調査は、その値 1 つで完結します。

```bash
# 却下された指示も、表示されている userId で引けます
curl -s "$BASE_URL/pool/transfers?userId=$USER_ID&status=rejected" \
  -H "Authorization: Bearer $TOKEN"
```

`from` / `to` は **`createdAt`（指示を受理した時刻）**で絞り込みます。`settledAt` ではありません
— 台帳（`GET /pool/ledger` の `transfer` 行）も受理時に記録されるため、同じ `from` / `to` を
両方に渡せば同じ区間が突き合わせられます。

**日付のみ（`2026-09-15`）で指定した `to` は、その日を丸ごと含みます**。
したがって **1 日ぶんは `?from=X&to=X`** で取れます（下記「日付の指定」参照）。

```bash
curl -s "$BASE_URL/pool/transfers?from=2026-09-14&to=2026-09-16&limit=50" \
  -H "Authorization: Bearer $TOKEN"

# 1 日ぶん（2026-09-15 の 00:00:00Z 〜 23:59:59.999999Z）
curl -s "$BASE_URL/pool/transfers?from=2026-09-15&to=2026-09-15&limit=50" \
  -H "Authorization: Bearer $TOKEN"
```

## GET /pool/ledger

プール残高の増減履歴。

- query: `type`, `from`, `to`（ISO 8601）, `limit`（1..200, 既定 50）, `offset`（0 以上, 既定 0）
- 400: `type` / `limit` / `offset` / `from` / `to` が不正、または**受け付けない引数名**（下記「クエリ引数の検証」）
- 200:
  ```json
  {
    "data": [
      { "id": "...", "type": "fee", "amount": "-50.00", "balanceAfter": "9950.00",
        "referenceId": "tx-...", "metadata": { "rate": "0.0050" }, "createdAt": "..." },
      { "id": "...", "type": "deposit", "amount": "10000.00", "balanceAfter": "10000.00",
        "referenceId": "tx-...", "metadata": null, "createdAt": "..." }
    ],
    "paging": { "limit": 50, "offset": 0, "total": 5 }
  }
  ```

- 並び順は `createdAt` の**降順**（新しい行が先頭）。上の例は残高 0 のプールへ
  10,000.00 USDT が着金したときの 2 行で、**新しい `fee` 行が先・`deposit` 行が後**に並びます。

**`balanceAfter` は走行残高です** — その行を適用した**直後**のプール残高を返します。
入金は「総額を入れてから手数料を引く」2 行に分かれるため、`deposit` 行は控除前
（`10000.00`）、`fee` 行が控除後（`9950.00`）になります。古い行から順に `amount` を
足していくと、各行の `balanceAfter` と一致します。

**プール残高が動く操作は、例外なく台帳に 1 行を残します**（逆に、残高が動かない操作は
行を作りません）。チャージ指示について具体的には:

| 起きたこと | 台帳 |
|---|---|
| 指示を受理（202） | `transfer` 行（−）が**その時点で**記録されます。残高はここで減ります |
| 指示が `settled` になった | 新しい行は増えません（残高は受理時に減算済み）。`transfer` 行の `metadata` に `settlement_mode` が付きます |
| 指示が `failed` になった | `refund` 行（＋）が加わり、受理時の `transfer` 行と**同額で相殺**されます |
| 受理拒否（402 / 404 / 412） | 行は作られません（残高が動いていないため）。拒否の記録は `GET /pool/transfers` 側にあります |

つまり `pending` の指示も台帳に現れます。「残高は減っているのに台帳に無い」区間は
ありません。行の `referenceId` が `transferId` なので、`GET /pool/transfer/{transferId}`
と突き合わせれば各行の確定状態が分かります。

`metadata` は行ごとの補足（自由形式）です。`fee` 行には控除に使った料率が
`{"rate": "0.0050"}` の形で入ります。**料率は `GET /pool/deposit_address` の `feeRate` と
同じく小数 4 桁固定の文字列**で、数値型では返しません。

`type` の意味:

| type | 符号 | 内容 |
|---|---|---|
| `deposit` | + | USDT 入金の反映（控除前の総額） |
| `fee` | − | 入金時の控除（既定 0.5%） |
| `transfer` | − | ユーザーへのチャージ差引（**受理時**に記録。確定後は `metadata.settlement_mode` が付きます） |
| `refund` | + | チャージ失敗時の返還（同じ `referenceId` の `transfer` 行と相殺） |
| `withdrawal` | − | プール残高を USD → USDT へ戻した出金 |
| `adjustment` | ± | 運用上の調整 |

`?type=` に渡せるのは**この表の 6 つだけ**です。それ以外は `400` で、`0` 件の `200` には
なりません（`GET /pool/transfers` の `status` と同じ規則です）。

```bash
# 表に無い type
$ curl -s "$BASE_URL/pool/ledger?type=charge" -H "Authorization: Bearer $TOKEN"
{"message":"type must be one of: deposit, fee, transfer, refund, withdrawal, adjustment","code":400}

# 大文字・カンマ区切りも受け付けません（1 回に 1 つだけ指定できます）
$ curl -s "$BASE_URL/pool/ledger?type=DEPOSIT" -H "Authorization: Bearer $TOKEN"
{"message":"type must be one of: deposit, fee, transfer, refund, withdrawal, adjustment","code":400}
$ curl -s "$BASE_URL/pool/ledger?type=deposit,fee" -H "Authorization: Bearer $TOKEN"
{"message":"type must be one of: deposit, fee, transfer, refund, withdrawal, adjustment","code":400}
```

> **コンソールの表記と `type` の値は違います。** 画面の台帳はユーザーへのチャージ差引を
> 「チャージ」と表示しますが、API の `type` は **`transfer`** です。`?type=charge` は
> 上記のとおり `400` になります（黙って 0 件を返して「その期間にチャージが無かった」と
> 読ませないためです）。

`?type=`（空）は「指定なし」= 全件です。

---

## クエリ引数の検証

一覧系（`GET /pool/transfers` / `GET /pool/ledger` / `GET /users/list` /
`GET /referral-codes`）と `GET /pool/balance` のクエリ引数は**受け付けられない値も、
受け付けない引数名も、黙って丸めたり無視したりしません**。範囲外・形式違い・未知の引数名はすべて
`400` のエラー JSON（`{ "message": ..., "code": 400 }`）で返します。

| 引数 | 受け付ける値 | 既定 |
|---|---|---|
| `limit` | 1〜200 の**十進整数**（`1e2` / `1.5` / `abc` / `-1` / `0` / `201` は 400） | 50 |
| `offset` | 0 以上の**十進整数**（負値・非整数は 400）。**総件数を超える `offset` は `200` の空ページ**（`"data": []`・`"total"` は絞り込み後の総件数） | 0 |
| `from` / `to` | **ISO 8601** の日付 `2026-09-14` またはオフセット付き日時 `2026-09-14T00:00:00Z` / `2026-09-14T09:00:00+09:00`。実在しない日付（`2026-02-30` / `2026-13-45`）は 400。**秒の小数部は 6 桁（μs）まで**（7 桁以上は 400） | フィルタ無し |
| `type`（`/pool/ledger`） | `deposit` / `fee` / `transfer` / `refund` / `withdrawal` / `adjustment` の**いずれか 1 つ**（大文字・カンマ区切り・表に無い値は 400） | フィルタ無し |
| `status`（`/pool/transfers`） | `pending` / `settled` / `failed` / `rejected` の**いずれか 1 つ**（同上） | フィルタ無し |
| `userId`（`/pool/transfers`） | **uuid**（形式が違えば 400。形式が正しく該当が無ければ `200` で `"total": 0`） | フィルタ無し |

空文字（`?from=`）は「指定なし」として扱います。

#### 日付の指定（`from` / `to` の境界）

**日付のみを指定した場合の基準は UTC です。**

| 指定 | 解釈される境界 |
|---|---|
| `from=2026-09-15`（日付のみ） | `2026-09-15T00:00:00Z` **以降**（その日の始まり） |
| `to=2026-09-15`（日付のみ） | `2026-09-15T23:59:59.999999Z` **まで** = **その日を丸ごと含みます** |
| `from` / `to` に日時を指定 | 指定した時刻がそのまま境界（両端とも含みます） |

したがって **1 日ぶんを取るには `?from=2026-09-15&to=2026-09-15`** と書きます
（`to` に翌日を渡す必要はありません）。日時で書くなら
`?from=2026-09-15T00:00:00Z&to=2026-09-15T23:59:59Z` が同じ区間です。

```bash
# 下の 2 本は同じ区間を返します（total が一致します）
curl -s "$BASE_URL/pool/transfers?from=2026-09-15&to=2026-09-15" \
  -H "Authorization: Bearer $TOKEN"
curl -s "$BASE_URL/pool/transfers?from=2026-09-15&to=2026-09-15T23:59:59Z" \
  -H "Authorization: Bearer $TOKEN"
```

> 日本時間で集計される場合はご注意ください。日付のみの指定は UTC 基準なので、
> `from=2026-09-15&to=2026-09-15` に入るのは JST では 9/15 09:00 〜 9/16 08:59:59 の
> 取引です。JST の 1 日で切るには日時（`+09:00`）で指定してください
> （例: `?from=2026-09-15T00:00:00+09:00&to=2026-09-15T23:59:59+09:00`）。

**秒の小数部は 6 桁（μs）まで**です。記録されている時刻が μs 精度のため、7 桁以上
（ナノ秒）を指定すると `400` になります（黙って 6 桁に丸めません）。

```bash
# 6 桁までは受け付けます
$ curl -s "$BASE_URL/pool/ledger?to=2026-09-15T23:59:59.999999Z" \
  -H "Authorization: Bearer $TOKEN"

# 7 桁は 400（`from` も同じ規則です）
$ curl -s "$BASE_URL/pool/ledger?to=2026-09-15T23:59:59.9999999Z" \
  -H "Authorization: Bearer $TOKEN"
{"message":"to must be an ISO 8601 date or datetime (e.g. \"2026-09-14\" or \"2026-09-14T00:00:00Z\")","code":400}
```

### 受け付ける引数名（これ以外は 400）

引数名は**大文字小文字を区別します**（`userid` は `userId` ではありません）。

| エンドポイント | 受け付ける引数 |
|---|---|
| `GET /pool/ledger` | `type`, `from`, `to`, `limit`, `offset` |
| `GET /pool/transfers` | `status`, `userId`, `from`, `to`, `limit`, `offset` |
| `GET /users/list` | `limit`, `offset` |
| `GET /referral-codes` | （なし。常に全件を返します） |
| `GET /pool/balance` | （なし。常に現在の残高を返します） |
| `GET /pool/deposit_address` | （なし。常に登録済みのアドレスを返します） |

表に無い引数を付けると `400` になり、本文にそのエンドポイントが受け付ける引数名が
列挙されます。

```bash
$ curl -s "$BASE_URL/pool/ledger?userid=abc" -H "Authorization: Bearer $TOKEN"
{"message":"Unknown query parameter \"userid\". Accepted: type, from, to, limit, offset","code":400}
```

引数名だけでなく**値**も同じ規則です。`GET /pool/transfers` の `userId`（uuid 形式）と
`status`（`pending` / `settled` / `failed` / `rejected`）は、形式・語彙が違えば `400` で、
受け付ける形式・値が本文に出ます（上記「GET /pool/transfers」参照）。

> 御社のページング・日付フィルタの実装に誤りがあった場合、Pay3 側で勝手に別の値へ
> 読み替えたり、知らない引数を捨てて全件を返したりすると、誤りが発覚しません。
> 引数名の綴り違いは「絞り込めていない一覧」として返るのが最も見つけにくいため、
> 値と同じく 400 で明示的に返します。

## 未知のパス・エラー本文の形式

- 認識できないパス・未対応の HTTP メソッドは **JSON の 404**
  （`{ "message": "Unknown endpoint. ...", "code": 404 }`）を返します。
  綴り違い（例: `POST /pool/tranfer`）が「成功」で返ることはありません。
- **この 404 の約束が掛かる範囲は `/pool/*`・`/referral-codes*`・`/users/*`・`/oauth/*` です。**
  `/kyc/*` と `/card/*` の未知サブパス（例: `GET /kyc/zzz`）は、現状
  **JSON ではなく `500` の `text/plain`** を返します。既存のモバイルアプリ経路と実行順を
  共有しているため、引き渡し後に JSON 404 へ揃えます。それまでは下記「4xx / 5xx が常に
  JSON とは限りません」と同じ扱い（`content-type` を見る）で実装してください。
- **ただし 4xx / 5xx が常に JSON とは限りません。** リクエストが Pay3 のアプリケーションに
  到達する前に、エッジ（Supabase / Cloudflare）が独自の応答を返すことがあります。
  実測している例（2026-09-16 再実測）:
  - URL に**不正なパーセントエンコード**（生の `%` 等）を含む → `500` の `text/plain`
    （`error code: 1101`）
  - パスに **SQL インジェクションに見える並び**（例: `/referral-codes/'%20OR%201=1--`）を含む
    → Cloudflare WAF の **HTML の 403**。`'` を 1 文字含むだけ（例: `/referral-codes/a'b`）では
    発火せず、通常の JSON 応答になります

  いずれも Pay3 側では制御できません。**ベース URL のホストを変えても同じ**です
  （`api-staging.pay-3.io` と、その CNAME 先を直接叩いた場合とで、ステータス・`content-type`・
  本文が一致することを確認しています）。エラー処理は `content-type` を確認し、
  **JSON でない本文でもパーサが落ちない**ように実装してください。

## 決済モード（sandbox と本番の違い）

決済モードは **クライアントごと** に Pay3 側が設定します（設定は Pay3 の内部運用の専権で、
パートナー向け API から変更することはできません）。

| 値 | 挙動 |
|---|---|
| `simulate` | **実際に資金が動きます**（プール残高 → ユーザーのカード残高）。サンドボックス用の値です |

サンドボックスで定義している値は `simulate` のみです。本番モードの値は本番環境のご案内時に別途お知らせします。

> プールへの入金（オンチェーンの着金）の検知は決済モードとは別の経路で、**サンドボックスでも自動で動きます**
> （2026-09-18 に実配信で確認済み。§5 と `pool.deposit.credited` を参照）。

- **モードが未設定のクライアントは `POST /pool/transfer` が `503` を返します。** 既定値を
  持たせていないのは、設定漏れのまま本番に出ると「実資金が動いていないのに台帳上は成功」
  という状態を作ってしまうためです。
- sandbox を使い始める前に、お使いのクライアントが `simulate` に設定されていることを
  Pay3 側で確認してください（未設定だと 503 になります）。
- `simulate` でも資金移動は本番と同じ経路を通ります。したがって **`settled` になったチャージ指示は
  カード残高に実際に反映されています**。資金が動かせなかった場合（プール原資の不足・決済基盤側の
  エラー）は `settled` にはならず、`failed` として理由付きで記録され、プール残高へ返還されます。
- 設定はクライアント単位なので、**同じ環境で別のクライアントが本番モードで動いていても
  互いに影響しません**（sandbox の試験導入が本番の決済モードを動かすことはありません）。
- `simulate` で確定した行は `settlementMode: "simulate"` が付き、台帳の `metadata` にも
  残ります。本番切替後に「sandbox 時代の行が実移動済みに見える」ことはありません。

## 未実装 / 制約（2026-09-18 時点）

- 本番モード（`settlementMode` の本番値）の実資金移動は未実装です。sandbox の受入テストは `simulate` で行ってください。
- `userId` は Pay3 の uuid のみ受け付けます。`P123456` 形式の対外 ID は未採番です。
- プール入金の着金検知は**自動で動きます**（2026-09-18 にテストネット USDC で確認済み）。検知できなかった着金は
  保留として記録し、Pay3 側が手当てします（黙って捨てません）。
- USD → USDT の出金は元帳への記録のみ自動化されており、**実際の USDT 送金は運用手作業**です。
