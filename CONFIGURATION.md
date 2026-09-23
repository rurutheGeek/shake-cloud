# サーバー設定と拡張

設定項目の意味や具体的な操作例は、目的別の[運用ドキュメント](docs/index.md)に分けています。このファイルは現在の構成と変更境界の一覧です。

## 現在の構成

Proxmox VE（`apextox`）の上に用途別のVMを置いています。各VMは独立したDocker Composeプロジェクト群です。Kubernetes（kubeadm + Cilium + Flux）とその上のAWX・CloudNativePG・Knativeは構築済みです（2026-09-12時点で k8s-cp-01・k8s-worker-01 は停止中）。NetBoxをAnsibleの動的インベントリとして利用しています（[接続先一覧](docs/operations/urls.md)・[配備台帳](docs/operations/handover.md)）。

| VM | 役割 |
| --- | --- |
| identity | Authentik（共通ログイン・AWS風ポータルの認証） |
| cloud-01 | クラウドAPI・管理DB・ポータル |
| services-01 | NetBox、ドキュメントサイト、Homarr、Vaultwarden、LibreSpeed、Home Assistant、CUPS、eufy-security-ws |
| media-01 | Nextcloud、Kavita、Navidrome、Picard、LocalSend受信機 |
| storage-s3 | Garage（S3互換オブジェクトストア） |
| monitor-01 | Prometheus、Alertmanager、Grafana |
| k8s-cp-01 / k8s-worker-* | Kubernetes（AWX・CloudNativePG・Knative） |
| dev-a / dev-b | 開発VM |
| game1 | ゲームサーバ（クラウド管理下） |
| router-01 | OpenWrt（家庭内ルータ。WAN=ONU、LAN=既存LAN。切替済み） |

## 設定する場所

| 対象 | 設定例 | 設定場所 |
| --- | --- | --- |
| Nextcloud | ユーザー・グループ、容量上限、共有、外部ストレージ、追加アプリ、Notesの表示既定、既存カレンダーの取り込み | `stacks/media/nextcloud/manage.py`（`setup`・`apps`・`config-notes`・`import-calendar`・`config-print`）。配備は `platform/ansible/media-nextcloud.yml`、OIDCは `stacks/media/nextcloud/configure-oidc.py` |
| Kavita | ライブラリ、OIDC、初期管理者 | `stacks/media/kavita/bootstrap.py`・`configure-oidc.py`。状態は `/srv/media-stack/storage/kavita` |
| Navidrome | スキャン間隔、トランスコード、Forward Auth | `stacks/media/navidrome/compose.yaml` の `ND_*` 環境変数。状態は `/srv/media-stack/storage/navidrome` |
| music-tools | 取込先、変換、Picard、同期 | `stacks/music-tools/compose.yaml`・`manage.py`。配備は `platform/ansible/music-tools.yml` |
| Vaultwarden | SSO、登録可否、公開URL | `stacks/vaultwarden/compose.yaml`・`manage.py`。保存された `/data/config.json` が環境変数より優先されることがある |
| Homarr | ボード、タイル、権限 | `stacks/homarr/apps.json`・`configure.py`。配備は `platform/ansible/homarr.yml` |
| LibreSpeed | 端末↔services-01の速度計測、履歴、統計パスワード | `stacks/librespeed/compose.yaml`・`manage.py`。配備は `platform/ansible/librespeed.yml` |
| Home Assistant | 家電連携、HTTP逆プロキシ、自動化 | HAのconfig（`/srv/services/home-assistant/config`）。配備は `platform/ansible/home-assistant.yml` |
| 配備先ホスト | 保存先、ポート、イメージ、HTTPS | `platform/terraform/dns.yaml`、`platform/ansible/group_vars/media.yml`、各ユニットの `.env.example`・`compose.yaml` |
| ルータ（router-01） | LAN・DHCP・DNS・MAP-E・ファイアウォール | `platform/openwrt/rootfs/etc/shakecloud/config/`（UCI の正本）。イメージは `platform/openwrt/openwrt.yaml`、VM は `platform/terraform/router.yaml`、手順は [router-01](docs/operations/router.md) |
| NetBox | 配備対象・IP・タグ | NetBox管理画面。`platform/terraform/tags.yaml` と `platform/ansible/inventory.netbox.yml` が対応の正本 |

秘密値は.gitignore対象ファイルやSOPS（`platform/sops/`）で管理し、Gitには登録しません。Ansibleはコンテナ・保存領域・初期設定を管理しますが、各アプリの管理画面設定すべてを再現する構成にはなっていません。

## 拡張の方法と境界

- 原本ディスクの増設・移動: media-01 では `LIBRARY_ROOT`（`/srv/media-stack/library`）と `platform/terraform/services/media` の宣言を変更します（データディスクは `prevent_destroy`）。
- ライブラリ分割: 技術書・漫画・家族用のディレクトリを作り、Kavitaで別ライブラリとして登録し閲覧権限を設定できます。Nextcloudの権限は他サービスへ同期されません。
- HTTPS: `platform/terraform/dns.yaml` の名前ごとに、各ホストのCaddy（`stacks/tls-proxy`）がLet's Encrypt（DNS-01）で証明書を取って中継します。アプリ自身のポートは 127.0.0.1 に閉じます。
- バックアップ: 各ユニットの `manage.py backup`（Nextcloud・Kavita・Navidrome・music-tools・Vaultwarden・LibreSpeed・Home Assistant・NetBox）と、cloud-01の管理DBの定期バックアップ（`cloud-backup.timer`）があります。別ホストへの転送は追加設定が必要です。
- 複数ホスト: 新規VMは `platform/terraform/services/<name>/` で宣言します。クラウドVMは `platform/ansible/inventory.cloud.py` でAnsibleの対象にします。サービスごとの分散にはロール分割・接続先・ネットワーク設計の追加が必要です。
- 冗長化: 現状は各サービス1インスタンスです。コンテナ数を増やすだけではHAになりません。PostgreSQLやSQLiteを含むアプリ状態は原本と分けて保持し、同じ状態ディレクトリを複数インスタンスで共有しないでください。

## PDFを追加する方法

`/srv/media-stack/library/books/作品名/作品名.pdf` としてください（media-01）。Nextcloudの `books` から作品フォルダを作ってアップロードできます。KavitaはBooksライブラリのフォルダ監視（Folder Watching）が有効で、変更を検知して取り込みます。反映されないときはKavitaのライブラリでScanを実行します。

参考: [Kavitaの配置ルール](https://wiki.kavitareader.com/guides/scanner/managefiles/)、[ライブラリ設定](https://wiki.kavitareader.com/guides/admin-settings/libraries/)、[Navidrome設定](https://www.navidrome.org/docs/usage/configuration/options/)。
