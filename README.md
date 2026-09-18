# Pay3 B2B API Docs

Pay3 の B2B カード発行 API の公式ドキュメント。`openapi.yaml`（OpenAPI 3.1）を [Scalar](https://github.com/scalar/scalar) で静的レンダリングする構成。**完全無料・依存サービスなし**（Scalar は CDN の OSS、ホスティングは GitHub Pages）。

## ファイル
**正本は `Pay-3-io/backend-V3` の `docs/`**（このリポジトリはその公開用コピー。編集は backend 側で行い、ここへ同期する）。

- `index.html` — Scalar レンダラ（モダン UI・ダークモード）。`openapi.yaml` を読み込む。**これ 1 枚が公開サイト**
- `openapi.yaml` — 公開用の API 仕様。`scripts/build-openapi.py` が backend の `openapi.yaml` に
  ガイド（`api/*.md` 9 本）を `info.description` として埋め込んで生成する（Scalar の Introduction 配下に出る）
- `api/*.md` / `llms.txt` — ガイドの生ファイルと LLM 向け目次（人は `index.html` で読む）
- `.nojekyll` — GitHub Pages の Jekyll 変換を止める（`api/*.md` をそのまま配信するため）
- `CNAME` — カスタムドメイン `developer.pay-3.io` 用

同期手順（backend の docs が更新されたら）:
```bash
cp <backend-V3>/docs/api/{quickstart,authentication,endpoints,users,pool,referral-codes,idempotency,webhooks,environments}.md api/
cp <backend-V3>/docs/llms.txt .
python3 scripts/build-openapi.py <backend-V3>/docs   # → openapi.yaml
```
`junoe-*.md` は社内向けなので含めない。

## ローカルプレビュー
```bash
# どれでも可
npx @scalar/cli@latest document serve openapi.yaml  # もしくは下の静的サーバ
# もしくは静的サーバ
python3 -m http.server 8080   # → http://localhost:8080
```

## 公開（GitHub Pages・無料・リポジトリ管理者が制御）
**公開中**。GitHub Pages が `init-docs` ブランチ（`/root`）から配信し、カスタムドメイン `developer.pay-3.io`（`CNAME` ファイル）で公開している。`init-docs` に push すれば数分で反映される。

- 公開URL: https://developer.pay-3.io/ （= `https://pay-3-io.github.io/apidocs/`）
- 設定: **Settings → Pages** → Source: Deploy from a branch → Branch: `init-docs` / `/root`
- カスタムドメイン: Settings → Pages → Custom domain = `developer.pay-3.io`、Enforce HTTPS 有効。DNS は `developer.pay-3.io` の CNAME を `pay-3-io.github.io` に向ける。

> Scalar は特定バージョン(1.61.0)に固定し SRI(integrity) を付与済み。バージョン更新時は `index.html` の version と integrity を同時に更新する。

## 仕様のメンテ
- 認証は2層（Admin Basic でクライアント管理 / OAuth Bearer でデータプレーン）。Admin 系エンドポイントは公開 docs には含めない。
- 新規エンドポイント追加時は `openapi.yaml` に追記するだけ。
- Webhook は OpenAPI 3.1 の `webhooks` に定義。
