# 汎用RAG・Discord Botの開発入口

状態: **計画用READMEのみ（2026-09-12）**。このディレクトリに実行用Compose・管理コマンド・秘密値はまだ追加していない。今回の作成で配備は発動しない。

## 配備先・担当

配備先: **game1**。

担当計画: [A02 Ollama](../../docs/development/A02-ollama.md)、[A03 RAG](../../docs/development/A03-rag.md)、[A04 Discord Bot](../../docs/development/A04-discord-bot.md)。仕様・進捗の正本は個別計画書とし、[全体一覧](../../docs/development/index.md)から依存関係を確認する。

## 再利用するもの

[AIの配置・権限方針](../../docs/architecture/operations.md)が既存設計。汎用RAG・Botの配備実装はこのリポジトリには未収録。共用Ollamaは[`stacks/pokemon-ai/ollama/`](../pokemon-ai/ollama/README.md)に実装済み（game1実機確認は未実施）。ポケモンAIの外部コードはA01で取得確認し、共通化できる箇所だけを参照する。

## 実装時の境界

A02は共用Ollama、A03は汎用の文書・索引・検索、A04はDiscord入出力を担当する。実装時はこの配下でコンポーネント別に分け、同じ設定ファイルを並行編集しない。Botは模擬応答で開発でき、RAG実接続だけをA03後に行う。文書の閲覧権限をDiscordへ自動継承せず、許可する資料とチャンネルを制限する。game1停止中は全機能停止。

同居サービスのCompose名・ポート・永続保存先を衝突させない。共有DNS／TLS・同一state適用・VM再起動だけを調整し、コードと資料の作業は並列に進める。サービスの起動確認・認証・再配備・停止再開・データ復元は各担当計画の完了条件を使う。

VMの所有者は[サービス配置とIaC](../../docs/development/D03-service-boundaries.md)を参照する。services-01は `05-seed`、game1は既存クラウド管理のまま、新規media-01だけを[I02の宣言先](../../platform/terraform/services/media/README.md)で管理する。
