---
title: Discord Bot（UBSLEEPY）
updated: 2026-10-05
section: 運用手順
audience: 管理者
tags:
  - ops
  - discord
---

# Discord Bot（UBSLEEPY）

> **更新日** 2026-10-05 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: apps-01 で稼働中。2026-10-05 に UBSLEEPY-next（イメージ固定・セーブDB）へ切替済み。旧ホスト shakeserver の `/opt/ubsleepy` は停止したまま残っています。

## 構成（本番とテスト）

| 項目 | 本番 | テスト |
| --- | --- | --- |
| サーバー | apps-01（`192.168.10.105`） | 同左 |
| Bot | おねむなbot【研修中】 | ねてばかりだったBot（debugモード） |
| プロジェクト名 | `ubsleepy` | `ubsleepy-next` |
| 配備先 | `/opt/ubsleepy`・`/srv/ubsleepy` | `/opt/ubsleepy-next`・`/srv/ubsleepy-next` |
| コンテナ | `ubsleepy-bot-1` | `ubsleepy-next-bot-1` |
| トークン | `DISCORD_TOKEN` | `TEST_DISCORD_TOKEN` |
| DB | `ubsleepy` | `ubsleepy_test` |
| 定義 | `stacks/ubsleepy/` | `stacks/ubsleepy-next/` |
| Ansible | `platform/ansible/ubsleepy.yml` | `platform/ansible/ubsleepy-next.yml` |

- コードは [rurutheGeek/UBSLEEPY-next](https://github.com/rurutheGeek/UBSLEEPY-next)。旧 `rurutheGeek/UBSLEEPY` はもう使いません
- イメージは GitHub Actions が main のマージ時に GHCR へ出し、`compose.lock.yaml` の digest で固定します。**apps-01 ではビルドしません**
- 通信は Discord へ出ていくだけ。受けるポートはありません

## 必要なファイル

`/opt/<プロジェクト>/`
- `compose.yaml`・`compose.lock.yaml`（テストは `compose.test.yaml` も）
- `manage.py`（操作コマンド）
- `.env`（宣言値のみ。`STORAGE_ROOT`、テストは `UBSLEEPY_TEST=true`）
- `secrets/discord_token`・`secrets/pkdb_password`・`secrets/ubsleepy_db_password`（root 0400）

`/srv/<プロジェクト>/state/`
- `config.json`（全体設定とギルドの既定値。設定の実体はDB）
- `save/`・`log/`・`resource/pokemon_senryu.csv`・`resource/image/`

秘密の原本は `platform/sops/ubsleepy.sops.yaml`（`DISCORD_TOKEN` / `TEST_DISCORD_TOKEN` / `PKDB_PASSWORD` / `UBSLEEPY_DB_PASSWORD`）。

## 操作（停止・起動・確認）

```bash
# 状態
sudo python3 /opt/ubsleepy/manage.py status
sudo docker logs --tail 50 ubsleepy-bot-1

# 停止 / 起動 / 再起動
sudo python3 /opt/ubsleepy/manage.py down
sudo python3 /opt/ubsleepy/manage.py up            # イメージをpullして起動
sudo docker restart ubsleepy-bot-1                 # 設定ファイルを読み直すとき

# バックアップを手動で取る
sudo python3 /opt/ubsleepy/manage.py backup \
  --destination /srv/ubsleepy/backups --keep 14
```

テストも同じ（`/opt/ubsleepy-next`・`ubsleepy-next-bot-1`）。テストを止めておくときは `cd /opt/ubsleepy-next && sudo python3 manage.py down`。

## 設定の変更（Discordから）

- `/channel`: クイズ回答の受付・日替わり投稿・ログのチャンネル
- `/role`: おかねもちロール（IDくじで1位になった人に付く）
- 設定は**DBに保存**され、再起動後も残ります。`config.json` の `GUILD_DICT` は既定値なので、**手で編集しなくてよい**
- ギルドを追加・削除するときも config の編集は不要（未登録ギルドは既定0＝機能OFF。`/channel` で設定したギルドだけ日替わり等が動く）

## コードの更新

1. UBSLEEPY-next にPRをマージ → GitHub Actions が `ghcr.io/ruruthegeek/ubsleepy-next:<コミットID>` をビルド
2. `stacks/ubsleepy(-next)/compose.lock.yaml` の digest を新しいビルドのものへ更新（shake-cloud のPR）
3. apps-01 の `/opt/ubsleepy(-next)/compose.lock.yaml` を同じ内容にして `manage.py up`

```bash
sudo docker pull ghcr.io/ruruthegeek/ubsleepy-next:<コミットID>
sudo docker inspect --format='{{index .RepoDigests 0}}' \
  ghcr.io/ruruthegeek/ubsleepy-next:<コミットID>     # 新しい digest を確認
```

## バックアップと復元

- `ubsleepy-backup.timer` が毎日 19:10（UTC）に state を `/srv/ubsleepy/backups/<日時>.tar.gz` へ固めます（14世代）
- DBは別途 `pg_dump`（`pkdb-db-1` は apps-01 上のコンテナ）:
  ```bash
  sudo docker exec -e PGPASSWORD="$(sudo cat /opt/ubsleepy/secrets/ubsleepy_db_password)" \
    pkdb-db-1 pg_dump -U ubsleepy_writer -d ubsleepy -Fc > /srv/ubsleepy/state/save/ubsleepy-<日付>.dump
  ```
- 戻すときは Bot を止めて state を退避し、バックアップを展開するか `manage.py init` からやり直します

## データ

- セーブデータ（おこづかい・クジびきけん・クイズ戦績）は `ubsleepy` DB。**全サーバー共通**（どのサーバーで使っても同じ残高・戦績）
- 図鑑データは pkdb（PostgreSQL）。設定が無ければCSVへフォールバック
- 設定（チャンネル・ロール）は `guild_setting` テーブル（ギルドごと）

## これまでの経緯

- 2026-10-04: 旧ホスト shakeserver から apps-01 へ移行（CSVのまま・自動更新あり）
- 2026-10-05: UBSLEEPY-next（イメージ固定・セーブDB・多サーバー対応）へ切替。手順と戻し方は[本番切替の手順](ubsleepy-next-switch.md)
