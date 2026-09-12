# ポケモンAIの開発入口

状態: **共有Ollamaの実装を追加（2026-09-12）**。ポケモンDB・WebUI・agent本体は外部コードとデータ待ちだが、game1で共用する推論サービスを [`ollama/README.md`](ollama/README.md) に分離した。配備は発動していない。

## 配備先・担当

配備先: **game1**。

担当計画: [A01 ポケモンAI](../../docs/development/A01-pokemon-ai.md)、推論先は[A02 Ollama](../../docs/development/A02-ollama.md)。仕様・進捗の正本は個別計画書とし、[全体一覧](../../docs/development/index.md)から依存関係を確認する。

## 再利用するもの

[ポケモンDB設計](../../docs/architecture/operations.md#pokemon-db)が外部 `pokemon-ai-lab/compose.yaml` を参照しているが、そのソースはこのリポジトリにない。取得・版と稼働状態の確認をA01で行い、既存コードを再利用する。READMEの記述だけで外部コードを検証済みとしない。

## 実装時の境界

ポケモンRDB・WebUI用DB・pgvector・WebUI状態・agent設定を含めて移行する。汎用RAGのデータ・DB権限と分ける。Ollama本体をこの構成とrag-bot双方に重複定義せず、A02の推論先を利用する。game1停止中は検索・WebUI・回答も停止する。

同居サービスのCompose名・ポート・永続保存先を衝突させない。共有DNS／TLS・同一state適用・VM再起動だけを調整し、コードと資料の作業は並列に進める。サービスの起動確認・認証・再配備・停止再開・データ復元は各担当計画の完了条件を使う。

## 実装済みの共有推論

[`ollama/compose.yaml`](ollama/compose.yaml) は game1 の `game1-ai` ネットワークに
Ollama を一つだけ起動する。ホスト側は loopback のみ、モデルは
`/srv/game1/ollama/models`、同時実行・常駐モデル数の既定値は1である。
`manage.py pull <model>` を明示しない限りモデルを取得しない。GPUイメージと
Vulkan設定は game1 のドライバ確認後に環境変数で切り替える。

VMの所有者は[サービス配置とIaC](../../docs/development/D03-service-boundaries.md)を参照する。services-01は `05-seed`、game1は既存クラウド管理のまま、新規media-01だけを[I02の宣言先](../../platform/terraform/services/media/README.md)で管理する。
