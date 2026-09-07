# 共通ログイン

Authentikを共通のアカウント台帳にします。利用者は各サービスで新規登録せず、Authentikのアカウントでログインします。SSO利用時は [接続手順](../operations/hub.md) に従ってSSH転送とローカルCAを設定してください。

| サービス | 認証・初回作成 | 権限 |
| --- | --- | --- |
| Homarr | OIDC | 一般利用者はハブの閲覧。homarr-adminsは管理 |
| Nextcloud | user_oidcによるOIDC・初回作成 | media-usersに共有books/musicを公開。私有データは別 |
| Kavita | 組み込みOIDC・初回作成 | Booksライブラリ、ダウンロード・ブックマーク |
| Navidrome | Authentikのプロキシ認証・初回作成 | sso_で始まる一般ユーザー。共有音楽を閲覧 |
| MeTube | Authentikのプロキシ認証 | 共有キュー・共有Cookie・共通保存先 |
| Vaultwarden | 組み込みOIDC・初回作成 | 保管庫は本人専用。マスターパスワードは別途必要 |
| NetBox | OIDC | Authentikのhomarr-adminsに利用を限定。NetBoxの操作権限は別管理 |

構成は `hub/configure-oidc.py`、`hub/configure-proxy.py`、`hub/configure-services.py`、`sso/` で管理します。OIDCクライアントの秘密値は `hub/oidc-secrets.json` へ初回生成し、Gitへ入れません。`compose.integrations.yaml` などの生成済みローカル設定にも秘密値が含まれます。

## 利用者をコードで追加

```bash
cp hub/users.example.json hub/users.local.json
chmod 600 hub/users.local.json
# ユーザー名・実際のメールアドレス・表示名を編集
sudo .hub-venv/bin/python hub/users.py hub/users.local.json
```

初期パスワードは `runtime/user-bootstrap.json` に保存します。対象本人へ別の安全な経路で渡し、Authentikのユーザー画面で変更してください。再適用で既存パスワードを変更しません。ファイルから行を消すだけではユーザーを削除せず、`active: false` を指定するとAuthentikのアカウントを無効にします。

通常の利用者は `media-users` にだけ所属させます。`homarr-admins` を追加するとHomarrの管理とNetBoxのSSO利用を許可します。SMTPは別途設定が必要です。メール未設定では招待・確認メールを送れません。管理者が登録するメールアドレスを確認してください。KavitaとVaultwardenは確認済みメールを要求します。`email_verified` は初期値falseです。SMTPでの確認フローを組むか、管理者が本人とアドレスを別経路で確認した場合にだけ、対象ユーザーのJSONをtrueへ変更します。未確認のアドレスを一括で確認済みにしません。

## 既存アカウントとの関係

既存のローカル管理者、ファイル、読書履歴、お気に入りは保持します。新しいSSOユーザーへ自動移行しません。NextcloudはOIDCのsubに基づく別ID、Navidromeは `sso_ユーザー名` を使い、既存adminと衝突させません。Vaultwardenも既存ユーザーへのメールアドレスだけによる自動紐付けを無効にしています。

SSOは共通パスワード認証です。アプリ固有の権限・セッション・データを一括で同期する機能ではありません。利用停止時に即時遮断が必要なら、Authentikの無効化だけでなく各アプリのセッション失効・ユーザー停止も実施してください。

Vaultwardenでは、初回にマスターパスワードを設定し、保管庫を開くときに入力します。SSOやメールで暗号化キーを代替・復元することはできません。

## 緊急時とモバイルアプリ

ローカル管理者のログインは残しています。Navidromeの緊急用/APIポートはサーバーの `127.0.0.1:14533` です。音楽同期タイマーはこちらを使います。通常のWebアクセスは4533です。MeTubeの内部ポート18081もlocalhost限定です。

SubsonicクライアントはブラウザーのAuthentikログイン画面を処理できないことがあります。Web SSOの検証とモバイルクライアントの検証は別です。利用するクライアントに応じて、専用のアプリ認証とHTTPS接続を別途構成します。

参考: [Nextcloud OIDC](https://docs.nextcloud.com/server/latest/admin_manual/configuration_user/user_auth_oidc.html)、[Kavita OIDC](https://wiki.kavitareader.com/guides/admin-settings/open-id-connect/)、[Authentik](https://docs.goauthentik.io/)。
