# D06 LocalSendの受信機と端末間転送資料

更新日: 2026-09-12。種別: **実装＋資料**。状態: **media-01に受信機を配備済み（2026-09-12）。端末アプリの実送受信は未確認**。

[開発計画一覧](index.md)へ戻る。番号は実施順を表しません。

## 目的・現状の根拠

常設VM不要の端末間転送（LocalSend）に加え、**media-01にヘッドレス受信機**を置き、端末から送ったファイルをNextcloudの `inbox` へ着地させる。受信機は `stacks/media/localsend/`（`ghcr.io/linychuo/localsend-hub:1.0.10`、digest固定、`network_mode: host`）。手動でURLを指定するときは `localsend.apextox.dpdns.org:53317`（`dns.yaml` の `localsend` レコード→ `192.168.10.101`）を使える。通常はアプリの自動検出（`media-01`）で足りる。

LocalSendは本来サーバーを持たないため、採用したのは非公式の受信機。PIN未対応・証明書fingerprintが再起動で変わる等のリスクは `stacks/media/localsend/README.md` に明記した。

## 変更範囲

- `stacks/media/localsend/`（Compose・lock・manage.py・README）と `platform/ansible/media-localsend.yml`。SGは `platform/terraform/services/media/main.tf` がTCP 53317をLANへ開ける。
- Nextcloudは `stacks/media/nextcloud/` が `${LIBRARY_ROOT}/inbox` を外部ストレージ `/inbox` として登録する。
- 利用者向けの案内は端末アプリの導線（同一LANでの検出条件、遠隔はNextcloudへ）を[全サービスの使い方](../services/usage.md)に追加する。

## 依存関係・並列作業

- 開始: なし。**配備済み**（media-01）。[N03](N03-vlan.md)の切替後はネットワーク案内のみ更新する。
- 共有変更: 利用者向け全サービス案内はW担当・D07と段落を調整する。

## 検証・完了条件

- 受信機はmedia-01でhealthy・`/api/localsend/v2/info` が `media-01` を返し、LANから53317へ到達できる（実測済み）。
- 公式アプリからの初回fingerprint信頼と実送受信、Nextcloud `inbox` への着地は**未確認**。端末2台の送受信結果を取得した場合だけ日付付きで追記する。
- 文書・リンク・公開対象検証の通過。実施していない実機確認を完了根拠へ追加しない。

共通の確認は `python3 -m mkdocs build --strict`、内部リンクの実在確認、`python3 tools/check-publication.py`。
