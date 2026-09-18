# Idempotency

金銭やプロビジョニングが動く操作（カード発行、KYC submit）は、ネットワーク再送による**二重実行**を防ぐため冪等化されています。

## 使い方

リクエストに `Idempotency-Key` ヘッダを付けます。値は御社が生成する一意な文字列（UUID 推奨）。

```bash
curl -X POST "$BASE_URL/card/issue_card" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "Idempotency-Key: 7c1f...-unique" \
  -d '{ "userId": "<uuid>", "type": "virtual" }'
```

## 挙動

- 同一 `(client, Idempotency-Key, endpoint)` の初回リクエストのみ実行され、結果が保存されます。
- 同じキーで再送すると、**最初の結果がそのまま返ります**（再実行されない＝カードが2枚発行されない）。
  **これは保存されたレスポンスの再生であって、最新の状態ではありません。** 例えば
  `POST /pool/transfer` の再送は、その指示が既に `settled` になっていても初回の
  `{"status":"pending"}` を返します。**最新状態は `GET /pool/transfer/{transferId}` で取得**
  してください（「同一キーの再送 = 同一応答」を契約として保つためにこの形にしています）。
- 同じキーに**異なるボディ**を付けて送ると `409` を返します（別の指示を同じキーで送ってしまった取り違えの検出）。
- 最初のリクエストがまだ処理中に同じキーが来た場合は `409`（in progress）を返します。少し待って再送してください。
- 最初のリクエストがサーバーエラーで失敗した場合はキーが解放され、同じキーで再試行できます。

## 対象エンドポイント

- `POST /card/issue_card`
- `POST /kyc/submit`
- `POST /pool/transfer`

ヘッダ未指定でも動作しますが、**上記の操作では必ず付けることを強く推奨**します。
