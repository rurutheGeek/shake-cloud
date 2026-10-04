---
title: サークル認証Bot（CIRCLEAUTH）
updated: 2026-10-04
section: 運用手順
audience: 管理者
tags:
  - ops
  - discord
---

# サークル認証Bot（CIRCLEAUTH）

> **更新日** 2026-10-04 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: **apps-01 へ配備する準備まで完了。** トークンは新規Discordアプリ（CIRCLEAUTH）で、SOPSに格納済み。名簿・認証ログ・通話データをUBSLEEPYのstateから取り込んで起動する。

UBSLEEPY（公開・ポケモン機能）とは別のDiscordアプリ・別トークンで動かし、UBSLEEPYが落ちても入室と認証は止まらないようにする。

## 担当する機能

- 学籍番号モーダル、ロール付与、入室時の案内
- 名簿（`save/pogakuin_list.csv`）と認証ログ（`log/auth_log.csv`）
- 通話通知（`CallPost`、`/calltitle`、`/invite`）

図鑑・クイズ・日替わり投稿・おこづかいはUBSLEEPY側にある。

## 構成

| 項目 | 値 |
| --- | --- |
| 配備先 | apps-01（`192.168.10.105`）。`/opt/circleauth`（Compose・`manage.py`・`secrets/`） |
| コード | `/srv/circleauth/source`。非公開リポジトリ [rurutheGeek/CIRCLEAUTH](https://github.com/rurutheGeek/CIRCLEAUTH) の `main` の checkout |
| セーブデータ | `/srv/circleauth/state`。`save/`・`log/`・`config.json`・`resource/image/`。**Git の外**に置き、コンテナ内でコードの上へ重ねる |
| イメージ | `python:3.13`（digest固定）。起動時に `setup/requirements.txt` を入れて `python main.py` |
| トークン | `platform/sops/circleauth.sops.yaml` の `DISCORD_TOKEN` → apps-01 の `/opt/circleauth/secrets/discord_token`（0400） |
| 取得用鍵 | 同SOPSの `DEPLOY_KEY`（読み取り専用deploy key）→ `/opt/circleauth/secrets/deploy_key`（0400）。`known_hosts` も同ディレクトリ |
| 通信 | Discord へ出ていくだけ。受けるポートは無い |
| 定義 | `stacks/circleauth/`、`platform/ansible/roles/circleauth`、`platform/ansible/circleauth.yml` |

## Discord側の設定

- Developer Portal → Applications → CIRCLEAUTH → Bot → **SERVER MEMBERS INTENT** をON
  （入室検知に必要。presences / message content は不要）
- 招待URL: scopes `bot` + `applications.commands`、権限は Manage Roles・View Channels・Send Messages・Read Message History・Embed Links・Attach Files
- Botのロールは付与対象（`UNKNOWN_ROLE_ID`）より上に置く

## データの移行

UBSLEEPYのstateから、認証・通話に必要なファイルだけをtarにして `manage.py import` で運ぶ。**移行中は旧UBSLEEPYの認証・通話を止めてから**行う（両方が動くと入室案内と通話通知が二重になる）。

```bash
# apps-01 で
sudo tar -C /srv/ubsleepy/state -czf /tmp/circleauth-state.tar.gz \
  config.json save/pogakuin_list.csv save/call_cache.csv log resource/image
sudo python3 /opt/circleauth/manage.py import /tmp/circleauth-state.tar.gz
```

`log/auth_log.csv` と `log/call_log.csv` が無い場合（移行後に記録が無い場合）は、そのまま空で始まる。

## コードの更新（自動）

`circleauth-update.timer` が5分おきに `manage.py update` を実行します。`main` に新しいコミットがあれば checkout を更新し、Bot を作り直します。**CIRCLEAUTH の `main` へマージすれば配備されます。** 非公開リポジトリなので、取得には読み取り専用deploy key（`secrets/deploy_key`）を使います。

```bash
sudo systemctl start circleauth-update.service   # すぐ反映したいとき
sudo journalctl -u circleauth-update.service -n 20
```

## 配備と操作

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/circleauth.yml'
```

```bash
sudo python3 /opt/circleauth/manage.py status
sudo docker logs --tail 50 circleauth-bot-1
sudo python3 /opt/circleauth/manage.py down      # 止める
sudo python3 /opt/circleauth/manage.py up        # 起動（セーブデータが無ければ起動しない）
```

## バックアップ

`circleauth-backup.timer` が毎日 19:20（UTC）に名簿・認証ログ・通話データを `/srv/circleauth/backups/<日時>.tar.gz` へ固めます（14世代）。戻すときは `manage.py down` → state を退避 → `init` → `import` → `up` の順です（[UBSLEEPY](ubsleepy.md) と同じ）。

## 残り

- Server Members Intent の有効化と、サーバーへの招待
- 初回配備と、UBSLEEPYからのデータ移行（上記）
- UBSLEEPY側の認証・通話の停止（UBSLEEPY-next の配備）と同時に行う
