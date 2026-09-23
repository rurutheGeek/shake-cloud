# W01 Homarrのservices-01移行

更新日: 2026-09-12。これは開発計画であり、配備完了の記録ではありません。[配置・所有境界・並列作業の共通ルール](index.md)を参照してください。番号は実施順を表しません。

## 目的・現状

状態: **services-01へ配備済み（`https://homarr.apextox.dpdns.org`、identityのOIDC、ボード反映済み）。残りはブラウザでのSSOログイン・権限・再起動後の保持確認**。

`stacks/homarr/compose.yaml` にHomarr、永続 `/appdata`、暗号鍵、OIDCの定義がある。`stacks/homarr/configure.py` と `apps.json` がリンクの管理元である。[利用手順](../services/homarr.md)のボード・管理者権限を維持する。

**既存環境の実装・データは流用せず、`stacks/homarr/` に新規構築する**（2026-09-12の利用者判断）。他サービスとの同居や既存の資料は持ち込まない。実装済みの内容: Homarr単独Compose（ダイジェスト固定）、`manage.py`（init/lock/up/configure/status/backup、秘密値は`secrets/`生成）、`configure.py`（標準ライブラリのみ、ボード・タイル・権限を冪等反映、`apps.json`に無いタイルは削除、位置は動かさない）、`apps.json`、テスト（`tests/test_homarr_stack.py`）。残りは下の「依存と並列作業」に書く配備側。

配備先: **services-01**。開発先は `stacks/homarr/`。専用Composeと保存先へ切り出す。

## 実装手順

**2026-09-12の利用者判断で既存環境からの移行は行わない。** 以下は新規構築として読む（既存データの棚卸し・保全・切戻しは対象外）。実装済みは`stacks/homarr/`一式（Compose・`manage.py`・`configure.py`・`apps.json`・テスト（`tests/test_homarr_stack.py`））と配備IaC（`platform/ansible/roles/homarr`・`platform/ansible/homarr.yml`・`dns.yaml`の`homarr`レコード・identityの`homarr` OIDCクライアント）。実配備は完了（W01・`https://homarr.apextox.dpdns.org`）。残りは実機確認（SSO・閲覧/管理者権限・再実行・再起動）。

1. 既存環境のボード・アプリ・暗号鍵・ログイン方式は棚卸しのみ行い、持ち込まない。`stacks/homarr/`はHomarr単独のComposeとし、他サービスの認証DBや資料を配備しない。
2. 設定反映スクリプトの配備先・URLをパラメータ化し、同じデータに再実行してもタイル位置を壊さない構成にする。認証は[identity](../operations/identity.md)のOIDCクライアント `homarr` と `users` / `admins` を使う。既存アカウントを引き継ぐ場合は紐付けを検証し、メール一致だけで別人のデータを結び付けない。
3. `manage.py backup` と復元手順を確認し、HTTPS入口とコンテナ再作成後もボード・暗号鍵が保たれることを確かめる。

## 依存と並列作業

- 開発開始: なし。サンプルデータで切り出しと設定生成を進める。
- 配備・切替: [I01](I01-resources.md)の余力確認、[N05](N05-https.md)の入口設定とidentityクライアント準備。
- 競合調整: `stacks/homarr/apps.json`、identityのSSO生成スクリプト、共通TLS設定は他W担当と変更を調整する。services-01のVM再起動はNetBox・VPN・家電にも影響する。

## 検証・完了条件

2026-09-12の実配備で確認したこと:

- `homarr.apextox.dpdns.org` がLet's Encryptの証明書でHTTPS応答する（`/api/auth/csrf`が200）
- `/api/auth/providers` に `oidc`（Authentik）が出て、callbackが `https://homarr.apextox.dpdns.org/api/auth/callback/oidc`
- `manage.py configure` がボード `home`・タイル・`admins`権限・`users`閲覧許可を反映し、再実行してもタイルが増えない（配備中に複数回実行）
- identityの`homarr`クライアントは`sub_mode=user_uuid`で作成済み

残り（ブラウザで人が確認する）:

- 一般利用者（`users`）がSSOで入って閲覧だけできること、管理者が編集できること
- コンテナ再作成・VM再起動後もボード・暗号鍵・セッションが保たれること
- 切戻し手順（`AUTH_PROVIDERS=credentials`へ戻す）の記録

- 一般利用者は閲覧のみ、管理者はボード編集可能。SSO・ローカル復旧ログイン・未認証拒否を確認する。
- タイル・配置・リンク先と鍵が復元され、再配備・コンテナ再作成・VM再起動後も保持される。
- 既存ボードを保ったまま設定反映を2回実行し、意図しない追加・削除がない。切戻し手順を記録する。
