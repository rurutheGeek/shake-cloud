# Vaultwarden

パスワード管理です。**services-01 に単独の Compose プロジェクトとして置きます。**
旧ホスト（検証用ステージング）のデータは移行せず、新規に構築します。認証は
新しい identity（Authentik）の OIDC へ接続し、HTTPS 名は
`vault.apextox.dpdns.org` です。

- 担当計画: [W02 Vaultwardenのservices-01移行](../../docs/development/W02-vaultwarden.md)
- 利用・SSO手順: [Vaultwarden](../../docs/services/vaultwarden.md)
- 所有境界: [IaCの所有境界](../../docs/architecture/iac.md)

## 構成

| ファイル | 内容 |
| --- | --- |
| `compose.yaml` | Vaultwarden 1サービス。イメージは `compose.lock.yaml` でダイジェスト固定 |
| `manage.py` | `init` / `lock` / `up` / `status` / `backup` |
| `.env.example` | 宣言値。秘密値は `secrets/`（Gitへ入れない） |
| `secrets/` | `admin_token` を `manage.py init` が生成。`oidc_client.json` は identity の `secrets/oidc-vaultwarden.json` を Ansible が写す |

## 配備（IaC）

services-01 は `05-seed` の静的インベントリ（`seed.ini`）で扱います。

```bash
# 1. identity の vaultwarden OIDCクライアントを作る
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/identity.yml'
# 2. vault.apextox.dpdns.org の A レコードを作る
tools/tf 20-dns apply
# 3. services-01 へ配備（role: platform/ansible/roles/vaultwarden、play: vaultwarden.yml）
ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
  .venv/bin/ansible-playbook -i platform/ansible/seed.ini platform/ansible/vaultwarden.yml
```

`dns.yaml` の `vault` レコード（upstream `127.0.0.1:8222`）を `tls_proxy`
ロールが読み、Caddy が `https://vault.apextox.dpdns.org` を受けて Vaultwarden
へ中継します。Vaultwarden 自身のポートは 127.0.0.1 のままです。

## 使い方

```bash
sudo python3 manage.py init    # .env・storage・admin token（再生成しない）
sudo python3 manage.py lock    # 初回のみ。以後はダイジェストを維持
sudo python3 manage.py up
sudo python3 manage.py status
sudo python3 manage.py backup --destination /var/backups/vaultwarden
```

## SSO

- identity の `vaultwarden` クライアント（confidential、sub_mode は `user_uuid`）。
  リダイレクトURIは `https://vault.apextox.dpdns.org/identity/connect/oidc-signin`。
- `users` グループにだけアプリへのアクセスを与えます。
- `SSO_ENABLED=true` / `SSO_SCOPES=email profile offline_access` / `SSO_PKCE=true`。
  既存アカウントとのメール一致の自動紐付けは `SSO_SIGNUPS_MATCH_EMAIL=false`、
  未知のメール確認状態は `SSO_ALLOW_UNKNOWN_EMAIL_VERIFICATION=false` で拒否します。
- 緊急時のローカルログインを残すため `SSO_ONLY=false` です。Web保管庫の
  「Other／その他」からローカル認証へ切り替えます。
- 一般登録と組織招待は既定で無効（`SIGNUPS_ALLOWED=false`・`INVITATIONS_ALLOWED=false`）。
  後者を有効にすると Vaultwarden の `is_signup_disabled()` が false を返し、Web UI に
  「Create account」が出ます（実際の登録は拒否されますが紛らわしい）。招待を使う場合は
  SMTP と運用を整えてから有効化します。SSO の初回作成には影響しません。
- **SSO はマスターパスワードや保管庫の暗号鍵を代替しません。** Authentik の
  アカウントを復旧できても、忘れたマスターパスワードだけでは保管庫を復号できません。
  マスターパスワードは本人が管理し、復旧手段を別途用意してください。

## 管理画面（/admin）

`/admin` は管理経路専用です。Caddy 側では公開せず、SSH ポート転送で
127.0.0.1:8222 へ直接接続して使います。

```bash
ssh -N -L 8222:127.0.0.1:8222 <services-01 のホスト>
# ブラウザーで http://127.0.0.1:8222/admin を開き、secrets/admin_token を入力
```

## データ

DB・添付・鍵・`config.json` は `${STORAGE_ROOT}/data`（`/data`）です。
`manage.py backup` は `state.tar` と `deployment.tar` を分けて取ります。
管理画面で保存した設定は `config.json` に入り、環境変数より優先される場合が
あります。環境変数を変えたのに反映されないときは `config.json` を確認します。

## まだやっていないこと

- services-01 への実配備（上のコマンドは未実行）と実機確認（SSO・マスターパスワード・
  再起動）
- 旧ホストからのデータ移行（実データは使わず、検証用の新規構築のみ）
