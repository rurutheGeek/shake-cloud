---
title: AIの会話履歴（aihist）
updated: 2026-10-16
section: 運用手順
audience: 管理者
tags:
  - ops
---

# AIの会話履歴（aihist）

> **更新日** 2026-10-16 ・ **区分** 運用手順 ・ **読む人** 管理者

## 正本

| 対象 | 場所 |
| --- | --- |
| 本体 | 非公開リポジトリ [`rurutheGeek/aihist`](https://github.com/rurutheGeek/aihist)。`group_vars/media.yml` の `aihist_version`／`aihist_sha256` で固定し、作業機の `gh` が GitHub Release から落として送る |
| systemd ユニット | `stacks/aihist/aihist.service.j2`（`aihist` ユーザー、`127.0.0.1:5840`） |
| データ | media-01 の `/srv/media-bulk/aihist`（HDD）。`aihist.db` と、送られた原本 `raw/<ホスト>/<ツール>/` |
| 配備 | `platform/ansible/media-aihist.yml` |
| DNS/Caddy | `platform/terraform/dns.yaml` の `aihist`（画面は Forward Auth、`/api/*` は SSO の外） |
| SSO | `stacks/identity/configure.py` の `configure_aihist`（`admins` だけ） |
| トークン | `platform/sops/aihist.sops.yaml` の `AIHIST_TOKEN`（`/api` だけに要る） |

## 配備

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  '.venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/media-aihist.yml'
```

名前を足したときは、`tools/tf 20-dns apply`、`identity.yml`（Authentik のアプリ）、`media-tls.yml`（media-01 の Caddy）、`edge.yml`（入口の Caddy）を流す。

版を上げるときは、aihist でタグ `v*` を push してリリースを作り、そのリリースの `SHA256SUMS` を `aihist_sha256s` に写してから配備する。

```bash
gh release download v<版> -R rurutheGeek/aihist -p SHA256SUMS -O -
```

## 会話の入れ方

| 入れ方 | やること |
| --- | --- |
| 画面の `↑` | ファイルを選んで上げる。Claude Code の `.jsonl`、Codex の `rollout-*.jsonl`、Antigravity の `.db` を中身から見分ける |
| `curl` の1行 | 各マシンで実行する。aihist を入れ、OS のタイマー（systemd のユーザータイマー・cron・launchd・タスク スケジューラ）が 10 分ごとに変わったファイルだけを送る。間隔は `AIHIST_EVERY`（`0` で1回だけ） |

```bash
curl -fsSL https://aihist.apextox.dpdns.org/api/install.sh | AIHIST_TOKEN=<トークン> sh          # Linux・WSL・Mac
$env:AIHIST_TOKEN="<トークン>"; irm https://aihist.apextox.dpdns.org/api/install.ps1 | iex      # Windows
```

画面の「送る設定」（`/setup`）に、トークンを埋めた入れる・消すコマンドとスクリプトが出る。消すときは `curl -fsSL https://aihist.apextox.dpdns.org/api/uninstall.sh | sh`（Windows は `irm …/api/uninstall.ps1 | iex`）で、実行ファイル・設定（`~/.config/aihist`）・タイマーをすべて消す。

送る前に、サーバーが配る実行ファイルと自分の sha256 を比べ、違えば入れ替える（`AIHIST_AUTO_UPDATE=0` で止める）。`aihist_version` を上げてプレイを流せば、各マシンは次に送るときに新しくなる。

スクリプトに秘密は入っていない。実行ファイルは `/api/bin/` からトークン付きで配る（media-01 の `/opt/aihist/bin`。プレイが `aihist_sha256s` と照らして置く）。WSL ではホスト名に `-wsl` が付く。

OpenCode は DB そのものを送らない（操作ログで数 GB あり、ログイン情報も入っている）。会話ごとに `session`・`message`・`part`・`project` の行をそのまま書き出したものを原本として送る。

## 元の AI へ戻す

```bash
aihist restore <会話IDの先頭>
```

サーバーとトークンは入れたときの設定ファイルから読む。画面の下の「〜で続ける」で同じコマンドをコピーできる。原本を元のツールの置き場所へ戻し、続けるコマンド（`claude --resume`・`codex resume`・`opencode --session`）を表示する。Codex と OpenCode は、消した会話を戻して続きを話せることを確かめた。Claude Code は戻したファイルが原本と同じことまで、Antigravity は未確認。

トークンは `sops -d --extract '["AIHIST_TOKEN"]' platform/sops/aihist.sops.yaml` で読む。
## バックアップ

`raw/` が原本で、`aihist.db` は原本から作り直せる。消えたときは各マシンから `push` し直せば戻る（各マシンに記録が残っている間だけ）。
