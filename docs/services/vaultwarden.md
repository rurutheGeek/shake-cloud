# Vaultwarden

## Web保管庫の日本語化

Web保管庫の表示言語は、Vaultwardenサーバーの環境変数ではなく、Bitwarden互換Webクライアント側の設定です。利用者ごとに次の場所で変更します。

`設定` → `プリファレンス` → `言語` → `日本語`

サーバー側で全利用者に日本語を強制する標準設定はありません。ブラウザーの言語を日本語にして初期表示を日本語へ寄せることはできますが、利用者ごとの表示設定として扱うのが安全です。

一方、Vaultwarden固有の`/admin`画面はWeb保管庫とは別の画面で、現在は英語のみです。サーバー側で日本語化する場合は、バージョンに対応した管理画面テンプレートを`data/templates/admin`へ配置して上書きします。ただし、アップデート時にテンプレートを更新し直す必要があり、公式が検証した日本語パッケージではありません。[Vaultwarden管理画面の翻訳手順](https://github.com/dani-garcia/vaultwarden/wiki/Translating-admin-page)

## SSO

現在の公式VaultwardenはOpenID ConnectによるSSOに対応しています。`SSO_ENABLED=true`で有効化し、`SSO_AUTHORITY`、`SSO_CLIENT_ID`、`SSO_CLIENT_SECRET`などを環境変数で設定します。コールバックURLは`DOMAIN`から生成されます。[公式SSO設定](https://github.com/dani-garcia/vaultwarden/wiki/Enabling-SSO-support-using-OpenId-Connect)

ただし、SSOはVaultwardenのマスターパスワードを不要にする機能ではありません。SSOで利用者を認証した後も、保管庫の復号にマスターパスワードが必要です。したがって、SSOの効果は「誰が使えるかの入口を共通化する」ことであり、パスワード保管庫の暗号鍵をIdPへ預けることではありません。

この構成の`compose.lock.yaml`はイメージをダイジェストで固定しているため、SSOを使う前に、固定中のVaultwardenがSSO対応バージョンかを確認します。更新時はバックアップ、テスト環境でのログイン確認、モバイル・ブラウザー拡張の同期確認を行います。

## SMTPと招待

SMTPを設定しない場合でも、管理画面から招待URLを作って本人へ手渡す運用はできます。メール招待、メール確認、パスワードヒントの送信、メール2FAなどを使うにはSMTPまたはsendmailが必要です。[SMTP設定](../operations/smtp.md)

Vaultwardenのメール本文を日本語化する場合は、`data/templates/email`へテンプレートを配置できます。テンプレート内の`{{変数}}`を壊さず、アップデート後に最新版との差分を確認してください。[公式メールテンプレート手順](https://github.com/dani-garcia/vaultwarden/wiki/Translating-the-email-templates)

## 設定の優先順位

Vaultwardenの管理画面で設定を保存すると、永続化領域の`/data/config.json`に保存され、環境変数より優先される設定があります。環境変数を変更したのに反映されない場合は、`config.json`側の保存値を確認します。環境変数と管理画面を同じ設定の編集場所として混在させない方が安全です。

## 管理画面の公開

利用者が使うのは`/`であり、`/admin`は管理者専用です。現在の`Caddyfile`では`/admin`を403にしているため、管理画面はSSHポートフォワードなどの管理経路から使う前提です。


Vaultwardenでは、メールだけで忘れたマスターパスワードを再設定して保管庫を復号することはできません。緊急アクセスなどの復旧手段は別途設定が必要です。
