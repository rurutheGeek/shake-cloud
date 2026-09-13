# SMTPとメール送信

## メールサーバーは必要か

はい。メールを送るには、外部SMTPリレーサービス、組織のメールサーバー、またはホスト上のsendmail互換サービスのいずれかが必要です。VaultwardenやNextcloudがSMTPサーバーになるわけではありません。

最初は自前でPostfixを公開するより、認証付きの外部SMTPリレーを使う方が、送信先の迷惑メール判定・逆引き・DKIM・送信制限を管理しやすくなります。

## Vaultwardenで使う設定

**現在の Vaultwarden（services-01、`stacks/vaultwarden/`）は SMTP をまだ設定していません。** W02 で新規構築した際、メール依存の機能を使わない前提で `stacks/vaultwarden/compose.yaml` に SMTP 変数を入れていないためです。有効にするときは、下の変数名を同スタックの Compose と `.env` へ足します。

Vaultwardenは、少なくとも送信元とSMTPホストを設定します。ユーザー名を設定する場合はパスワードも必要です。通常は587番ポートのSTARTTLSを使います。465番ポートの暗黙TLSを使うサービスでは`force_tls`を指定します。[Vaultwarden公式SMTP設定](https://github.com/dani-garcia/vaultwarden/blob/main/.env.template)

Vaultwardenで有効化するときは、次の変数名を `stacks/vaultwarden/.env` へ足し、`compose.yaml` の `environment` で Vaultwarden 本来の `SMTP_*` へ渡します。値は実際のサービスの情報へ置き換え、Gitへ登録しません。

```dotenv
VAULTWARDEN_SMTP_HOST=smtp.example.net
VAULTWARDEN_SMTP_FROM=vaultwarden@example.net
VAULTWARDEN_SMTP_FROM_NAME=Vaultwarden
VAULTWARDEN_SMTP_SECURITY=starttls
VAULTWARDEN_SMTP_PORT=587
VAULTWARDEN_SMTP_USERNAME=vaultwarden@example.net
VAULTWARDEN_SMTP_PASSWORD=write-this-in-the-untracked-env-only
```

Nextcloud側へSMTPを入れるときも、Nextcloudスタックの `.env` と `compose.yaml` に別途設定します。両者は同じSMTPサービスを使えても、環境変数名と設定場所は別です。

SMTPパスワードはGitへ追加せず、VM上の `.env`（0600）で管理します。設定後は `stacks/vaultwarden/manage.py up` で再配備します。

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

送信には **Gmail（`shake.notify@gmail.com`）の SMTP** を使います（2026-09-12 設定）。公開メールサーバーは構築していません。少量の招待・確認メールには、認証付きの外部SMTPを各サービスから利用する構成を基本にします。ドメイン登録とSMTP契約は別です。Cloudflareでドメインを購入しても、それだけで一般のSMTP送信設定が得られるわけではありません。

**ローカルMTA（Postfix）は置きません**（2026-09-11 決定）。サテライトとして置けばアプリは認証情報を持たずに済みますが、結局インターネットへ届けるには上流のスマートホストが要り、構成要素が1つ増えるだけです。家庭回線からの直接MX配送は PTR・SPF/DKIM・ポート25遮断で拒否されやすいため、上流が外部SMTPなら、アプリが直接そこへ送る方が短く済みます。将来メールボックスや複数アプリの集約が要るようになったら再検討します。

自前の受信メールボックスも必要になった場合は、SMTP送信だけとは別の要件として、メールボックス・迷惑メール対策・配送監視を設計します。

## Gmailを使う場合（現在の設定）

`shake.notify@gmail.com` から送ります。設定の要点:

- **アカウントのパスワードではなく「アプリパスワード」を使う。** 2段階認証を有効にしたうえで
  [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) で発行する。画面は
  `abcd efgh ijkl mnop` のように4文字ずつ区切って表示されるが、**空白は表示用**で、実際の値は
  16文字。`.env`／SOPS には空白を除いて入れる。
- ホスト `smtp.gmail.com`、587番 STARTTLS（または465番 SSL）。外向き 587 が塞がれていないこと。
- **差出人は認証したアドレス（または Gmail 側で確認済みの別名）に限られる。** 別ドメインの
  `@apextox.dpdns.org` などを `SMTP_FROM` にはできない。
- 無料アカウントのSMTPは**1日およそ500通**まで。配信はGoogleのSPF/DKIMで通るため、
  SPF/DKIM/DMARC を自前で用意しなくてよい。

`platform/sops/smtp.sops.yaml`（SOPS 暗号化。書式は `platform/sops/smtp.sops.yaml.example`）:

```yaml
SMTP_HOST: smtp.gmail.com
SMTP_PORT: "587"
SMTP_SECURITY: starttls
SMTP_USERNAME: shake.notify@gmail.com
SMTP_PASSWORD: <16文字のアプリパスワード>
SMTP_FROM: shake.notify@gmail.com
SMTP_FROM_NAME: shake-cloud
```

## identity（Authentik）での設定

SMTP は `platform/sops/smtp.sops.yaml`（上記 Gmail の例を参照）で設定します。キーは:

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

`manage.py configure` は SMTP を使って次の2つを整えます（`configure.py`、2026-09-12）。

- **パスワード再設定フロー**（`default-recovery-flow`）: ログイン画面の「パスワードを忘れた」
  から、識別 → メール送信 → 新パスワード設定 → ログインの順に進みます。`akadmin` には
  `SMTP_FROM`（`ADMIN_EMAIL` で上書き）を復旧先として設定します。
- **メール確認コード**（`default-authenticator-email-setup`）: 利用者設定から登録できる
  第二の認証器。パスキーを失った人が、メールに届くコードでログインの検証段階を
  通過できます。

送信できないときは `.env` の `SMTP_*` と Gmail のアプリパスワードを見直し、
`identity.yml` を流し直します。

2026-09-11 に identity VM 上へ**一時的な SMTP シンク**を立てて送信経路
（STARTTLS/SSL/PLAIN、認証、送信）を確認し、2026-09-12 に **Gmail の実設定を配備して
実送信を確認**しました（`invitations.py` の `smtp_settings`／`deliver` が `.env` を
読み、Gmail 経由で配送）。値を変えるときは `smtp.sops.yaml` を更新し、
`platform/ansible/identity.yml` を流し直します。配信の迷惑メール・SPF・DKIM・DMARC は
Google 側で通ります。
