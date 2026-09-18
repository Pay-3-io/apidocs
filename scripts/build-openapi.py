#!/usr/bin/env python3
"""backend-V3/docs から公開用 openapi.yaml を組み立てる。

Scalar 1 枚で見せるため、ガイド（api/*.md）を info.description に埋め込む。
- 見出しはそのまま（Scalar は description の見出しをサイドバーの Introduction 配下に出す）
- ガイド間の相対リンク（xxx.md / xxx.md#frag / #frag）は Scalar 内で解決できないので、
  リンク文字列だけ残して太字にする
使い方: python3 scripts/build-openapi.py <backend-V3/docs のパス>
"""
import re, sys, pathlib

GUIDES = [
    ("quickstart", "Quickstart"),
    ("authentication", "Authentication"),
    ("environments", "Environments"),
    ("endpoints", "Endpoints"),
    ("users", "Users"),
    ("pool", "Partner Pool"),
    ("referral-codes", "Referral Codes"),
    ("idempotency", "Idempotency"),
    ("webhooks", "Webhooks"),
]

def strip_relative_links(md: str) -> str:
    # [text](file.md), [text](./file.md#frag), [text](#frag) -> **text**
    md = re.sub(r"\[([^\]]+)\]\((?:\./)?[A-Za-z0-9_.-]+\.md(?:#[^)]*)?\)", r"**\1**", md)
    md = re.sub(r"\[([^\]]+)\]\(#[^)]*\)", r"**\1**", md)
    md = md.replace("(../openapi.yaml)", "(openapi.yaml)")
    return md

def main(src: str) -> None:
    src_dir = pathlib.Path(src)
    spec = (src_dir / "openapi.yaml").read_text(encoding="utf-8")
    parts = [
        "Pay3 のカード発行・KYC・決済インフラを、御社の UI を保ったまま API で利用するための B2B API です。",
        "認証は OAuth アクセストークン（クライアント ID + API キー）。資格情報・Webhook・送信元 IP は"
        "パートナーコンソールの「開発者」メニュー、または `/developer/*` で御社自身が管理します。",
        "",
        "以下はガイドです。各エンドポイントの機械可読な定義は左のメニュー（Auth 以降）を参照してください。",
        "",
    ]
    for slug, _title in GUIDES:
        md = (src_dir / "api" / f"{slug}.md").read_text(encoding="utf-8").rstrip()
        parts.append(strip_relative_links(md))
        parts.append("")
        parts.append("---")
        parts.append("")
    desc = "\n".join(parts).rstrip() + "\n"
    # description を YAML のブロックスカラーに
    block = "  description: |\n" + "".join(("    " + ln if ln else "") + "\n" for ln in desc.split("\n"))
    m = re.search(r"^  description: .*\n", spec, flags=re.M)
    assert m, "info.description が見つからない"
    spec = spec[: m.start()] + block + spec[m.end():]
    pathlib.Path("openapi.yaml").write_text(spec, encoding="utf-8")
    print(f"openapi.yaml written ({len(spec)} bytes, guides={len(GUIDES)})")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../backend-V3/docs")
