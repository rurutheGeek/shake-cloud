---
title: ポケモン系のPostgreSQL（pkdb）
updated: 2026-10-04
section: 運用手順
audience: 管理者
tags:
  - ops
  - database
---

# ポケモン系のPostgreSQL（pkdb）

> **更新日** 2026-10-04 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: **apps-01 へ配備し、旧ホストから移行済み（2026-10-04）。** 旧ホスト（shakeserver、tailnet `100.116.167.59`、aarch64）のDBは止めずに残してあり、**利用者はまだ旧ホストのDBを見ています**。利用者は `bsquiz`（クイズのWeb、`pkdb_reader`）と `pkhack_app`（`pkhack_reader`）、shakeweb で、どれも shakeserver 上のコンテナです。Discord Bot（[UBSLEEPY](ubsleepy.md)）はDBを使いません。

## 構成

| 項目 | 値 |
| --- | --- |
| 配備先 | apps-01（`192.168.10.105`）。`/opt/pkdb`（Compose・`manage.py`・`secrets/`）、`/srv/pkdb/data`（データ）、`/srv/pkdb/backups`（日次ダンプ） |
| 接続先 | `pkdb.apextox.dpdns.org:5432`（LAN のみ。tailnet からは router-01 のサブネットルート経由） |
| 版 | PostgreSQL 15.15（`postgres:15.15-alpine`、digest固定）。旧ホストと同じ版・同じ musl |
| DB | `sleepy_pkdb`（スキーマ `pokemondb`）、`shakeweb`、`pkhack` |
| ロール | `pkdb_reader`・`pkdb_editor`・`shakeweb_reader`・`shakeweb_editor`・`pkhack_reader`・`pkhack_editor`。**パスワードは旧ホストと同じ**（ハッシュごと移した） |
| 管理者 | `postgres`。**パスワードは旧ホストと同じ**。apps-01 の `/opt/pkdb/secrets/postgres_password`（0400）にも同じ値を置いてある |
| タイムゾーン | UTC（旧ホストと同じ） |
| 管理画面 | <https://adminer.apextox.dpdns.org>（Adminer。入口は core-01 の Caddy、Authentik の Forward Auth で `admins` のみ。apps-01 では `127.0.0.1:8330`）。「サーバ」は `db`、ユーザ名とパスワードはDBのロール。パスワードはどのロールも旧ホストと同じ。普段は `pkdb_editor`、`postgres` は必要なときだけ |
| 表と列の説明 | [ポケモンDBの取扱説明書](../reference/pokemondb.md) |
| コード | `stacks/pkdb/`、`platform/ansible/roles/pkdb`、`platform/ansible/pkdb.yml`、セキュリティグループは `platform/terraform/services/apps/main.tf`、名前は `platform/terraform/dns.yaml` |

## 名前の小文字化

**`sleepy_pkdb` の表・列・制約・索引の名前は、2026-10-04 に大文字から小文字へ改名しました**（`"POKEMON_STATUS"` → `pokemon_status`）。引用符なしで書けます。データベースの `search_path` も `pokemondb, public` にしたので、スキーマ名も省けます。

- 定義は `stacks/pkdb/sql/lowercase.sql`。配備のたびに流れ、改名済みなら何もしません。ビューとマテリアライズドビューの定義は PostgreSQL が追従します。関数 `upsert_pokemon_move_learn` は本体を書き換えて作り直します（引数は同じ）。
- **旧ホストのDBは大文字のまま**です。`bsquiz` などを切り替えるときに、アプリのSQLを小文字へ直します。
- 旧ホストから取り直して復元したときも、配備（または下のコマンド）で小文字に揃います。
- 改名後は、旧ホストとの `fingerprint` の比較は表の名前が合わないので使えません。

```bash
sudo python3 /opt/pkdb/manage.py apply --database sleepy_pkdb /opt/pkdb/sql/lowercase.sql
```

## UBSLEEPYのセーブDB（ubsleepy）

Discord Bot「UBSLEEPY」のセーブデータ（おこづかい・クジびきけん・クイズ戦績）用のDBです。テーブルの定義は `stacks/pkdb/sql/ubsleepy_tables.sql` が正です。

| 項目 | 値 |
| --- | --- |
| DB | `ubsleepy` |
| ロール | `ubsleepy_writer`（Botが読み書き）、`ubsleepy_reader`（閲覧） |
| パスワード | `platform/sops/ubsleepy.sops.yaml` の `UBSLEEPY_DB_PASSWORD` / `UBSLEEPY_DB_READER_PASSWORD` |
| 作成 | 配備時に `sql/ubsleepy.sql`（ロールとDB）と `sql/ubsleepy_tables.sql`（テーブルと権限）が流れる。どちらも冪等で、**既存ロールのパスワードは変えない** |

