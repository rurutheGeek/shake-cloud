# H01 Home Assistant Containerの導入

更新日: 2026-09-12。これは開発計画であり配備完了の記録ではありません。[配置・所有境界・並列作業の共通ルール](index.md)を参照してください。番号は実施順を表しません。

## 目的・現状

状態: **services-01へ配備済み（2026-09-12）。初回オーナー作成・バックアップ復元試験は未完**。

[家電の構成案](../architecture/operations.md#home-devices)は専用HAOSを想定していたが、採用先はservices-01上のContainer。HAOS追加アプリの管理は使わず、必要な周辺サービスは個別Composeで管理する。

配備先・開発範囲: **services-01。開発先 `stacks/home-assistant/`。本体・設定・自動化・履歴と復元手順**。

認証: HAコアはOIDC非対応のため、コミュニティ製OIDC統合 [`hass-oidc-auth`](https://github.com/christiaangoossens/hass-oidc-auth)（v1.2.1、digest固定で `custom_components/` へ配備）を追加し、Authentikの公開クライアント `home-assistant` でSSOできるようにした。**ローカルのオーナーアカウントは緊急用に残す**（`roles.user` は設けず、Authentikアプリの `users`／`admins` バインドで利用者を制限する）。

## 実装手順

1. 対象機器、LANからの到達、既存HAの有無、必要なUSB/Bluetoothを棚卸しする。導入版のContainer要件を確認して固定し、専用Compose・保存先・必要デバイスだけを構成する。
2. 初期履歴は本体の標準DBを使い、保持期間を制限する。対象IoTへ到達/検出できるネットワーク方式を実測し、HA自身の認証とLAN/VPN経路から開始する。
3. テスト用の操作・自動化で再配備を確認してからH02～H04の統合を追加できる入口を作る。個別機器の完成をHA本体の前提にしない。
4. 書き込みを止める等の整合方法で設定・履歴・自動化を別保存先へバックアップし、隔離した復元先で操作を確認する。デバイス割当と復旧用経路を手順へ残す。

## 依存と並列作業

- 開発開始: なし。デバイスなしの構成・自動化・復元試験から開始する。
- 配備・切替: [I01](I01-resources.md)の余力、services-01への必要なLAN/USB到達。[N02](N02-tailscale.md)の復旧経路を維持する。VLAN移行完了は不要。
- 競合調整: services-01のVPN・NetBox・Homarr等とポート/ネットワーク/VM再起動を調整する。H02～H04は自分の統合設定だけ変更し、共通HA設定の変更者を一人にする。

## 検証・完了条件

- HA認証、未認証拒否、テスト自動化・状態履歴、コンテナ再作成・VM停止再開後の復帰を確認する。
- 設定・履歴・自動化の復元、必要なUSBの再割当、LAN/VPNからの操作が成立する。
- services-01停止中は家電自動化も止まる旨を記録し、K11外の復旧用Tailscaleが使えることを確認する。

## 実機の結果（2026-09-12）

`stacks/home-assistant/`（Compose・`manage.py`・`.env.example`・テスト）と `platform/ansible/home-assistant.yml` を配備。プロジェクトは `/opt/services/home-assistant`、状態は `/srv/services/home-assistant/config`、イメージは `compose.lock.yaml` でdigest固定。

- `services-01` でコンテナを起動し、`127.0.0.1:8123` のHTTP応答・healthy・コンテナ再起動後の復帰を確認した。既定の履歴DBは専用保存先にある。
- LANからの入口は既存Caddyへ `ha.apextox.dpdns.org`（`upstream 127.0.0.1:8123`）を追加し、Let's Encrypt証明書でHTTPS化した（`platform/terraform/dns.yaml`・`20-dns`・`tls_proxy`）。未認証の `HTTP 302`（オンボーディング）を確認済み。
- HA 2026.9以降はHTTP設定が `.storage/http` へ移行し、YAMLの取り込みはUI承認までのpending（5分で自動撤回）にしかならない。配備は `manage.py ensure-http-proxy` で `stable` に `use_x_forwarded_for` と `trusted_proxies: 172.31.254.1`（compose.yamlで固定したゲートウェイ）を入れ、再起動で反映する。
- **SSO（2026-09-12）**: Authentikの公開OIDCクライアント `home-assistant`（`redirect_uri` は `https://ha.apextox.dpdns.org/auth/oidc/callback`、`sub_mode: user_uuid`、`users`／`admins` の両方にバインド）を `stacks/identity/configure.py` が冪等に作る。HA側は `auth_oidc` を `configuration.yaml` の管理ブロックへ書き、`hass-oidc-auth` をdigest固定で入れて再起動する。discovery 200・authorize 302まで確認済み。
- `manage.py install-integration` でEufy統合 `eufy_security`（v8.2.4、digest固定）も配備済み。Eufyの実接続は `stacks/eufy-security-ws/`（H04）の資格情報待ち。
- 未完: 初回オーナー作成（ブラウザ。SSOの実ログインはその後）、未認証拒否・テスト自動化・履歴の確認、`manage.py backup` と隔離先への復元試験。
