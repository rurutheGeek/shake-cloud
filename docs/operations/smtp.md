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

自前の受信メールボックスも必要になった場合は、SMTP送信だけとは別の要件として、メールボックス・迷惑メール対策・配送監視を設計します。

Authentikにも同じSMTPサービスを設定できます。hub/compose.smtp.example.yamlを参考に、ホスト・ポート・送信元・認証情報を入力します。まだ実際のメール配送は検証していません。
