---
title: ポケモン系のPostgreSQL（pkdb）
updated: 2026-10-09
section: 運用手順
audience: 管理者
tags:
  - ops
  - database
---

# ポケモン系のPostgreSQL（pkdb）

> **更新日** 2026-10-09 ・ **区分** 運用手順 ・ **読む人** 管理者

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
| 管理画面 | <https://adminer.apextox.dpdns.org>（Adminer。**登録画面の右上「Adminer」から開ける**。入口は core-01 の Caddy、Authentik の Forward Auth で `admins` のみ。apps-01 では `127.0.0.1:8330`）。「サーバ」は `db`、ユーザ名とパスワードはDBのロール。パスワードはどのロールも旧ホストと同じ。普段は `pkdb_editor`、`postgres` は必要なときだけ |
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
| DB | `ubsleepy`（本番）、`ubsleepy_test`（テスト配備用。Bot に `UBSLEEPY_DB_NAME=ubsleepy_test` を渡す。ロールとパスワードは本番と同じ） |
| ロール | `ubsleepy_writer`（Botが読み書き）、`ubsleepy_reader`（閲覧） |
| パスワード | `platform/sops/ubsleepy.sops.yaml` の `UBSLEEPY_DB_PASSWORD` / `UBSLEEPY_DB_READER_PASSWORD` |
| 作成 | 配備時に `sql/ubsleepy.sql`（ロールとDB）と `sql/ubsleepy_tables.sql`（テーブルと権限）が流れる。どちらも冪等で、**既存ロールのパスワードは変えない** |

`ubsleepy.sql` は `CREATE DATABASE` を含むため `-- manage.py: no-transaction` を付けています（トランザクション内では実行できない）。

## アプリ用の表（`app_<アプリ名>_`）

図鑑のデータではなく、特定のアプリのために置く表は、名前を `app_<アプリ名>_` で始めます（スキーマは同じ `pokemondb`）。

| 表 | 使うアプリ | 中身 |
| --- | --- | --- |
| `app_intro_alias` | UBSLEEPY のイントロクイズ | 曲の別名（1行に1つ）。`in_work` が `work` と違う行は、再録でその作品に流れるときだけの呼び名 |
| `app_intro_appearance` | 同上 | 曲がほかに流れる作品（再録・流用） |
| `app_intro_secret` | 同上 | ふだん出題しない音源（未使用曲・古いバージョンなど） |

- 定義は `stacks/pkdb/sql/app_intro.sql`（配備のたびに流れ、冪等）。作品は略称、曲名は文字のまま持ち、**リストを直している間は正規化しません**。
- Bot は `pkdb_reader` で1分ごとに読み直すので、**直すと配備なしで本番・テストの両方に反映**されます。表が空・DBにつながらないときは、Bot のイメージに入っているCSVを使います。
- 直すのは UBSLEEPY-next の `python tools/intro_db.py`（apps-01 のコンテナの `psql` を `pkdb_editor` で使う。手順は同リポジトリの `CLAUDE.md`）。`pkdb_editor` はこの3表にだけ直接書けます。
- このために `pkdb_editor` へスキーマ `pokemondb` の `USAGE` を足しました（表の `SELECT` は元から持っていたが、スキーマに入れず使えていなかった）。

## ポケモンDBの登録画面

**<https://pkdb-entry.apextox.dpdns.org>**（Homarr の「ポケモン登録」。Authentik の `admins` のみ）。SQL を書かずに、ポケモン・わざ・特性・図鑑情報・覚えわざ・進化・作品・使用率順位を足す・直す画面です。

### できること

| 画面 | できること |
| --- | --- |
| トップ | 件数と「手をつけたいところ」（値の無い姿・図鑑情報の無いポケモン・覚えわざの無いわざなど）、最近の登録 |
| ポケモン | 番号・名前・あだ名・英語名で探し、姿ごとの最新値と作品ごとの値を一覧。登録・修正・コピー・名前と各言語名・地方図鑑番号・覚えわざ・進化 |
| わざ | 作品ごとの値を登録・修正。前の作品からまとめて写す。覚えているポケモンを一覧 |
| 特性 | 作品ごとの説明を登録・修正。前の作品からまとめて写す。持つポケモンを一覧 |
| 図鑑情報 | 分類・たかさ・おもさ・性別比・タマゴグループ・経験値タイプ・被捕獲度・努力値を1つの姿ずつ。未登録だけの絞り込み |
| 作品 | 作品グループと、作品1本（発売日つき）の追加・修正 |
| 順位 | 使用率を貼り付けて取り込み（同じ作品・シーズン・形式は置き換え）。一覧 |
| 履歴 | 誰が何をしたか。修正は直す前の値も残り、「この修正前の値を入力欄に入れる」から復元できる |

