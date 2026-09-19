# W03 Nextcloud・Calendar・Tasksのmedia-01移行

更新日: 2026-09-19。これは開発計画であり、配備完了の記録ではありません。[配置・所有境界・並列作業の共通ルール](index.md)を参照してください。番号は実施順を表しません。

## 目的・現状

状態: **既存コードの移行・認証統合・実機確認**。media-01へ空のNextcloud・PostgreSQL・Redis・cronを配備し、`setup`（外部ストレージ・cron）と`apps`（calendar・tasks・text・user_oidc）まで2026-09-12に実機適用済み。2026-09-19にNotesを追加し、実機で有効を確認。同じく2026-09-19に旧Androidアプリのカレンダー（ICS 884件）を`manage.py import-calendar`でルルザギークへ取り込み、すすすへ編集可で共有。HTTPS入口（`https://nextcloud.apextox.dpdns.org`）とAuthentik OIDC（`user_oidc`）を設定済み。**既存環境からのデータ移行と既存アカウントの紐付けは未了**。

`stacks/compose.yaml` はNextcloud・PostgreSQL・Redis・cronを定義済み。`platform/ansible/deploy.yml` と `group_vars/media.yml` はCalendar・Notes・Tasks・Text・user_oidcを導入する。[既存機能](../services/nextcloud.md)と[共有権限](../operations/nextcloud-permissions.md)を移行する。

配備先: **media-01**。開発先は `stacks/media/`。既存コードを再利用し、DB・設定・ファイル・cronを同じ移行単位にする。

## 実装手順

1. 既存lockとアプリ版、DB・ファイル量、共有books/musicと私有データの対応を記録する。移行時には版更新を重ねない。共通ComposeからVaultwardenを分離する変更をW02と調整する。
2. ホストごとの保存先・UID/GIDを明示し、原本を一つの共有領域に置く。認証は[identity](../operations/identity.md)のOIDCクライアントを使う。既存アカウントを引き継ぐ場合は `users` / `admins` への紐付けを検証し、メール一致だけで別人のデータを結び付けない。 CalDAV等はブラウザーSSOとは別にアプリパスワードを検証する。
3. cron・同期・取り込みを停止し、メンテナンス状態でDB・設定・ファイルの整合バックアップを取る。隔離先に復元してアプリと共有権限を確認し、入口とクライアントを切り替える。

## 依存と並列作業

- 開発開始: なし。既存Playbook・Composeの分離とテスト用ファイルの復元から開始する。
- 配備・切替: [I02](I02-media-vm.md)のVM・データ領域、[I01](I01-resources.md)の容量確認、[N05](N05-https.md)の入口とidentity。
- 競合調整: 原本の書き込みはW06と調整する。`platform/ansible/deploy.yml`、media変数、共通Composeの変更担当を明示し、他アプリの配備を発動しない実行単位に分ける。

## 検証・完了条件

- 共有books/musicは対象者だけに見え、私有ファイルは他人へ公開されない。既存利用者のファイル所有者が変わらない。
- アップロード・ダウンロード・共有、Calendar予定とTasksの作成・更新、スマホCalDAV同期、cronの実行を確認する。
- 整合バックアップからファイル件数とDB内容を確認し、再配備・VM停止再開後に同期が復帰する。media-01停止中の同期・予定表停止を案内する。
