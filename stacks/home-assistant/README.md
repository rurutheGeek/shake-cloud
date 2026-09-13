# Home Assistant Containerの開発入口

状態: **H01は2026-09-12にservices-01へ配備済み（HA 2026.9.2）。ローカルオーナーの作成とAuthentik SSO（`hass-oidc-auth`）での実ログイン、Eufy統合の導入まで動作確認済み。バックアップと復元試験は未完**。Compose・`manage.py`・Ansible・テストはこのディレクトリにある。H02はSwitchBot Cloud統合を追加済み、H03は見送り、H04はライブ映像不可を実機で確定。

## 配備先・担当

配備先: **services-01**。プロジェクトは `/opt/services/home-assistant`、状態は `/srv/services/home-assistant`（`config/`）で、Composeプロジェクト名は `services-home-assistant`。127.0.0.1:8123に閉じ、入口は既存Caddyの <https://ha.apextox.dpdns.org>（[H01](../../docs/development/H01-home-assistant.md)）。

担当計画: [H01 Home Assistant](../../docs/development/H01-home-assistant.md)、[H02 SwitchBot](../../docs/development/H02-switchbot.md)、[H03 Echo](../../docs/development/H03-echo.md)、[H04 Eufy](../../docs/development/H04-eufy.md)。仕様・進捗の正本は個別計画書とし、[全体一覧](../../docs/development/index.md)から依存関係を確認する。

## 配備と管理

初回は静的inventory、以後はservices-01を含む基盤inventoryを使う。

```bash
.venv/bin/ansible-playbook -i platform/ansible/seed.ini platform/ansible/home-assistant.yml
```

- `manage.py init|lock|up|status|down|backup|restart|ensure-http-proxy|install-integration` は `stacks/identity/` と同じ形。`backup` はsudoで実行し、HAを一時停止して状態と配備ファイルを整合の取れたtarにする。
- **HTTPの逆プロキシ設定はHA 2026.9以降 `.storage/http` が正本**。YAMLの取り込みはUI承認が必要なpending（5分で自動撤回）にしかならないため、配備は `manage.py ensure-http-proxy --proxy 172.31.254.1` で `stable` に直接入れ、再起動して反映する。値はcompose.yamlで固定したゲートウェイ（`172.31.254.1`）と対。
- **認証はAuthentikのOIDC（SSO）とローカルオーナーの併用。** コアがOIDC非対応のため、`manage.py install-integration` がコミュニティ統合 [`hass-oidc-auth`](https://github.com/christiaangoossens/hass-oidc-auth)（v1.2.1）をdigest固定で `config/custom_components/auth_oidc` へ入れ、Ansibleが `configuration.yaml` の `auth_oidc` 管理ブロックを書く。client_id `home-assistant` は[identity](../identity/configure.py)が公開クライアントとして作る（秘密値なし）。**フォルダ名は `auth_oidc` 固定**: 統合が静的資産を `custom_components/auth_oidc/...` と直書きするため、別名で入れるとCSS/JSが404になる（2026-09-12に発生）。
- `manage.py install-integration` はEufy統合 `eufy_security`（v8.2.4）も入れる。実機接続は中継の[`stacks/eufy-security-ws/`](../eufy-security-ws/README.md)（H04）とHAの「統合を追加」で行う。
- `configuration.yaml` などのHAの設定はGitに置かず、`/srv/services/home-assistant/config` を正本として上書きしない（`auth_oidc` の管理ブロックだけが例外）。秘密値・トークンはHAのconfig entry側に入り、Git/ログへ出さない。

## 再利用するもの

`manage.py` は[identityの管理コード](../identity/manage.py)を設計例にし、[家電設計](../../docs/architecture/operations.md#home-devices)を機器別要件の根拠にする。既存のHAOS専用VMを前提とした設定を新設しない。

## 実装時の境界

本体構成・履歴・バックアップ復号情報と周辺サービスの設定を分ける。必要な周辺サービスは別Composeで管理し、HAOSの追加アプリ機構がある前提にしない。H02〜H04の調査・設定開発はH01配備を待たずに行う。

同居サービスのCompose名・ポート・永続保存先を衝突させない。共有DNS／TLS・同一state適用・VM再起動だけを調整し、コードと資料の作業は並列に進める。サービスの起動確認・認証・再配備・停止再開・データ復元は各担当計画の完了条件を使う。

VMの所有者は[サービス配置とIaC](../../docs/development/D03-service-boundaries.md)を参照する。services-01は `05-seed`、game1は既存クラウド管理のまま、新規media-01だけを[I02の宣言先](../../platform/terraform/services/media/README.md)で管理する。
