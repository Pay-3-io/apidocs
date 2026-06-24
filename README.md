# Pay3 B2B API Docs

Pay3 の B2B カード発行 API の公式ドキュメント。`openapi.yaml`（OpenAPI 3.1）を [Redoc](https://github.com/Redocly/redoc) で静的レンダリングする構成。**完全無料・依存サービスなし**（Redoc は CDN の OSS、ホスティングは GitHub Pages）。

## ファイル
- `openapi.yaml` — API 仕様（唯一の正。これを編集すれば docs が更新される）
- `index.html` — Redoc レンダラ（`openapi.yaml` を読み込む）
- `CNAME` — カスタムドメイン `developer.pay-3.io` 用

## ローカルプレビュー
```bash
# どれでも可
npx @redocly/cli preview-docs openapi.yaml
# もしくは静的サーバ
python3 -m http.server 8080   # → http://localhost:8080
```

## 公開（GitHub Pages・無料・リポジトリ管理者が制御）
現状 `developer.pay-3.io` は Vercel 上の Redoc 配信ですが、その Vercel プロジェクトに権限が無いため、**GitHub Pages に移行**して org 管理下で運用する。

1. このリポジトリの **Settings → Pages**
2. **Source: Deploy from a branch** → Branch: `main`（または公開したいブランチ）/ `/root`
3. 数分で `https://pay-3-io.github.io/apidocs/` に公開される
4. カスタムドメインを使う場合:
   - `CNAME` ファイル（`developer.pay-3.io`）はこのリポジトリに含む
   - DNS: `developer.pay-3.io` の CNAME を `pay-3-io.github.io` に向ける（現在の Vercel 向け設定を差し替え）
   - Settings → Pages → Custom domain に `developer.pay-3.io` を設定し Enforce HTTPS

> Redoc は特定バージョン(2.1.5)に固定し SRI(integrity) を付与済み。バージョン更新時は `index.html` の version と integrity を同時に更新する。

## 仕様のメンテ
- 認証は2層（Admin Basic でクライアント管理 / OAuth Bearer でデータプレーン）。Admin 系エンドポイントは公開 docs には含めない。
- 新規エンドポイント追加時は `openapi.yaml` に追記するだけ。
- Webhook は `x-webhooks`（Redoc 拡張）に定義。
