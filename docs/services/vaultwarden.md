# Vaultwarden

**新しい入口は <https://vault.apextox.dpdns.org>（services-01、Let's Encrypt・Authentik SSO）です。** 2026-09-12に新規構築しました。管理画面 `/admin` は公開せず、`ssh -N -L 8222:127.0.0.1:8222 debian@services-01` の転送で `http://localhost:8222/admin` を開きます（admin tokenは `/opt/services/vaultwarden/secrets/admin_token`、0400）。一般登録と組織招待は既定で無効で、Web UIに「Create account」は出ません（初回作成はSSO経由のみ）。以下は旧ステージング（`vault.localhost:8243`・SSH転送）で確認した内容を含みます。

## Web保管庫の日本語化

Web保管庫の表示言語は、Vaultwardenサーバーの環境変数ではなく、Bitwarden互換Webクライアント側の設定です。利用者ごとに次の場所で変更します。

`設定` → `プリファレンス` → `言語` → `日本語`

サーバー側で全利用者に日本語を強制する標準設定はありません。ブラウザーの言語を日本語にして初期表示を日本語へ寄せることはできますが、利用者ごとの表示設定として扱うのが安全です。

一方、Vaultwarden固有の`/admin`画面はWeb保管庫とは別の画面で、現在は英語のみです。サーバー側で日本語化する場合は、バージョンに対応した管理画面テンプレートを`data/templates/admin`へ配置して上書きします。ただし、アップデート時にテンプレートを更新し直す必要があり、公式が検証した日本語パッケージではありません。[Vaultwarden管理画面の翻訳手順](https://github.com/dani-garcia/vaultwarden/wiki/Translating-admin-page)

<a id="sso-login"></a>
## Authentikでログインする手順

この環境はVaultwarden 1.37.2 / Web Vault 2026.7.0で、組み込みOIDCを有効化しています。通常の新規アカウント作成は[Authentikからの招待](sso.md)を使います。Vaultwarden側の「Create account／アカウント作成」から一般登録を始めません。

1. [接続手順](../operations/hub.md)に従い、SSH転送の8243・9443とローカルCAを準備する。
2. ブラウザーで `https://vault.localhost:8243/` を開く。8222の直接HTTPポートやBitwardenのクラウドサイトから始めない。
3. 画面に見えるメール欄へAuthentikに登録したメールを入力し、「シングルサインオンを使用する」を押す。
4. Authentikの画面で共通アカウントへログインする。
5. 初回は保管庫用のマスターパスワードを設定する。既存の保管庫ならそのマスターパスワードで解除する。

### 「SSO識別子」を求められたら

これはAuthentikのユーザー名やパスワード、OIDCのclient secretではありません。現在のサーバーが返す共通の識別子は次です。

```text
00000000-01DC-01DC-01DC-000000000000
```

通常のメール入力から進む画面では自動取得されます。`/#/sso`の直接アクセスやクライアントによって手入力を求められた場合に使います。任意の文字列で進める版もありますが、初回保管庫作成時に組織識別子との不一致を起こす可能性があるため、この環境の返す値へ揃えます。これは公開値で、認証用秘密値ではありません。[導入版のSSO識別子実装](https://github.com/dani-garcia/vaultwarden/blob/1.37.2/src/sso.rs)、[組織識別子応答](https://github.com/dani-garcia/vaultwarden/blob/1.37.2/src/api/core/organizations.rs)

### 今回確認したエラーと対応

2026-09-08のサーバーログで `You need to verify your email with your provider before you can log in` を確認しました。Authentikの有効なメール付きアカウントが未確認属性になっているため、初回SSOが拒否されます。[メール確認手順](sso.md)を実施してからSSOをやり直します。既存利用者の所有確認は未完了で、今回一括の確認済み変更は行っていません。

| 症状 | 原因・対応 |
| --- | --- |
| SSOを押して入力エラー | 先に見えているメール欄へ登録メールを入れる |
| SSO識別子を要求 | 上記の共通識別子を入力。秘密値は入力しない |
| メール未確認エラー | Authentikでメール所有確認後、真偽値`email_verified: true`を設定 |
| 既存non-SSOユーザーと同じメールで失敗 | 既存保管庫との自動紐付けは無効。既存ログインを使い、バックアップと本人確認の上で個別移行を計画 |
| 証明書／issuer／discoveryエラー | HTTPS入口、CA信頼、9443転送、Vaultwarden内部からのissuer到達を確認 |
| マスターパスワードを求められる | 通常の復号手順。Authentikのパスワードを入れる場面ではない |
| 最初は入れるがしばらくすると失敗 | OIDCセッション・refresh token・時刻を確認。今回`offline_access`を追加 |

サーバーは `SSO_ENABLED=true`、`SSO_SCOPES=email profile offline_access`、`SSO_PKCE=true`を使用し、未知のメール確認状態を許可しません。ローカル登録は`SIGNUPS_ALLOWED=false`、既存保管庫へのメール一致だけの紐付けは`SSO_SIGNUPS_MATCH_EMAIL=false`のままです。通常のローカル登録と、認可済みSSOによる初回作成は別経路です。

緊急時・既存アカウント向けのローカルログインを残すため、`SSO_ONLY=false`としています。Web保管庫の「Other／その他」からローカル認証へ切り替えます。全利用者へSSOのみを強制する場合は、既存保管庫・ブラウザー拡張・スマホの移行確認後に別途変更します。[公式SSO設定](https://github.com/dani-garcia/vaultwarden/wiki/Enabling-SSO-support-using-OpenId-Connect)

SSOはマスターパスワードや保管庫の暗号鍵を代替しません。Authentikのアカウントを復旧できても、忘れたマスターパスワードだけで保管庫を復号できるようにはなりません。Bitwarden拡張・モバイルでは自己ホストのサーバーURLを設定し、その端末から両HTTPS入口に接続できることも確認します。現在のlocalhost＋SSH転送構成をそのままスマホから使えるとは扱いません。

## SMTPと招待

通常の利用開始の招待はAuthentikで発行します。Vaultwarden側の招待は共有保管庫の組織参加など、アプリ固有の用途として区別します。メール招待、メール確認、パスワードヒントの送信、メール2FAなどを使うにはSMTPまたはsendmailが必要です。[SMTP設定](../operations/smtp.md)

Vaultwardenのメール本文を日本語化する場合は、`data/templates/email`へテンプレートを配置できます。テンプレート内の`{{変数}}`を壊さず、アップデート後に最新版との差分を確認してください。[公式メールテンプレート手順](https://github.com/dani-garcia/vaultwarden/wiki/Translating-the-email-templates)

## 設定の優先順位

Vaultwardenの管理画面で設定を保存すると、永続化領域の`/data/config.json`に保存され、環境変数より優先される設定があります。環境変数を変更したのに反映されない場合は、`config.json`側の保存値を確認します。環境変数と管理画面を同じ設定の編集場所として混在させない方が安全です。

## 管理画面の公開

利用者が使うのは`/`であり、`/admin`は管理者専用です。現在の`Caddyfile`では`/admin`を403にしているため、管理画面はSSHポートフォワードなどの管理経路から使う前提です。


Vaultwardenでは、メールだけで忘れたマスターパスワードを再設定して保管庫を復号することはできません。緊急アクセスなどの復旧手段は別途設定が必要です。
