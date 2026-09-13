# Shake Lab Docs

本・音楽・ファイル・パスワード・予定・TODOを、一つの入口から開けます。

普段の操作は[利用者向け：全サービスの使い方](services/usage.md)から始めてください。管理者向けの設定やサーバー作業は、目次の[管理者向け]から選びます。**すべての接続先は[接続先一覧](operations/urls.md)にまとめています。**

## 新しい基盤（`*.apextox.dpdns.org`・LAN 内）

| サービス | 開く | 用途 |
| --- | --- | --- |
| Homarr | <https://homarr.apextox.dpdns.org> | サービス一覧の入口（閲覧は全員、編集は管理者） |
| Vaultwarden | <https://vault.apextox.dpdns.org> | パスワード管理 |
| プリンター | <https://cups.apextox.dpdns.org> | 印刷の状況（印刷自体はAirPrintかIPP） |
| Home Assistant | <https://ha.apextox.dpdns.org> | 家電の状態確認・操作・自動化（[使い方](services/home-assistant.md)） |
| ゲームポータル | <https://play.apextox.dpdns.org> | ゲーム配信の入口 |
| クラウド | <https://cloud.apextox.dpdns.org> | VM・S3・DB・関数のポータル |
| 共通ログイン | <https://auth.apextox.dpdns.org> | Authentik（招待・パスキー・復旧） |
| AWX | <https://awx.apextox.dpdns.org> | Ansible の実行基盤 |
| NetBox | <https://netbox.apextox.dpdns.org> | 台帳（IP・VM） |
| ドキュメント | <https://docs.apextox.dpdns.org> | このサイト |

**これらは家庭内 LAN からのみ届きます。** メディア系（Nextcloud・Kavita・Navidrome・
MeTube）は media-01 へ移行中で、新しい入口（`*.apextox.dpdns.org`・新しい共通ログイン）と、
下の旧メディアスタック（SSH トンネル経由・別の Authentik）が併存しています。
**いま使う入口は[接続先一覧](operations/urls.md)で確認してください。**

## 旧メディアスタック（SSH トンネル）

| サービス | 開く | 用途 |
| --- | --- | --- |
| Nextcloud | [ファイル](https://nextcloud.localhost:8443) | ファイルと共有 |
| Calendar | Nextcloud内 | 予定・共有カレンダー |
| Tasks | Nextcloud内 | 個人・共有タスク |
| Kavita | [書籍](https://kavita.localhost:5443) | PDF・電子書籍 |
| Navidrome | [音楽](http://localhost:4533) | 音楽再生 |
| MeTube | [音声取り込み](http://localhost:8081) | URLからMP3を音楽フォルダへ |
| お気に入りの曲 | [曲のハート一覧](http://localhost:4533/app/#/song?filter=%7B%22starred%22%3Atrue%7D) | アルバムのFavouritesとは別 |
| Vaultwarden | [保管庫](https://vault.localhost:8243) | パスワード管理 |
| Authentik | ログイン時に表示 | 共通ログイン。アカウント管理は管理者向け |

これらはSSHトンネル接続時のURLです。接続できない場合は管理者へ連絡してください。[接続手順](operations/hub.md)は管理者向けです。

## 最初に使う

- 本: Nextcloudのbooks内に作品フォルダを作り、その中へPDFを置きます。Kavitaへの自動反映は約10分、即時反映はScanです。
- 音楽: Nextcloudのmusicへ追加します。Navidromeは定期スキャンで取り込みます。
- 予定: NextcloudのCalendarでカレンダーを作り、必要な相手に共有します。
- TODO: Tasksでリストを作り、タスクを追加します。
- 家電: Home Assistant（<https://ha.apextox.dpdns.org>）で状態を見たり操作します。詳細は[Home Assistantと家電の使い方](services/home-assistant.md)。
- パスワード: Vaultwardenの招待を受け、自分だけが知るマスターパスワードで登録します。

[音楽の取り込み・タグ編集・BCSTM](services/music.md)も参照してください。日常の操作は[全サービスの使い方](services/usage.md)にまとめています。

## 将来の構成案

[ホームラボ／最小プライベートクラウド構成案](architecture/index.md)では、Proxmox・常用Kubernetes・VM／サーバレス／S3／DBの提供、2人用ゲーム、VPNと公開Web、認証、Git管理を整理しています。稼働中サービスの操作手順とは別の設計資料です。

機能ごとの開発・移行・資料修正は[並列開発計画](development/index.md)から選べます。VMの配置計画と実機の状態は区別して記録しています。

開発へ参加する場合は[開発参加ガイド](onboarding.md)を先に読んでください。
