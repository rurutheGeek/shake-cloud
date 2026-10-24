---
title: AIの会話履歴（aihist）
updated: 2026-10-24
section: 運用手順
audience: 管理者
tags:
  - ops
---

# AIの会話履歴（aihist）

> **更新日** 2026-10-24 ・ **区分** 運用手順 ・ **読む人** 管理者

## 正本

| 対象 | 場所 |
| --- | --- |
| 本体 | 非公開リポジトリ [`rurutheGeek/aihist`](https://github.com/rurutheGeek/aihist)。リリースのたびに CI が `ghcr.io/ruruthegeek/aihist` のイメージを作る |
| 実体 | クラウドの service（`platform/terraform/services/aihist`）。k8s-cp-01 の `services` namespace で1台、メモリ 256MiB |
| データ | service のディスク（32GiB、`/data`）。`aihist.db` と、送られた原本 `raw/<ホスト>/<ツール>/` |
| DNS/Caddy | `platform/terraform/dns.yaml` の `aihist`。core-01 の Caddy が service の LAN アドレスへ中継する（画面は Forward Auth、`/api/*` は SSO の外） |
| SSO | `stacks/identity/configure.py` の `configure_aihist`（`admins` だけ） |
| トークン | `platform/sops/aihist.sops.yaml` の `AIHIST_TOKEN`（`/api` だけに要る）。`tools/tf` が service の秘密値として渡す |
| 移す前の写し | media-01 の `/srv/media-bulk/aihist`（2026-10-24 に移した時点のまま。更新されない） |

## 配備

```bash
tools/tf services/aihist apply
```

版を上げるときは、aihist でタグ `v*` を push してリリースを作り、`main.tf` のタグとダイジェストを両方変えて適用する。ダイジェストは次で読む。

```bash
docker buildx imagetools inspect ghcr.io/ruruthegeek/aihist:<版> --format '{{json .Manifest.Digest}}'
```

service を作り直すと LAN アドレスが変わることがある。そのときは `dns.yaml` の `upstream` を `tools/tf services/aihist output url` に合わせ、`edge.yml` を流す。作り直すとディスクも消えるので、先に中身を写す。

## 会話の入れ方

| 入れ方 | やること |
| --- | --- |
| 画面の `↑` | ファイルを選んで上げる。Claude Code の `.jsonl`、Codex の `rollout-*.jsonl`、Antigravity の `.db` を中身から見分ける |
| `curl` の1行 | 各マシンで実行する。aihist を入れ、OS のタイマー（systemd のユーザータイマー・cron・launchd・タスク スケジューラ）が1分ごとに起き、画面左下の「設定 → 送信」で決めた時刻のときだけ、変わったファイルを送る。送る AI・添付ファイル・手元の片付けは「設定 → マシン」でマシンごとに変える |

```bash
curl -fsSL https://aihist.apextox.dpdns.org/api/install.sh | AIHIST_TOKEN=<トークン> sh          # Linux・WSL・Mac
$env:AIHIST_TOKEN="<トークン>"; irm https://aihist.apextox.dpdns.org/api/install.ps1 | iex      # Windows
```

画面左下の「設定」（`/settings`）でマシン名を入れて「マシンを追加」を押すと、そのマシン用のトークン（その場でしか表示されない）と入れるコマンドが出る。使わなくなったトークンは同じ画面で削除する。`aihist.sops.yaml` の `AIHIST_TOKEN` も引き続き使える。同じ画面に容量（DB と原本、マシン・AI ごと）と言語（日本語・英語）がある。「手元の片付け」は 7 日にしてある（2026-10-16）。各マシンは送ったあと、最終更新が 7 日より前でサーバーに同じものがある会話を手元から消す（索引と OpenCode の DB は消さない）。消した会話は `aihist restore` で戻す。消すときは `curl -fsSL https://aihist.apextox.dpdns.org/api/uninstall.sh | sh`（Windows は `irm …/api/uninstall.ps1 | iex`）で、実行ファイル・設定（`~/.config/aihist`）・タイマーをすべて消す。

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

`raw/` が原本で、`aihist.db` は原本から作り直せる。service のディスクは k8s-cp-01 のデータディスクにあり、[週次の vzdump](backup.md) が HDD へ取る。各マシンは7日より古い会話を手元から消すので、それより新しい会話は各マシンから `push` し直せば戻る。

aihist だけを戻すときは、k8s-cp-01 のバックアップを別の VMID へ復元し、`/srv/k8s/local-path/` の下の `_services_<service ID>` のディレクトリを写す。k8s-cp-01 ごと戻すと AWX・database も巻き戻る。