### 決まりごと

- 正規化（ID・関連行）は裏で関数が行う。新しいポケモン・姿・作品の値は、既存の行から「コピー」で下書きして保存する。
- 特性・わざ・進化方法は名前で入れる。その作品に無ければ直近の作品から写し、どこにも無ければ新しく足す（IDは自動）。
- 覚えわざは「複数行を貼り付けて追加」でまとめて入る。消す行は「削除」に印を付けて保存。別の作品からまとめて写すこともできる。
- 保存のたびに関係するマテリアライズドビューを作り直すので、クイズや検索にすぐ出る（覚えわざ・図鑑情報・順位はビューに影響しない）。
- 誰が何をしたかは `pokemondb.entry_log` に before/after 付きで残る。画面から消せるのは、わざの行・覚えわざ・進化リンク・（置き換えでの）あだ名だけ。ほかの行や生のSQLは、画面右上の「Adminer」から（同じ SSO で開きます）。
- **他作品からのコピーは内容を必ず確認する。** スキーマにある「根拠なく過去作のデータを流用しない」原則に従い、コピーは下書きとして使い、作品ごとの正しい値に直す。

仕組み:

| 部品 | 場所 |
| --- | --- |
| 画面 | `stacks/pkdb/entry/`（Python 3.13 + FastAPI。apps-01 でイメージを組み立てる。`127.0.0.1:8331`） |
| 登録の中身 | `stacks/pkdb/sql/entry*.sql` の関数（基盤とポケモン＝`entry.sql`、続きはドメインごと）。どの表へ何を入れるか・IDの採番・before/after の記録はここ |
| DBのロール | `pkdb_entry`。関数の実行と全表の閲覧だけで、表へ直接は書けない。パスワードは apps-01 の `/opt/pkdb/secrets/entry_password` にだけあり、この画面のコンテナだけが使う |

関数は SQL からも呼べます（`pkdb_editor` に実行権限あり）。AIやスクリプトから足すときも、表へ直接 `INSERT` せずこれを使います。

## データの直し

pokemondb の誤りや抜けは、手で直さず `stacks/pkdb/sql/data_fixes.sql` に足します。配備のたびに流れ、直っていれば何もしません。直したときは、マテリアライズドビューも依存の順に作り直します。

| 日付 | 内容 |
| --- | --- |
| 2026-10-04 | バタフリー：XY（`060`）でとくこうが 80 → 90 になった行が抜けていたので足した（特性の枠は BW から引き継ぎ） |
| 2026-10-04 | アルセウス：18フォームの姿の名前がすべて「アルセウスのすがた」だったので、「ほのおタイプ」の形にした |
| 2026-10-10 | 進化の表のフォーム：とくべつなイワンコ（`0744-01`）→ たそがれのすがた、ウパー（パルデアのすがた、`0194-02`）→ ドオー、ヌメラ → ヌメイル（ヒスイのすがた、`0705-01`）の行を直した・足した。進化するフォームが「無進化」になり、UBSLEEPY の種族値クイズに出ていた。あわせてマテビューを作り直し、ユキメノコ（古い計算のまま「中間進化」だった）も「最終進化」になった |

**直していないもの**（判断待ち）:

- ニョロボン（`0062`）：最新の値は正しいが、こうげき 85 → 95 が GS（`020`）の行に入っている。実際の変更は XY（`060`）で、`060` の行が無い。過去の作品の値だけが違う。
- シルヴァディ（`0773`）：フォーム `01`〜`17` に種族値・タイプの行が無い（基本の姿だけ）。
- ポッチャマ系の隠れ特性は SV（`090`）で「まけんき」→「かちき」。DBはこのとおり入っていて正しい。

## 配備

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/pkdb.yml'
```

再実行しても、管理者パスワード・データ・イメージのdigestは変わりません。登録画面（entry）はこのリポジトリのソースから組むため、ダイジェスト固定の対象外で、配備のたびに `up --build` で作り直します。

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
