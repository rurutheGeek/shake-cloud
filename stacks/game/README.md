# ゲーム配信・Azaharの開発入口

状態: **計画用READMEのみ（2026-09-12）**。このディレクトリに実行用Compose・管理コマンド・秘密値はまだ追加していない。今回の作成で配備は発動しない。

## 配備先・担当

配備先: **game1**。

担当計画: [G01 Wolf](../../docs/development/G01-wolf.md)、[G02 Azahar](../../docs/development/G02-azahar.md)、[G03 負荷調整](../../docs/development/G03-game-ai-resources.md)。仕様・進捗の正本は個別計画書とし、[全体一覧](../../docs/development/index.md)から依存関係を確認する。

## 再利用するもの

[ゲーム設計](../../docs/architecture/gaming.md)と[配備台帳](../../docs/operations/handover.md)を参照する。game1のVMが存在することとWolf・Azaharの再配備コードが存在することを区別する。このリポジトリにWolf／Azaharの実装ファイルは未収録で、既存VMの設定取得・確認から始める。

## 実装時の境界

プロフィール別のセーブ・設定・ペアリングを分離する。G01とG02の開発は独立させ、実機の2セッションと非公開ルームの接続確認で合わせる。GPU・推論の負荷試験とVM再起動はA02・G03と調整する。既存クラウド管理のgame1を新しいTerraform stateで宣言しない。

同居サービスのCompose名・ポート・永続保存先を衝突させない。共有DNS／TLS・同一state適用・VM再起動だけを調整し、コードと資料の作業は並列に進める。サービスの起動確認・認証・再配備・停止再開・データ復元は各担当計画の完了条件を使う。

VMの所有者は[サービス配置とIaC](../../docs/development/D03-service-boundaries.md)を参照する。services-01は `05-seed`、game1は既存クラウド管理のまま、新規media-01だけを[I02の宣言先](../../platform/terraform/services/media/README.md)で管理する。
