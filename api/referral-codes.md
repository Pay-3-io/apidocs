# Referral Codes（紹介コード）

御社の紹介コード（代理店コード）を登録し、コード付きリンク経由で登録したユーザーを
そのコードに紐付けます。

すべて `Authorization: Bearer <accessToken>` が必要です。
Base URL (sandbox): `https://api-staging.pay-3.io/functions/v1/external-service`

> **ベース URL は末尾の `/external-service` まで含みます**（仕様書 §2 と同じ定義です）。
> 以下の見出しのパスはすべてそのベース URL の直下です
> （例: `GET {BASE_URL}/referral-codes`）。同じ注記が [pool.md](pool.md) の冒頭にあります。

## 必要なスコープ

| スコープ | 範囲 |
|---|---|
| `referrals:read` | 一覧の取得 |
| `referrals:write` | 登録・有効化切替・削除（`referrals:read` を含む） |

## コードの規則

- 英数字・ハイフン・アンダースコアの 3〜64 文字。
- **大文字小文字は区別しません**。`PARTNER-A` と `partner-a` は同じコードで、共存できません。
- **早い者勝ち**。全社横断で一意です（ユーザーの登録導線が 1 つの名前空間のため）。
- **誤登録は「変更」ではなく「削除して新規作成」**してください。改名 API は提供しません
  （カスケード変更と履歴の取り扱いを避けるための明示的な決定です）。

## GET /referral-codes

自社のコード一覧。

- 200:
  ```json
  {
    "data": [
      { "code": "PARTNER-A", "enabled": true, "label": "代理店A",
        "link": "https://app.pay-3.io/?ref=PARTNER-A",
        "createdAt": "...", "updatedAt": "..." }
    ]
  }
  ```
- **クエリ引数は受け付けません。** 常に自社の全コードを新しい順で返します
  （ページングも絞り込みもありません）。`?enabled=true` のような引数を付けると `400` で、
  本文は `Unknown query parameter "enabled". Accepted: (none)` になります。
  効いていない引数を黙って捨てて「絞り込めたように見える全件」を返さないためです
  （詳細は [pool.md の「クエリ引数の検証」](pool.md#クエリ引数の検証)）。

## POST /referral-codes

- body: `{ "code": "PARTNER-A", "label": "代理店A", "enabled": true }`
  - `label` / `enabled` は省略可（`enabled` の既定は `true`）
- 201: 上記 1 件の形
- 400: コードの形式が不正
- 409: 既に使われている（早い者勝ち）

## PATCH /referral-codes/{code}

有効化 / 無効化のみ。

- body: `{ "enabled": false }`
- 200: 更新後の 1 件
- 400: `enabled` 以外を変更しようとした（改名は削除 → 新規作成）
- 404: 見つからない

無効化したコードは新規の紐付けに使えなくなります（`POST /users/register` が 400 を返す）。
**既に紐付いたユーザーの帰属は変わりません。**

## DELETE /referral-codes/{code}

- 200: `{ "code": "PARTNER-A", "deleted": true }`
- 404: 見つからない

ユーザーの帰属は登録時点で確定するため、**削除しても過去の帰属・集計は変わりません。**
削除は元に戻せないので、コンソールから操作する場合は確認のうえ実行してください。

> コードは完全一致で照合します。`%` や `_` をパスに入れても
> ワイルドカードとして扱われることはありません（一括削除はできません）。

---

## ユーザーとの紐付け

`POST /users/register` に `referral_code` を付けて登録すると、
そのユーザーがコードに紐付きます。

```bash
curl -X POST "$BASE_URL/users/register" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
        "signup_type": "EMAIL",
        "signup_type_id": "taro@example.com",
        "first_name": "Taro",
        "referral_code": "PARTNER-A"
      }'
```

- 成功時のレスポンスに `referralCode` が入ります（紐付かなかった場合は `null`）。
- **`referral_code` に指定できるのは、ご自身の client で発行されたコードだけです。**
  他社が発行したコードは、実在しないコードと**同じ `400`**（同一のレスポンス本文）になります。
- **コードが未登録 / 無効化済みの場合は `400` を返し、ユーザーを作成しません。**
  黙って無視すると「コードを付けたのに紐付いていない」状態が静かに発生するためです。
- 紐付けは **1 ユーザー 1 件**で、後から上書きされません。

### Web 登録導線（`?ref=` 付きリンク）について

`GET /referral-codes` が返す `link`（`https://app.pay-3.io/?ref=CODE`）は、
**Web 登録画面側での `?ref` 取り込みが未実装のため、現時点では紐付きません。**
2026-09-14 時点で紐付けが動作するのは上記の **API 登録経路のみ**です。
Web 導線を使う場合は別途 Pay3 側の対応が必要です。
