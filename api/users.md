# Users（ユーザーステータス照会）

御社の紹介コード経由で登録したユーザーの KYC 完了状況・カード発行ステータスを返します
（仕様書 §8）。

すべて `Authorization: Bearer <accessToken>` が必要です。
Base URL (sandbox): `https://api-staging.pay-3.io/functions/v1/external-service`

> **ベース URL は末尾の `/external-service` まで含みます**（仕様書 §2 と同じ定義です）。
> 以下の見出しのパスはすべてそのベース URL の直下です
> （例: `GET {BASE_URL}/users/{userId}`）。同じ注記が [pool.md](pool.md) の冒頭にあります。

## 必要なスコープ

| スコープ | 範囲 |
|---|---|
| `users:status` | `GET /users/list` と `GET /users/{userId}`（`users:read` を持っていれば自動的に満たします） |

> これらのエンドポイントは **permissions を明示的に設定したクライアントだけ**が呼べます。
> permissions が未設定のクライアントは（他の一部エンドポイントと違い）素通りせず `403` です。

## 見える範囲

**御社に属しているユーザーだけ**が見えます。次のどちらかを満たすユーザーです。

1. 紹介コード付きの登録リンク経由で登録したユーザー（= `user.registered` Webhook が
   届いたユーザー。§7）。帰属は**登録時点で確定**し、あとからコードを無効化・削除しても
   変わりません
2. `POST /users/register` で御社が作成したユーザー

この集合は `GET /users/list`・`GET /users/{userId}`・`POST /pool/transfer`
（[pool.md](pool.md)）で**完全に同一**です。一覧に出たユーザーは必ず照会でき、必ずチャージ
指示を出せます（KYC 等の条件は別途かかります）。

属していない userId・他社のユーザー・存在しない userId は**すべて `404`** を返します
（`403` は返しません。存在するかどうかを含めてお返ししない方針のためです）。

## GET /users/list

御社に属しているユーザーの一覧です（仕様書 §10-3「登録ユーザー一覧」の API 面）。

```bash
curl -s "$BASE_URL/users/list?limit=50&offset=0" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

- 200:
  ```json
  {
    "data": [
      {
        "userId": "5c3ff529-0000-4000-8000-000000000000",
        "registeredAt": "2026-09-14T10:11:12.000Z",
        "referralCode": "PARTNER-A",
        "kycStatus": "approved",
        "kyc": { "identity": { "status": "approved" }, "cardIssuer": { "status": "approved" } },
        "cardStatus": "issued"
      }
    ],
    "paging": { "limit": 50, "offset": 0, "total": 1 }
  }
  ```
- 該当ユーザーが 0 人のときは `{"data": [], "paging": {"limit":50,"offset":0,"total":0}}`
  （`404` にはなりません。「読めない」ではなく「0 件」です）
- 400: `limit` / `offset` が不正、または**受け付けない引数名**（下記の値域を参照）
- 403: 必要スコープがありません

| フィールド | 意味 |
|---|---|
| `userId` | Pay3 のユーザー ID（現行サンドボックスでは UUID 形式） |
| `registeredAt` | 登録日時（ISO 8601・UTC） |
| `referralCode` | 登録時に確定した紹介コード。`POST /users/register` 経由で紹介コードが無いユーザーは `null` |
| `kycStatus` | 総合。`GET /users/{userId}` と**同じ語彙・同じ判定**（下記 [kycStatus と kyc](#kycstatus-と-kyc段ごとの状態)） |
| `kyc` | 段ごとの状態 `{ identity: { status }, cardIssuer: { status } }`（同上） |
| `cardStatus` | カード発行状況の要約。`issued`（発行済み）/ `not_issued`（未発行） |

> **`cardStatus` は要約です。** カードの枚数・種別（virtual/physical）・`frozen` などの
> 実状況は `GET /users/{userId}` の `cards` でお取りください。一覧はユーザー数に比例した
> カード照会を行わない設計のため（一覧の表示がカード基盤の状態に引きずられないように
> するためです）、DB 上の発行フラグだけを返します。

### ページング

| パラメータ | 既定値 | 値域 | 不正なとき |
|---|---|---|---|
| `limit` | `50` | 1〜200 の十進整数 | `400`（黙って丸めません） |
| `offset` | `0` | 0 以上の十進整数 | `400`。**総件数を超える `offset` は `200` の空ページ**（`"data": []`・`"total"` は総件数） |

- 並び順は**登録日時の新しい順**で固定です（同時刻は `userId` 順）。並びが固定なので
  `offset` を進めても行の取りこぼし・重複は起きません。
- `paging.total` は御社に属するユーザーの総数です（`limit` で切る前の件数）。

### 全ページを取る

`paging.total` を上限に `offset` を `limit` ずつ進めます。`/pool/ledger`・`/pool/transfers` も
同じ `paging` の形なので、同じ書き方がそのまま使えます。

```bash
LIMIT=200
OFFSET=0
while : ; do
  PAGE=$(curl -s "$BASE_URL/users/list?limit=$LIMIT&offset=$OFFSET" \
    -H "Authorization: Bearer $ACCESS_TOKEN")
  echo "$PAGE" | jq -c '.data[]'
  TOTAL=$(echo "$PAGE" | jq '.paging.total')
  OFFSET=$((OFFSET + LIMIT))
  [ "$OFFSET" -ge "$TOTAL" ] && break
