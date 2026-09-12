# セルフホストVPNの開発入口

状態: **計画用READMEのみ（2026-09-12）**。このディレクトリに実行用Compose・管理コマンド・秘密値はまだ追加していない。今回の作成で配備は発動しない。

## 配備先・担当

配備先: **services-01**。

担当計画: [N01 VPN](../../docs/development/N01-vpn.md)、復旧経路は[N02 Tailscale](../../docs/development/N02-tailscale.md)。仕様・進捗の正本は個別計画書とし、[全体一覧](../../docs/development/index.md)から依存関係を確認する。

## 再利用するもの

[VPN比較](../../docs/architecture/vpn.md)と[ネットワーク設計](../../docs/architecture/network-auth.md)が既存の検討資料。VPNの配備コードは未実装。NetBirdを第一検証候補とし、製品決定・外部到達確認後にここへ構成を追加する。

## 実装時の境界

他アプリとCompose・DB／鍵・登録状態を分ける。services-01停止中もラズパイのTailscaleから復旧できる経路を維持する。既存TLS入口とのポート共存はN01・N05で確認してから配備する。

同居サービスのCompose名・ポート・永続保存先を衝突させない。共有DNS／TLS・同一state適用・VM再起動だけを調整し、コードと資料の作業は並列に進める。サービスの起動確認・認証・再配備・停止再開・データ復元は各担当計画の完了条件を使う。

VMの所有者は[サービス配置とIaC](../../docs/development/D03-service-boundaries.md)を参照する。services-01は `05-seed`、game1は既存クラウド管理のまま、新規media-01だけを[I02の宣言先](../../platform/terraform/services/media/README.md)で管理する。
