# SMTPとメール送信

## メールサーバーは必要か

はい。メールを送るには、外部SMTPリレーサービス、組織のメールサーバー、またはホスト上のsendmail互換サービスのいずれかが必要です。VaultwardenやNextcloudがSMTPサーバーになるわけではありません。

最初は自前でPostfixを公開するより、認証付きの外部SMTPリレーを使う方が、送信先の迷惑メール判定・逆引き・DKIM・送信制限を管理しやすくなります。

## Vaultwardenで使う設定

Vaultwardenは、少なくとも送信元とSMTPホストを設定します。ユーザー名を設定する場合はパスワードも必要です。通常は587番ポートのSTARTTLSを使います。465番ポートの暗黙TLSを使うサービスでは`force_tls`を指定します。[Vaultwarden公式SMTP設定](https://github.com/dani-garcia/vaultwarden/blob/main/.env.template)

`compose.integrations.example.yaml`をコピーして使う場合の変数例です。値は実際のサービスの情報へ置き換え、Gitへ登録しません。

```dotenv
VAULTWARDEN_SMTP_HOST=smtp.example.net
VAULTWARDEN_SMTP_FROM=vaultwarden@example.net
VAULTWARDEN_SMTP_FROM_NAME=Vaultwarden
VAULTWARDEN_SMTP_SECURITY=starttls
VAULTWARDEN_SMTP_PORT=587
VAULTWARDEN_SMTP_USERNAME=vaultwarden@example.net
VAULTWARDEN_SMTP_PASSWORD=write-this-in-the-untracked-env-only
```

このリポジトリの連携例には、Nextcloud用SMTPとVaultwarden用SMTPを分けて記載しています。両者は同じSMTPサービスを使えても、環境変数名と設定場所は別です。

有効化する場合は、次のように連携Composeを作成してから再配備します。

```bash
cd media-stack
cp -n compose.integrations.example.yaml compose.integrations.yaml
# .envへSMTP_HOSTなどの実値を追加する
sudo python3 scripts/stack.py lock
sudo python3 scripts/stack.py up
```

`scripts/stack.py`は`compose.integrations.yaml`が存在すると自動的に読み込みます。SMTPパスワードはGitへ追加せず、root専用の`.env`または別のSecret配備で管理します。

## メール送信で確認すること

1. 外部SMTPサービスで送信元アドレスを許可する
2. SMTPホスト、ポート、TLS方式、認証情報を設定する
3. Vaultwardenの`DOMAIN`を実際のHTTPS URLにする
4. 招待メールまたはテストメールを送る
5. Vaultwardenログで接続エラーを確認する
6. 受信側で迷惑メール、SPF、DKIM、DMARCを確認する

SMTP未設定でも保管庫そのものは利用できますが、招待・メール確認・パスワードヒントの送信などのメール依存機能は使えません。

Vaultwardenでは、メールだけで忘れたマスターパスワードを再設定して保管庫を復号することはできません。緊急アクセスなどの復旧手段は別途設定が必要です。

## 今回の方針

SMTP事業者と送信元は未定です。公開メールサーバーは構築していません。少量の招待・確認メールには、認証付きの外部SMTPを各サービスから利用する構成を基本にします。ドメイン登録とSMTP契約は別です。Cloudflareでドメインを購入しても、それだけで一般のSMTP送信設定が得られるわけではありません。

**ローカルMTA（Postfix）は置きません**（2026-09-11 決定）。サテライトとして置けばアプリは認証情報を持たずに済みますが、結局インターネットへ届けるには上流のスマートホストが要り、構成要素が1つ増えるだけです。家庭回線からの直接MX配送は PTR・SPF/DKIM・ポート25遮断で拒否されやすいため、上流が外部SMTPなら、アプリが直接そこへ送る方が短く済みます。将来メールボックスや複数アプリの集約が要るようになったら再検討します。

自前の受信メールボックスも必要になった場合は、SMTP送信だけとは別の要件として、メールボックス・迷惑メール対策・配送監視を設計します。

## 新しい identity（Authentik）での設定

事業者が決まったら、`platform/sops/smtp.sops.yaml` を作り、次のキーを入れる（SOPS で暗号化。Git には平文を入れない）:

```yaml
SMTP_HOST: smtp.example.net
SMTP_PORT: "587"
SMTP_USERNAME: cloud@example.net
SMTP_PASSWORD: <password>
SMTP_FROM: cloud@example.net
SMTP_FROM_NAME: shake-cloud
SMTP_SECURITY: starttls   # 465 なら ssl、それ以外は starttls か plain
```

`platform/ansible/identity.yml` を流すと、identity ロールがこれを復号して identity VM の
`.env` へ写します。`.env` の値は:

- **Authentik 自身**が `AUTHENTIK_EMAIL__*` として読み、パスワード再設定などを送ります。
- **招待ツール**（`stacks/identity/invitations.py`）が `SMTP_*` として読み、招待メールを
  送ります。`smtp.sops.yaml` が無ければ招待はメールを送らず、リンクを 0600 のファイルへ
  保存するだけです。

認証情報は Secret として identity VM の `.env`（0600）にだけ置き、リポジトリには
暗号化した `smtp.sops.yaml` だけを置きます。

2026-09-11 に、identity VM 上へ**一時的な SMTP シンク**を立てて招待メールの送信
経路（STARTTLS/SSL/PLAIN、認証、送信）を確認しました。実際の事業者・送信元が
決まれば、`smtp.sops.yaml` を作って配備するだけで有効になります。受信側の
迷惑メール・SPF・DKIM・DMARC は事業者側の設定として別途確認します。
