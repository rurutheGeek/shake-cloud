# メールビューア（mail-view）

Gmail の通知用メールボックス（`shake.notify@gmail.com`）の受信トレイを、
Gmail へログインせずブラウザーで読むための読み取り専用ビューアです。**services-01
に単独の Compose プロジェクトとして置いています。** メールの実体は Gmail にあり、
このスタックは状態を持ちません。

- 運用・認証情報の扱い: [SMTPとメール送信](../../docs/operations/smtp.md)
- 使い方（利用者向け）: [全サービスの使い方](../../docs/services/usage.md)
- 所有境界: [IaCの所有境界](../../docs/architecture/iac.md)

## 仕組み

- `imap.gmail.com:993` へアプリパスワードでログインし、`EXAMINE`（readonly）で
  メールボックスを開きます。**表示しても既読は付きません。** 検索は `UID SEARCH`、
  一覧は `BODY.PEEK[HEADER.FIELDS ...]`、本文は `BODY.PEEK[]`（上限つき）です。
- 一覧は既定で新しい `MESSAGE_LIMIT` 件（50件）です。「全件を表示」（`?limit=all`、
  上限2000件）で受信トレイ全体を出します。`CACHE_SECONDS`（既定30秒）キャッシュし、
  `?refresh=1` で取り直します。
- HTML メールは標準ライブラリのパーサーでテキスト化し、URL だけリンクにします。
  表のセルは空白で区切り、インデントと空行を均して読みやすくします。
  外部画像は読み込まず、CSP で `default-src 'none'` にしています。
- 本文が `MAX_BYTES`（既定512KB）を超える場合は先頭だけを表示します。
- 添付ファイルは名前とサイズだけを表示し、ダウンロードはしません。

## セキュリティ

このページは Gmail の全文検索・本文と、**identity（Authentik）の招待メールや
復旧リンク**が見える場所です。入口は services-01 の Caddy だけで、Forward Auth
（全ログインユーザー）を通します。アプリ自身のポートは `127.0.0.1` に閉じており、
LAN から直接は開けません。コンテナは `read_only`・`cap_drop: [ALL]`・
`no-new-privileges` で動かし、パスワードは `manage.py` が環境変数で渡します。

アプリパスワードは SMTP と共用できます。Gmail で IMAP を使うには、2段階認証を
有効にしたうえで IMAP アクセスを有効にし、アプリパスワードを発行します
（`platform/sops/mail-view.sops.yaml` があればそれを使い、無ければ
`smtp.sops.yaml` を使います）。

## 構成

| ファイル | 内容 |
| --- | --- |
| `compose.yaml` | Python 3.13（alpine）で `app.py` を実行。イメージは `compose.lock.yaml` でダイジェスト固定 |
| `app.py` | 標準ライブラリだけの HTTP サーバー（IMAP・HTML 変換・ページ） |
| `manage.py` | `init` / `lock` / `up` / `status` |
| `.env.example` | 宣言値。秘密値は `secrets/`（Gitへ入れない） |
| `secrets/imap_password` | Ansible が SOPS から写す。`manage.py` が環境変数で渡す |

`backup` はありません。状態が無く、認証情報の正本は `platform/sops/` にあります。

## 配備（IaC）

services-01 は `05-seed` の静的インベントリ（`seed.ini`）で扱います。先に
`identity.yml` を流して Forward Auth のプロバイダを作ってから配備します。

```bash
# 1. mail-view.apextox.dpdns.org の A レコードを作る
tools/tf 20-dns apply
# 2. Forward Auth のプロバイダとアプリを作る（configure.py）
ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
  .venv/bin/ansible-playbook -i platform/ansible/seed.ini platform/ansible/identity.yml
# 3. services-01 へ配備（role: platform/ansible/roles/mail_view、play: mail-view.yml）
ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
  .venv/bin/ansible-playbook -i platform/ansible/seed.ini platform/ansible/mail-view.yml
```

`dns.yaml` の `mail-view` レコード（upstream `127.0.0.1:8310`）を `tls_proxy`
ロールが読み、Caddy が `https://mail-view.apextox.dpdns.org` を Forward Auth
つきで受けて中継します。

## 使い方

```bash
sudo python3 manage.py init    # .env と secrets/imap_password を確認
sudo python3 manage.py lock    # 初回のみ。以後はダイジェストを維持
sudo python3 manage.py up
sudo python3 manage.py status
```

## 設定

- `IMAP_HOST` / `IMAP_PORT`。既定は `imap.gmail.com:993`。
- `IMAP_USERNAME`。配備時に Ansible が SOPS の値から `.env` へ入れます。
- `IMAP_PASSWORD`。`secrets/imap_password` から `manage.py` が渡します。
- `MESSAGE_LIMIT`（既定50件）、`CACHE_SECONDS`（既定30秒）、
  `MAX_BYTES`（既定512KB）、`TZ_OFFSET_HOURS`（既定9）。
- IMAP のタイムアウトは30秒。取得に失敗したときはページに理由を出します。