`ubsleepy.sql` は `CREATE DATABASE` を含むため `-- manage.py: no-transaction` を付けています（トランザクション内では実行できない）。

## 配備

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/pkdb.yml'
```

再実行しても、管理者パスワード・データ・イメージのdigestは変わりません。

## 管理者としてつなぐ

```bash
ssh debian@192.168.10.105 'sudo docker exec -it pkdb-db-1 psql -U postgres -d sleepy_pkdb'
```

## バックアップと復元

`pkdb-backup.timer` が毎日 04:20（UTC）に `manage.py backup` を実行し、`/srv/pkdb/backups/<日時>/` へ `globals.sql`（ロール）と DB ごとの `<名前>.dump`（`pg_dump -Fc`）を書きます。14世代を残します。ダンプはデータと同じディスクにあり、VMごとの保全は apps-01 の週次 vzdump（[バックアップ](backup.md)）が持ちます。

```bash
sudo python3 /opt/pkdb/manage.py backup --destination /srv/pkdb/backups
sudo python3 /opt/pkdb/manage.py restore /srv/pkdb/backups/<日時>
```

`restore` は**すでにあるDBには触りません**。作り直すDBは先に `DROP DATABASE` します。ロールは、無ければ作り、あれば属性とパスワードのハッシュをダンプの内容に揃えます（`postgres` を含む）。

## 旧ホストからの移行（2026-10-04 に実施）

apps-01 は tailnet のアドレスへ直接届かないため、dev-02 からのSSH転送で旧ホストの 5432 を apps-01 の `127.0.0.1:15432` に見せて取り出しました。`pg_dump` は固定したイメージのもの（15系）を使います。新しい版の `pg_dump` で取ったアーカイブは 15 の `pg_restore` で読めません。

```bash
ssh -i ~/.ssh/id_ed25519_pve -R 127.0.0.1:15432:100.116.167.59:5432 debian@192.168.10.105
# 以下 apps-01 で
sudo PKDB_SOURCE_PASSWORD='<旧ホストのpostgresのパスワード>' \
  python3 /opt/pkdb/manage.py fetch --host 127.0.0.1 --port 15432 /srv/pkdb/import
sudo python3 /opt/pkdb/manage.py restore /srv/pkdb/import
sudo PKDB_SOURCE_PASSWORD='<同上>' \
  python3 /opt/pkdb/manage.py fingerprint --host 127.0.0.1 --port 15432 > /tmp/pkdb-source.txt
sudo python3 /opt/pkdb/manage.py fingerprint > /tmp/pkdb-target.txt
diff /tmp/pkdb-source.txt /tmp/pkdb-target.txt
sudo rm -rf /srv/pkdb/import
```

`fingerprint` は全ての表とマテリアライズドビューについて、行数と内容のダイジェストを出します。

### 照合結果

- 表47個は、行数・内容とも新旧で一致。
- マテリアライズドビュー6本のうち `MV_LANG_QUIZ` は一致。残り5本は行数が一致し、内容が違う。**旧ホスト側が古いまま**だったためで、復元時に再計算された新側が正しい。旧ホストで `MV_LATEST_POKEMON_STATUS` の定義を計算し直した結果は、新側のダイジェストと一致した。
- 違う行は4件：ライチュウの2フォーム（`0026` の `03`・`04`）の特性1が空 → `エレキメイカー`・`ノーガード`、シキジカ・メブキジカ（`0585`・`0586`）のタイプ2が `むし` → `くさ`。`MV_QUIZ_STATUS`・`MV_BSQUIZ_STATUS`・`MV_POKEMON_SHIRITORI_STATUS`・`MV_SHIRITORI_WORDS` はこのビューから作るため、連鎖して変わる。

## 残り

- `bsquiz`・`pkhack_app`・shakeweb の移行。接続先を `pkdb.apextox.dpdns.org:5432` に変える（いまは `host.docker.internal:5432`）。**切替までに旧ホストへ書き込みが入ったDBは、取り直す**（`DROP DATABASE` → `fetch` → `restore`）。移行時点で書き込みがあったのは `shakeweb` だけ（9/20以降でUPDATE 1件）。
- 旧ホストのDBの停止。全利用者を切り替えてから行い、ボリュームは消さずに残す。
