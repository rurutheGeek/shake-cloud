---
title: Botポータル
updated: 2026-10-04
section: 運用手順
audience: 管理者
tags:
  - ops
  - discord
---

# Botポータル

> **更新日** 2026-10-04 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: apps-01 へ配備する。`portal.apextox.dpdns.org`（Authentik forward auth）から、Discord Botの状態・ログ閲覧・再起動・`manage.py` の定型操作を行う。

将来的にはDiscord以外（systemd・HTTPヘルスなど）も同じ画面へ集約する。サービスは `services.yaml` に足す。

## 構成

| 項目 | 値 |
| --- | --- |
| 配備先 | apps-01（`192.168.10.105`）。`/opt/bot-portal`（Compose・アプリ本体・`storage/state/audit.log`） |
| 入口 | tls-proxy の Caddy。`platform/terraform/dns.yaml` の `portal`（`auth: true`）→ `127.0.0.1:8095` |
| 認証 | Authentik forward auth（`stacks/identity/configure.py` の `BOT_PORTAL`）。`Remote-User` ヘッダーが無いリクエストは401 |
| アプリ | FastAPI + Jinja2。`stacks/bot-portal/app/` |
| できること | サービス一覧（状態・稼働開始・短いSHA）、ログ（tail・タイムスタンプ付き）、再起動、`manage.py status/update/up/down/backup`、操作履歴 |
| 定義 | `stacks/bot-portal/`、`platform/ansible/bot-portal.yml`、`platform/ansible/roles/bot_portal` |

## 権限の注意

`manage.py` を実行するため、コンテナへ `/var/run/docker.sock` と `/opt`・`/srv` の対象ディレクトリを直接マウントしている。**実質的にホストと同じ権限**なので、次を崩さないこと。

- 127.0.0.1 にしか公開しない（入口は Caddy だけ）
- Authentik forward auth を外さない
- `services.yaml` の `actions` は `status` `update` `up` `down` `backup` `restart` だけにする（アプリ側でも許可表で検証）

## 配備

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/bot-portal.yml'
```

入口の追加は、`dns.yaml` の `portal` を tls-proxy へ反映し、`stacks/identity` の `configure.py` を実行して Authentik のアプリを作る。

```bash
# tls-proxy の再生成（core-01）
#   platform/ansible/edge.yml を実行
# Authentik のアプリ・プロバイダ（core-01）
#   stacks/identity/manage.py の手順で configure.py を実行
```

## 操作

画面の「再起動」は `docker restart`、「manage.py …」は各サービスの `/opt/<名前>/manage.py` を実行する。`update` `up` `down` `backup` は確認チェックが必要。実行結果は操作履歴（`/audit`）と `storage/state/audit.log` に残る。

## 残り

- systemd ユニット・HTTPヘルスなどDiscord以外のサービスの表示
- 操作履歴のローテーション
- テスト用インスタンス（`ubsleepy-test` / `circleauth-test`）の登録
