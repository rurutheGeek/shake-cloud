# RomMの開発入口

状態: **独立Composeを実装（2026-09-12）**。game1への配備はまだ発動していない。

## 配備先・担当

配備先: **game1**。RomMはゲームVMのライブラリ管理で、メディア（音楽・本）の移行ではない。

担当計画: [W07 RomM](../../docs/development/W07-romm.md)。仕様・進捗の正本は個別計画書とし、[全体一覧](../../docs/development/index.md)から依存関係を確認する。

## 再利用するもの

[配置設計](../../docs/architecture/operations.md)と[ゲーム設計](../../docs/architecture/gaming.md)に要件がある。RomMのCompose・`manage.py`はこのディレクトリに実装済み（下の「実装済みの構成」）。game1への配備はまだ発動していない。[identity/manage.py](../identity/manage.py)は管理手順の設計例として参照できる。

## 実装時の境界

ROM原本とアプリDB・メタデータを分け、game1内の保存先を参照する。エミュレータ起動・通信連携はG01/G02の担当とする。原本の管理機能とゲーム起動連携を一括の完了条件にしない。ゲーム中の大量走査を避け、ゲーム・AIとディスク・負荷を調整する。

同居サービスのCompose名・ポート・永続保存先を衝突させない。共有DNS／TLS・同一state適用・VM再起動だけを調整し、コードと資料の作業は並列に進める。サービスの起動確認・認証・再配備・停止再開・データ復元は各担当計画の完了条件を使う。

## 実装済みの構成

[`compose.yaml`](compose.yaml) と `manage.py` は RomM と専用 MariaDB を
`game1-romm` プロジェクトで管理する。ROM原本は `ROM_LIBRARY_ROOT` から
`/romm/library:ro` として読み取り専用で渡し、DB・Redis状態・資産・リソースは
`STORAGE_ROOT` 配下へ分離する。秘密値は `secrets/` に生成し、`.env` やComposeへ
書き込まない。イメージのダイジェスト固定、冷間バックアップ、停止・再開は
`manage.py` の明示操作で行う。

VMの所有者は[サービス配置とIaC](../../docs/development/D03-service-boundaries.md)を参照する。services-01は `05-seed`、game1は既存クラウド管理のまま、新規media-01だけを[I02の宣言先](../../platform/terraform/services/media/README.md)で管理する。
