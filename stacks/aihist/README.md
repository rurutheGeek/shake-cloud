# aihist

AI ツール（Claude Code・Codex・Antigravity・OpenCode）の会話履歴を集め、検索・閲覧し、別の AI へ渡す Markdown に書き出す。本体は非公開リポジトリ [rurutheGeek/aihist](https://github.com/rurutheGeek/aihist) の GitHub Release が正本で、ここには配備の部品だけを置く。

| 項目 | 値 |
|---|---|
| ホスト | media-01（systemd の `aihist.service`、`127.0.0.1:5840`） |
| 本体 | `/opt/aihist/aihist`（版と sha256 は `platform/ansible/group_vars/media.yml`） |
| データ | `/srv/media-bulk/aihist`（HDD。`aihist.db` と送られた原本 `raw/`） |
| 入口 | `https://aihist.<ゾーン>`。画面は Forward Auth（admins）、`/api/*` は SSO を通さずトークンで守る |
| トークン | `platform/sops/aihist.sops.yaml` の `AIHIST_TOKEN` |
| 配備 | `platform/ansible/media-aihist.yml` |
