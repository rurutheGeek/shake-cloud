# Shake Lab Docs

本・音楽・ファイル・パスワード・家電を、家庭内LANの一つの入口から開けます。

普段の操作は[利用者向け：全サービスの使い方](services/usage.md)から始めてください。管理者向けの設定やサーバー作業は[運用ドキュメント](overview.md)から選びます。**すべての接続先は[接続先一覧](operations/urls.md)にまとめています。**

## 主なサービス（`*.apextox.dpdns.org`・家庭内LANから）

| サービス | 開く | 用途 |
| --- | --- | --- |
| Homarr | <https://homarr.apextox.dpdns.org> | サービス一覧の入口（閲覧は全員、編集は `admins`） |
| クラウド | <https://cloud.apextox.dpdns.org> | VM・S3・DB・関数のポータルとAPI |
| 共通ログイン | <https://auth.apextox.dpdns.org> | Authentik（招待・パスキー・復旧） |
| Nextcloud | <https://nextcloud.apextox.dpdns.org> | ファイル・共有・予定（Calendar）・TODO（Tasks） |
| Kavita | <https://kavita.apextox.dpdns.org> | PDF・電子書籍 |
| Navidrome | <https://navidrome.apextox.dpdns.org> | 音楽再生 |
| Vaultwarden | <https://vault.apextox.dpdns.org> | パスワード管理 |
| Home Assistant | <https://ha.apextox.dpdns.org> | 家電の状態確認・操作・自動化（[使い方](services/home-assistant.md)） |
| プリンター | <https://cups.apextox.dpdns.org> | 印刷の状況（[使い方](services/printer.md)） |
| Grafana | <https://grafana.apextox.dpdns.org> | 監視（稼働・資源・UPS） |
| AWX | <https://awx.apextox.dpdns.org> | Ansible の実行基盤（Kubernetes） |
| NetBox | <https://netbox.apextox.dpdns.org> | 台帳（IP・VM） |
| Shake Lab Docs | <https://docs.apextox.dpdns.org> | このサイト |

**これらは家庭内LANからのみ届きます。** ログインが必要なサービスは、共通ログイン（Authentik）のアカウントを使います。アカウントが無い場合は管理者に招待を依頼してください。

## 最初に使う

- ファイル: Nextcloudに保存・共有します。予定は Calendar、TODO は Tasks です（[Nextcloudの使い方（利用者向け）](services/nextcloud-guide.md)）。
- 本: Nextcloudの `books` に作品フォルダを作り、PDFを入れます。Kavitaが変更を検知して取り込みます。即時反映はKavitaのScanです。
- 音楽: Nextcloudの `music` に追加します。Navidromeが定期スキャンで取り込みます。
- パスワード: Vaultwardenの招待を受け、自分だけが知るマスターパスワードを設定します。
- 家電: Home Assistantで状態を見たり操作します（[使い方](services/home-assistant.md)）。
- 印刷: 端末から直接（AirPrint / IPP）か、Nextcloudの「…」→「印刷」を使います（[プリンター](services/printer.md)）。
- 端末からファイルを送る: LocalSendでmedia-01へ送ると、Nextcloudの `inbox` に届きます（接続先は[接続先一覧](operations/urls.md)）。

日常の操作は[全サービスの使い方](services/usage.md)、音楽の取り込み・タグ編集は[音楽の取り込み・タグ編集・BCSTM](services/music.md)にまとめています。

## 基盤と開発

- クラウド（VM・S3・DB・関数）を使う: [クラウドの使い方](services/cloud.md)・[shakecloud CLI](operations/cli.md)・[Terraform Provider](operations/terraform-provider.md)
- 新しいサービスを載せる/VMを作る: [サービスの置き場所とクラウドVMでの作り方](operations/services.md)
- 実機の状態・残りの作業: [配備台帳](operations/handover.md)（進捗の正本）
- 基盤の設計: [ホームラボ／最小プライベートクラウド構成案](architecture/index.md)・[IaCの所有境界](architecture/iac.md)
- 開発に参加する: [開発参加ガイド](onboarding.md)・[並列開発計画](development/index.md)
