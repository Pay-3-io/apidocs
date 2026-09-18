# Quickstart

Pay3 External (B2B) API を使って、ユーザー登録から仮想カード発行までを通す最短手順です。

- **Base URL (sandbox)**: `https://api-staging.pay-3.io/functions/v1/external-service`
- 認証は **OAuth アクセストークン**（クライアント ID と API キーで取得）。クライアントの作成は Pay3 が行います。
- フロントエンド（ユーザー向け画面）は御社で実装します。本 API はバックエンドのみを提供します。

## 0. 事前準備

Pay3 が御社用のクライアントを作成し、パートナーコンソールに御社の担当者を招待します。
コンソールの「開発者」メニューで **クライアント ID（`client_` + 32 桁の 16 進数）** を確認し、
**API キー（`pay3_sk_test_…` = サンドボックス / `pay3_sk_live_…` = 本番）** を発行してください。
キーの全文は発行した瞬間にだけ表示されます（Pay3 側にも平文は残りません）。控えを失った場合は再発行してください。
続けて同じ画面で **送信元 IP** を登録します — 登録した IP からの呼び出しだけを受け付けます
（未登録の間は 403 `ip_not_registered`）。

## 1. アクセストークンを取得

```bash
curl -X POST "$BASE_URL/oauth/access-token" \
  -H "Content-Type: application/json" \
  -d '{ "clientId": "client_<32 hex>", "clientSecret": "pay3_sk_test_..." }'
# => { "success": true, "accessToken": "<token>" }
```

以降の API 呼び出しは `Authorization: Bearer <accessToken>` を付けます。トークンの有効期限は既定1時間です。
スキームは **`Bearer` のみ**受理します（大文字小文字は区別しません）— `Basic` 等の他のスキーム語や、
スキーム語を省いたトークン単体は `401` です。詳細は [authentication.md](./authentication.md)。

## 2. ユーザーを登録

```bash
curl -X POST "$BASE_URL/users/register" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "signup_type": "EMAIL", "signup_type_id": "taro@example.com",
        "email": "taro@example.com", "first_name": "Taro", "last_name": "Yamada" }'
# => { "data": { "userId": "<uuid>", ... }, "code": 0 }
```

> `signup_type`（`EMAIL`/`PHONE`/`TELEGRAM`）と `signup_type_id`（その識別子）は**必須**です。

登録したユーザーは御社クライアントに紐づき（テナント分離）、他クライアントからは参照できません。

## 3. KYC を実施（カード発行の前提）

```bash
# Sumsub アクセストークンを取得し、御社UIで本人確認を完了させる
curl -X POST "$BASE_URL/kyc/access-token" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "userId": "<uuid>" }'

# 本人確認完了後、KYC を submit（口座/カード基盤のセットアップを起動）
curl -X POST "$BASE_URL/kyc/submit" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "Idempotency-Key: <unique-key>" \
  -d '{ "userId": "<uuid>", "applicantId": "<sumsub-applicant-id>" }'
```

## 4. カードを発行

```bash
curl -X POST "$BASE_URL/card/issue_card" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "Idempotency-Key: <unique-key>" \
  -d '{ "userId": "<uuid>", "type": "virtual" }'
# => { "data": { ...card }, "code": 0 }
```

- `type`: `"virtual"` または `"physical"`
- `amount`（任意）: 発行と同時にユーザー残高へ載せる入金額。省略時は `0`。
- `bin`（任意）: 発行する BIN。省略時はその種別を出せる先頭 BIN（サンドボックスの virtual では `537100`）。
  値域と組み合わせの制約は [endpoints.md の「カード BIN の値域」](endpoints.md#カード-bin-の値域) を参照。
- **発行価格は Pay3 側（SystemConfig）で一元管理**され、API では指定しません。
- **発行にはユーザー残高が必要です**（発行価格ぶん）。足りない場合は **400（事前拒否）/ 402（発行途中で
  徴収が尽きた。カードは Pay3 が閉じます）** の 2 系統で、必要額をハードコードせず `status` / `code` で
  分岐してください →
  [endpoints.md「残高が足りないときは 400 と 402 の 2 系統があります」](endpoints.md#残高が足りないときは-400-と-402-の-2-系統があります)
- **`kyc/submit` は口座/カード基盤のセットアップを「起動」する非同期処理**です。セットアップが終わる前に
  発行を叩くと **409**（カードは作られません）が返るので、`user.kyc.updated` Webhook か
  `GET /users/{userId}` の `kycStatus` を確認してから、新しい `Idempotency-Key` で再実行してください。
- 金銭が動く操作（発行・KYC submit）には必ず [`Idempotency-Key`](idempotency.md) を付けてください。

BIN を指定して発行する場合（例: Visa の Pay3 Card）:

```bash
curl -X POST "$BASE_URL/card/issue_card" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "Idempotency-Key: <unique-key>" \
  -d '{ "userId": "<uuid>", "type": "virtual", "bin": "45492418" }'
# => { "data": { ..., "bin": "45492418" }, "code": 0 }
```

発行前に価格を確認したい場合は見積もりを取れます（**金銭は動きません**）:

```bash
curl -X POST "$BASE_URL/card/quote" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "userId": "<uuid>", "type": "virtual", "bin": "45492418" }'
# => {
#      "message": "Quote generated",
#      "data": { "bin": "45492418", "form_factor": "virtual", "country": null, "currency": "USD",
#                "price": "5.00", "estimated_shipping": null, "total": "5.00" },
#      "code": 0
#    }
```

- `type` を省略すると `physical` として解決されます。**virtual を見積もるときは必ず `type` を付けてください。**
- カタログに無い `bin`、その BIN で出せない `type` は **400**（`Unsupported card bin/form factor`）で返ります。
- **金額（`price` / `total` / `estimated_shipping`）は小数 2 桁固定の「文字列」**です（`"5.00"`。JSON の数値ではありません）。
  `estimated_shipping` は該当しないとき（virtual、または `country` 未指定）`null` — **「無料」ではなく「対象外」**の意味です。

## 5. 発行進捗・カード情報を確認

```bash
# 発行進捗イベント（ローディングUI用）
curl -X POST "$BASE_URL/card/issuance_events" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "userId": "<uuid>" }'

# 発行済みカード一覧
curl -X POST "$BASE_URL/card/fetch_cards" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "userId": "<uuid>" }'
```

## 6. イベントを受け取る（任意）

カード発行などのイベントを御社システムへ push 受信するには [Webhooks](webhooks.md) を設定してください。

---
次に読む: [Authentication](authentication.md) / [Endpoints](endpoints.md) / [Webhooks](webhooks.md)
