# Homarr

サービスの入口（ダッシュボード）です。**services-01 に単独の Compose
プロジェクトとして置きます。** 旧ハブの `media-hub`（Authentik・docs・他サービス
同居）は流用せず、認証は新しい identity の OIDC へ接続します。

- 担当計画: [W01 Homarr](../../docs/development/W01-homarr.md)
- 利用案内: [Homarrの使い方](../../docs/services/homarr.md)
- 所有境界: [IaCの所有境界](../../docs/architecture/iac.md)

## 構成

| ファイル | 内容 |
| --- | --- |
| `compose.yaml` | Homarr 1サービス。イメージは `compose.lock.yaml` でダイジェスト固定 |
| `manage.py` | `init` / `lock` / `up` / `configure` / `status` / `backup` |
| `configure.py` | `apps.json` からボードを冪等に反映。標準ライブラリのみ |
| `apps.json` | 管理するタイルの一覧（名前・URL・説明・アイコン） |
| `.env.example` | 宣言値。秘密値は `secrets/`（Gitへ入れない） |
| `secrets/` | `secret_encryption_key`・`admin_password` を `manage.py init` が生成。`oidc_client.json` は identity の `secrets/oidc-homarr.json` を Ansible が写す |

## 配備（IaC）

services-01 は `05-seed` の静的インベントリ（`seed.ini`）で扱います。

```bash
# 1. identity の homarr OIDCクライアントを作る
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/identity.yml'
# 2. homarr.apextox.dpdns.org の A レコードを作る
tools/tf 20-dns apply
# 3. services-01 へ配備（role: platform/ansible/roles/homarr、play: homarr.yml）
ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
  .venv/bin/ansible-playbook -i platform/ansible/seed.ini platform/ansible/homarr.yml
```

`dns.yaml` の `homarr` レコード（upstream `127.0.0.1:7575`）を `tls_proxy`
ロールが読み、Caddy が `https://homarr.apextox.dpdns.org` を受けて Homarr へ
中継します。Homarr 自身のポートは 127.0.0.1 のままです。

## 使い方

```bash
sudo python3 manage.py init
sudo python3 manage.py lock          # 初回のみ。以後はダイジェストを維持
sudo python3 manage.py up
sudo python3 manage.py configure     # ボード・タイル・権限を反映
sudo python3 manage.py status
```

`configure` は既存タイルを削除も移動もしません。UIで動かした配置はそのまま
残り、`apps.json` に足した分だけが増えます。同じ内容で2回実行しても差分は
出ません。

## 認証

- ローカル管理者は `secrets/admin_password`。SSO障害時の復旧ログインに使います。
- SSOは identity の `homarr` クライアント。`AUTH_PROVIDERS=credentials,oidc` と
  `AUTH_OIDC_ISSUER` を `.env` へ入れて有効化します。
- Homarr 側の `admins` グループに admin 権限を与えます。identity の `admins`
  グループとの対応は、メール一致ではなく identity の subject（`user_uuid`）で
  確認します。

## データ

ボード・アプリ・暗号鍵は `storage/homarr`（`/appdata`）です。`SECRET_ENCRYPTION_KEY`
を失うと保存済みの認証情報を復号できないため、`manage.py backup` は
`state.tar` と `deployment.tar` を分けて取ります。

## まだやっていないこと

- services-01 への実配備（上のコマンドは未実行）と実機確認（SSO・閲覧/管理者権限・再実行・再起動）
- 旧ハブからのデータ移行（ユーザーの判断で流用しない。新規に構築する）
