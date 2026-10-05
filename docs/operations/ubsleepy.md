---
title: Discord Bot（UBSLEEPY）
updated: 2026-10-04
section: 運用手順
audience: 管理者
tags:
  - ops
  - discord
---

# Discord Bot（UBSLEEPY）

> **更新日** 2026-10-04 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: **apps-01 で稼働中（2026-10-04 に旧ホスト shakeserver から移行）。** 改修なしで移し、Bot は今までどおりCSVで動きます（PostgreSQL は使いません）。旧ホストの `ubsleepy_bot` は停止したまま `/opt/ubsleepy` ごと残してあります。

## 構成

| 項目 | 値 |
| --- | --- |
| 配備先 | apps-01（`192.168.10.105`）。`/opt/ubsleepy`（Compose・`manage.py`・`secrets/`） |
| コード | `/srv/ubsleepy/source`。公開リポジトリ [rurutheGeek/UBSLEEPY](https://github.com/rurutheGeek/UBSLEEPY) の `main` の checkout |
| セーブデータ | `/srv/ubsleepy/state`。`save/`・`log/`・`config.json`・`resource/pokemon_senryu.csv`・`resource/image/`。**Git の外**に置き、コンテナ内でコードの上へ重ねる |
| イメージ | `python:3.13`（digest固定。旧ホストと同じdigest）。起動時に `setup/requirements.txt` を入れて `python main.py` |
| トークン | `platform/sops/ubsleepy.sops.yaml` の `DISCORD_TOKEN` → apps-01 の `/opt/ubsleepy/secrets/discord_token`（0400） |
| 通信 | Discord へ出ていくだけ。受けるポートは無い |
| 定義 | `stacks/ubsleepy/`、`platform/ansible/roles/ubsleepy`、`platform/ansible/ubsleepy.yml` |

## コードの更新（自動）

`ubsleepy-update.timer` が5分おきに `manage.py update` を実行します。`main` に新しいコミットがあれば checkout を更新し、Bot を作り直します（依存の入れ直しで1〜2分止まる）。変化が無ければ何もしません。**UBSLEEPY の `main` へマージすれば配備されます。** セーブデータは `state/` から重ねているので、更新では触れません。

```bash
sudo systemctl start ubsleepy-update.service   # すぐ反映したいとき
sudo journalctl -u ubsleepy-update.service -n 20
```

Bot が書くファイルを増やしたときは、`stacks/ubsleepy/compose.yaml` の `volumes` と `manage.py` の `STATE_DIRECTORIES`・`STATE_FILES` に足します。足さないと、そのファイルは checkout の中に書かれ、バックアップに入りません。`save/` と `log/` の下なら足す必要はありません。

## 配備と操作

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/ubsleepy.yml'
```

```bash
sudo python3 /opt/ubsleepy/manage.py status
sudo docker logs --tail 50 ubsleepy-bot-1
sudo python3 /opt/ubsleepy/manage.py down      # 止める
sudo python3 /opt/ubsleepy/manage.py up        # 起動（セーブデータが無ければ起動しない）
```

## バックアップ

`ubsleepy-backup.timer` が毎日 19:10（UTC）にセーブデータ一式を `/srv/ubsleepy/backups/<日時>.tar.gz` へ固めます（14世代）。データと同じディスクにあり、VMごとの保全は apps-01 の週次 vzdump（[バックアップ](backup.md)）が持ちます。旧ホストにあった R2 への日次バックアップは引き継いでいません。

戻すときは、Bot を止めて `/srv/ubsleepy/state` を退避してから取り込みます。`import` はセーブデータが1つでもあると書き込みません。

```bash
sudo python3 /opt/ubsleepy/manage.py down
sudo mv /srv/ubsleepy/state /srv/ubsleepy/state.old
sudo python3 /opt/ubsleepy/manage.py init
sudo python3 /opt/ubsleepy/manage.py import /srv/ubsleepy/backups/<日時>.tar.gz
sudo python3 /opt/ubsleepy/manage.py up
```

## テスト配備（UBSLEEPY-next）

再開発版（[rurutheGeek/UBSLEEPY-next](https://github.com/rurutheGeek/UBSLEEPY-next)、非公開）を、本番と同じ apps-01 で別プロジェクト・別ディレクトリで動かします。テストトークン（`TEST_DISCORD_TOKEN`）と debug モード、テスト用DB（`ubsleepy_test`）を使い、**本番の `/srv/ubsleepy/state` には触りません**（state は写し）。

| 項目 | 値 |
| --- | --- |
| 定義 | `stacks/ubsleepy-next/`（`compose.yaml`・`compose.test.yaml`・`manage.py`） |
| 配備 | `platform/ansible/ubsleepy-next.yml`（ロール `platform/ansible/roles/ubsleepy-next`） |
| 配備先 | `/opt/ubsleepy-next`、`/srv/ubsleepy-next`（`state`） |
| プロジェクト名 | `ubsleepy-next` |
| イメージ | GitHub Actions が main のマージ時に GHCR へ出す `ghcr.io/ruruthegeek/ubsleepy-next:<コミットID>` を、`compose.lock.yaml` の digest で固定。**apps-01 ではビルドしない** |
| 秘密 | `secrets/discord_token`（テストトークン）、`pkdb_password`、`ubsleepy_db_password` |

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/ubsleepy-next.yml'
```

イメージを更新するときは、GitHub Actions が出した新しいコミットの digest へ `stacks/ubsleepy-next/compose.lock.yaml` を書き換えて再実行します。状態の確認は `sudo python3 /opt/ubsleepy-next/manage.py status`（`digest` も可）です。

本番への切替と戻し方は[UBSLEEPY 本番切替の手順](ubsleepy-next-switch.md)にあります（実施は別途相談）。

## 旧ホストからの移行（2026-10-04 に実施）

同じトークンのBotは2つ同時に動かせないため、並行稼働はしていません。停止から起動までは約70秒でした。

1. apps-01 へ配備（セーブデータが無いので Bot は起動しない）。使い捨てコンテナで依存の導入と読み込みを確認。
2. shakeserver で `docker compose stop`（`/opt/ubsleepy`）。`ubsleepy-backup.timer` を無効化（止めないと「Botが停止」の通知を毎日Discordへ送る）。
3. `save log config.json resource/pokemon_senryu.csv resource/image` を tar で取り出し、apps-01 で `manage.py import`。
4. 旧ホストの `sha256sum` と `manage.py digest` を比べ、**27ファイルすべて一致**。
5. Playbook を再実行して起動。Discord のゲートウェイへの接続と、`state/save/output_cache.txt` への書き込みを確認。

旧ホストの R2 バックアップは `log/bqlog.csv` と `resource/image/` を含んでいませんでした。apps-01 のバックアップは両方を含みます。

## 残り

- [UBSLEEPY#74](https://github.com/rurutheGeek/UBSLEEPY/pull/74)：`main` へのpushで shake-infra の CD を呼ぶ `deploy.yml` を削除する。**マージするまでは、UBSLEEPY の `main` へpushすると shakeserver でもBotが起動して二重になる。**
- [shake-infra#25](https://github.com/rurutheGeek/shake-infra/pull/25)：`site.yml` と CD から Bot を外す。
- Discord 上でのコマンドの動作確認（接続までしか確認していない）。
- shakeserver の `/opt/ubsleepy` の削除は、数日使って問題が無いと分かってから。