done
```

- 終了条件は **`offset >= paging.total`** です。`data` が空になるまで回しても構いません
  （総件数を超えた `offset` は `404` ではなく **`200` の空ページ**を返します）。
- 巡回中に新しいユーザーが登録されると、並びが**新しい順**であるため後ろのページが 1 行ずつ
  ずれます。厳密な一巡が必要な場合は、**先頭から前回同期済みのユーザーに到達するまで辿る**
  差分同期（仕様書 §8.2）をお使いください。
- **受け付ける引数は `limit` / `offset` の 2 つだけ**です。それ以外の引数名（`?userid=`
  のような綴り違いを含む）を付けると `400` になり、本文に受け付ける引数名が列挙されます。
  引数名は大文字小文字を区別します。知らない引数を黙って捨てて全件を返すことはしません
  （詳細は [pool.md の「クエリ引数の検証」](pool.md#クエリ引数の検証)）。
- 絞り込み（紹介コード別など）・ソート指定・CSV 出力は現時点では提供していません。
  必要でしたらお知らせください。

## GET /users/{userId}

- `userId` は `user.registered` Webhook（§6.2）でお渡しする Pay3 のユーザー ID です。
  現行サンドボックスでは UUID 形式です。

```bash
curl -s "$BASE_URL/users/$USER_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

- 200:
  ```json
  {
    "userId": "P123456",
    "kycStatus": "approved",
    "kyc": { "identity": { "status": "approved" }, "cardIssuer": { "status": "approved" } },
    "cards": [
      { "cardType": "virtual", "status": "active" },
      { "cardType": "physical", "status": "shipped" }
    ]
  }
  ```
  - カードが 1 枚も無いユーザーは `"cards": []`（`null` にはなりません）。
  - **カード番号・CVV・BIN・請求先住所・氏名・メールアドレス等は含めません**（仕様書 §8）。
    項目の追加ご要望（残高等）があればお知らせください。
- 403: 必要スコープがありません
- 404: 御社に帰属していない / 存在しない userId
- 502: カード発行状況を一時的に取得できませんでした（カード 0 枚とは区別します。再試行してください）

### kycStatus と kyc（段ごとの状態）

Pay3 の本人確認は **2 段**あります。Sumsub による一次本人確認（`identity`）と、
その後に行われる**カード発行体の審査**（`cardIssuer`）です。一次が承認されても、
発行体の審査が終わるまでカードの発行・チャージ指示はできません。

- `kycStatus` … **総合**。`approved` は「チャージ指示・カード発行が通る状態」と同義です
- `kyc.identity.status` … 一次本人確認（Sumsub）
- `kyc.cardIssuer.status` … カード発行体の審査

```json
{
  "kycStatus": "pending",
  "kyc": {
    "identity":   { "status": "approved" },
    "cardIssuer": { "status": "pending" }
  }
}
```

| `kyc.identity.status` | 意味 |
|---|---|
| `not_submitted` | 一次本人確認が未実施（登録直後の状態） |
| `pending` | 書類提出済み・審査中 |
| `approved` | 一次本人確認は承認済み（**まだカードは発行できません**。発行体の審査へ自動で進みます） |
| `rejected` | 否認。再提出すると `pending` に戻ります |

| `kyc.cardIssuer.status` | 意味 |
|---|---|
| `not_started` | 一次本人確認が終わっていないため、発行体の審査は始まっていません |
| `pending` | 発行体が審査中（通常は数分。長い場合があります） |
| `approved` | 発行体の審査を通過し、カード発行・チャージができる状態 |
| `rejected` | 発行体が否認 |

総合 `kycStatus` は次のように決まります。

| `identity` | `cardIssuer` | `kycStatus` |
|---|---|---|
| `approved` 以外 | （問わない） | `identity` と同じ値 |
| `approved` | `approved` | `approved` |
| `approved` | `rejected` | `rejected` |
| `approved` | それ以外 | `pending` |

> **`approved` は「チャージ指示が通る状態」と同義**です。`POST /pool/transfer` が
> `412` を返す条件（KYC 未完了）と同じ判定なので、`approved` なのに `412` になることはありません。
> 一次が承認された時点では `kycStatus` は `pending` のままで、発行体の審査が通ると
> `approved` になります。その変化は [`user.kyc.updated`](webhooks.md) Webhook で通知します
> （`stage` で「どの段が変わったか」が分かります）。

### cards

| cardType | status | 意味 |
|---|---|---|
| `virtual` | `active` | 発行完了・即時利用可能 |
| `virtual` | `issued` | 発行手続き中（まだ利用できません） |
| `physical` | `issued` | 発行手続き完了・発送準備中 |
| `physical` | `shipped` | 発送済み（お手元に届くまで利用不可） |
| `physical` | `activated` | アクティブ化済み・利用可能 |
| 共通 | `frozen` | 一時停止中（ユーザー操作またはサポート対応） |

- `frozen` は種別より優先して返します（アクティブ化済みのリアルカードがロックされている場合も `frozen`）。
- 解約・無効化されたカードは一覧に含めません。

## 既存の `GET /users?id=` について

Pay3 の内部向けに `GET /users?id=<uuid>` という別のエンドポイントが
以前から存在しますが、**こちらは本仕様書の §8 とは別物**です（レスポンス形が異なります）。
御社の連携では `GET /users/{userId}` をお使いください。
