---
title: UBSLEEPY 本番切替の手順（実施済み）
updated: 2026-10-05
section: 運用手順
audience: 管理者
tags:
  - ops
  - discord
---

# UBSLEEPY 本番切替の手順（実施済み）

> **更新日** 2026-10-05 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: 2026-10-05 に実施済み。以下は実際に行った手順と戻し方の記録です。日々の操作は [Discord Bot（UBSLEEPY）](ubsleepy.md) を参照。

## 切替でやったこと（2026-10-05）

1. 旧Botの停止と自動更新の停止
   ```bash
   sudo bash -c 'cd /opt/ubsleepy && python3 manage.py down'
   sudo systemctl disable --now ubsleepy-update.timer
   ```
2. バックアップ
   - スタック一式: `/opt/ubsleepy` → `/opt/ubsleepy.bak-20261005`
   - `/srv/ubsleepy/state/save/report.csv` と `state/config.json` のコピー
   - DB: `pg_dump`（`pkdb-db-1`）→ `/srv/ubsleepy/state/save/ubsleepy-20261005.dump`
3. `/opt/ubsleepy` をイメージ固定スタックへ変換
   - `stacks/ubsleepy/`（`name: ubsleepy`・`compose.lock.yaml` はイメージのdigest）
   - `secrets/` に `pkdb_password`・`ubsleepy_db_password` を追加（`discord_token` は既存）
4. 最新CSVをDBへ取り込み（使い捨てコンテナ。初回接続でスキーマ移行も実行）
   ```bash
   sudo docker run --rm \
     -e UBSLEEPY_DB_PASSWORD=... \
     -v /srv/ubsleepy/state/save:/app/save \
     ghcr.io/ruruthegeek/ubsleepy-next@sha256:... \
     python -m bot_module.save save/report.csv
   ```
   結果: 552値・46人を取り込み。以降セーブデータは**全サーバー共通**（固定スコープ）
5. 起動して確認
   ```bash
   sudo bash -c 'cd /opt/ubsleepy && python3 manage.py up'
   sudo docker logs --tail 50 ubsleepy-bot-1
   ```
   ログで「pkdbから図鑑を読み込みました」「本日の時報は投稿済みでした」「コマンドを登録しました」を確認
6. 設定はDiscordから（`/channel` `/role`）。`config.json` の `GUILD_DICT` は既定値で、手編集は不要

## 戻し方

移行後は旧コードのSQL（guild_idなし）が失敗するため、**旧Botへ戻すときはDBもdumpから戻します**。

```bash
sudo bash -c 'cd /opt/ubsleepy && python3 manage.py down'
sudo docker exec -i pkdb-db-1 pg_restore -U ubsleepy_writer -d ubsleepy --clean --if-exists \
  < /srv/ubsleepy/state/save/ubsleepy-20261005.dump   # PGPASSWORDはsecretsから
sudo mv /opt/ubsleepy /opt/ubsleepy.image-stack
sudo cp -a /opt/ubsleepy.bak-20261005 /opt/ubsleepy
sudo bash -c 'cd /opt/ubsleepy && python3 manage.py up'
```

- 旧スタック: `/opt/ubsleepy.bak-20261005`
- CSV: `/srv/ubsleepy/state/save/report.csv.bak-20261005`
- DB: `/srv/ubsleepy/state/save/ubsleepy-20261005.dump`
- 切替後の成績（DBに書かれた分）は旧Botには戻りません

## 参考（当時の注意）

- 丸めが疑われるIDは自動修正しない。2026-10-04 時点の一覧:
  `352333140431339520`（HDD4649）・`773862144063569920`（cylinder）・`392235383561388032`（bouchi）・`504581995288854528`（RIKI）
- pkdb側の要修正データ（2026-10-04 時点）: バタフリーのとくこう（80→90）、ポッチャマ系の隠れ特性（かちき→まけんき）、アルセウスのフォーム名（01〜17が同じ）
