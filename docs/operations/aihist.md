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

版を上げるときは、aihist でタグ `v*` を push してリリースを作り、`aihist-linux-amd64` の sha256 を `aihist_sha256` に書いてから配備する。

```bash
gh release download v<版> -R rurutheGeek/aihist -p SHA256SUMS -O - | grep linux-amd64
```

## 会話の入れ方

| 入れ方 | やること |
| --- | --- |
| 画面の `↑` | ファイルを選んで上げる。Claude Code の `.jsonl`、Codex の `rollout-*.jsonl`、Antigravity の `.db` を中身から見分ける |
| `aihist push` | 各マシンで実行する。前回から変わったファイルだけを送る。`-every 10m` で送り続ける |

```bash
AIHIST_TOKEN=<トークン> aihist push -server https://aihist.apextox.dpdns.org
```

トークンは `sops -d --extract '["AIHIST_TOKEN"]' platform/sops/aihist.sops.yaml` で読む。Windows 用の `aihist-windows-amd64.exe` も同じリリースにある。

## バックアップ

`raw/` が原本で、`aihist.db` は原本から作り直せる。消えたときは各マシンから `push` し直せば戻る（各マシンに記録が残っている間だけ）。
