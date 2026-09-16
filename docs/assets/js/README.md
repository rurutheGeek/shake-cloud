# 同梱JS

## mermaid.min.js

- 出所: <https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js>
- 版: Mermaid 11（2026-09-13取得）
- ライセンス: MIT
- 使い方: `docs/assets/js/mermaid-init.js` と合わせて `mkdocs.yml` の `extra_javascript` で読み込む。CDNへ依存せずオフラインで描画する。
- 更新: URLを版固定（例 `mermaid@11.x.y`）にして差し替え、sha256を確認する。

## mermaid-init.js

` ```mermaid ` のコードブロックを `div.mermaid` に置き換えて描画する初期化コード。
