# Forgejo（リポジトリの保管庫）

利用者向けの説明と運用は [docs/services/forgejo.md](../../../docs/services/forgejo.md)。

| ファイル | 役割 |
|---|---|
| `compose.yaml` | Forgejo 1つ。`127.0.0.1:8083`、`mem_limit` 512m、SSH 無し、SQLite |
| `compose.lock.yaml` | イメージの digest（LTS 15 系） |
| `mirrors.json` | ミラーの一覧（正本）。外しても消さない |
| `manage.py` | `init`・`up`（起動 → ログイン手段 → 管理用利用者とトークン → 組織 `archive` → ミラー）・`mirrors`・`status`・`down`・`backup` |

`up` は何度流しても同じ結果になる。OIDC の秘密値（`secrets/oidc_client.json`）が無いあいだはログイン手段を登録せずに進む。
