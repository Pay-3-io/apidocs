# Environments

| 環境 | 用途 | 外部連携 | Base URL |
|---|---|---|---|
| **sandbox (Development)** | 御社の結合テスト用。偽カード・偽KYCで安全に試せる | カード基盤サンドボックス / Sumsub sandbox | `https://api-staging.pay-3.io/functions/v1/external-service` |
| **production** | 本番 | カード基盤本番 / Sumsub 本番 | `https://api.pay-3.io/functions/v1/external-service` |

いずれも**ベース URL は末尾の `/external-service` まで含みます**（仕様書 §2 と同じ定義）。
API のパスはすべてそのベース URL の直下です（例: `GET {BASE_URL}/pool/balance`）。

## sandbox の使い方

1. Pay3 からパートナーコンソール（sandbox: `https://console-staging.pay-3.io`）の招待を受け取り、「開発者」メニューで
   クライアント ID を確認し、API キーを発行して、送信元 IP を登録する。
2. [Quickstart](quickstart.md) の手順を sandbox Base URL に対して実行。
3. カード発行・KYC は sandbox プロバイダに対して行われ、実課金・実発行は起きません。
4. プールへの入金は **USDC / Ethereum Sepolia（テストネット）のみ**です。入金先アドレスと通貨・チェーンは
   `GET /pool/deposit_address` とコンソールの「プール」に表示されます（[pool.md](pool.md)）。
   本番は USDT / TRON です。**表示された通貨・チェーン以外を同じアドレスへ送ると着金しません。**

## 動作確認のおすすめ順

1. `oauth/access-token` でトークン取得（認証の疎通）
2. `users/register` でユーザー作成
3. `kyc/access-token` → 本人確認 → `kyc/submit`
4. `card/issue_card`（`Idempotency-Key` 付き）
5. `card/issuance_events` / `fetch_cards` で結果確認
6. Webhook を設定して `webhooks/test` で受信確認

## 注意

- sandbox と production は**別々のクライアント資格情報**（`pay3_sk_test_…` / `pay3_sk_live_…`）です。混在させないでください。
- production のクレデンシャル・Webhook secret はサーバー側のみで管理してください。
