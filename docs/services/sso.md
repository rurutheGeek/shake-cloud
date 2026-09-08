# 認証基盤と共通ログイン

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

## 認証の役割を分けて理解する

| 仕組み | 担当すること | 例 |
| --- | --- | --- |
| VPN / Tailscale | サービスまで通信できる経路 | 宅外から保管庫のURLへ到達 |
| Authentik | 誰であるかを確認する共通アカウント | パスワードや登録済みパスキーでログイン |
| OIDC | Authentikで認証した結果をアプリへ伝える | Vaultwardenが署名付きトークンを検証 |
| アプリ側アカウント・権限 | データの持ち主と操作可能範囲 | 本人の保管庫、共有musicの閲覧、管理者権限 |
| Vaultwardenのマスターパスワード | 保管庫を復号する | Authentikログイン後の保管庫解除 |

利用者は **Authentikの招待を受ける → 共通アカウントを作る → メール所有を確認する → 各アプリのSSOで初回ログインする**、の順で利用を開始します。アプリ側のユーザーは対応する初回ログイン処理で作られます。招待1回で全アプリのアカウントが直ちに一括作成されるわけではありません。

Authentikと各アプリのパスワードを同じに設定して回る必要はありません。Vaultwardenのマスターパスワードは別に用意します。Authentikのパスワード変更では保管庫のマスターパスワードは変わりません。

管理者にとっての「Application」は利用者へ見せるアプリとアクセス制限、「Provider」はそのアプリへ認証結果を渡す設定、「Flow / Stage」はログイン・招待登録・メール確認などの画面と処理の順序です。`media-users`は一般利用権、`homarr-admins`は管理用途であり、招待利用者には前者だけを付与します。

## 標準のアカウント作成はAuthentikの招待

2026-09-08に `media-invitation-enrollment` フローを追加しました。`hub/invitations.py configure` で再適用でき、`sso/manage.py`からも適用します。招待なしの登録は拒否し、招待はこのフロー限定・1回限り・24時間有効です。導入版のInvitation Stageはリンクを開いて登録画面へ入った時点で招待を消費するため、途中でブラウザーを閉じた場合は管理者が再発行します。登録時に指定メール・ユーザー名を利用者が変更したり、管理者グループを自己指定したりする入口は設けません。

SMTPは未設定のため、現在は**管理者が発行したリンクを本人へ安全な経路で渡す**運用です。スクリプトはメールを送信しません。招待を作っただけでメール所有確認が済むわけではありません。[Authentikの招待](https://docs.goauthentik.io/users-sources/user/invitations/)

### 管理者: 招待を発行する

`runtime/invite-user.json`を権限0600で作り、次の例を実際の対象者へ置き換えます。このファイルと出力された招待リンクはGitへ入れません。

```json
{
  "username": "member-a",
  "email": "member-a@example.net",
  "name": "利用者A"
}
```

```bash
sudo .hub-venv/bin/python hub/invitations.py invite runtime/invite-user.json
```

出力先の `runtime/invitations/` 内のJSONにURLと有効期限を保存します。トークンそのものはコマンド出力へ表示しません。管理者が本人と**そのメールアドレスの所有**を別経路で確認済みの場合に限り、発行時に `--email-owner-confirmed` を付けると確認済み属性も招待に設定できます。未確認なら付けず、登録後に次節の確認を行います。既存ユーザーや同じ対象の未撤去招待がある場合は重複発行を止めます。

期限切れや未使用の招待はAuthentik管理画面の **Directory → Invitations** で確認・削除してから再発行します。登録フローは **Flows and Stages → Flows** で確認できます。画面名は導入版の翻訳により異なります。

### 利用者: 招待から各アプリへ進む

1. [SSH転送・ローカルCA](../operations/hub.md)を準備し、招待リンクを開く。別アカウントでログイン済みならログアウトか別ブラウザープロファイルを使う。
2. 自分専用のAuthentikパスワードを設定する。招待フローは12文字以上を要求する。登録後、利用者設定からパスキー・MFAの追加を検討する。
3. 管理者のメール所有確認が未完了なら、確認を済ませる。VaultwardenとKavitaはこの状態のままでは初回SSOを通過できない。
4. ハブから目的のアプリを開き、SSOでログインする。Vaultwardenは[具体的なログイン手順](vaultwarden.md#sso-login)に従う。
5. Vaultwardenの初回だけ、別のマスターパスワードを設定して保管庫を作る。

### 管理者: メール未確認で止まる場合

Authentikの **Directory → Users → 対象ユーザー** で、登録メールと本人の所有を確認します。本人確認後、ユーザーのAttributesに既存属性を保持して次を追加／更新します。

```yaml
email_verified: true
```

これは「エラーを消すためのスイッチ」ではなく、管理者がメール所有を確認した記録です。`"true"`という文字列ではなく真偽値を使います。現在のOIDC email mappingはこの属性を`email_verified` claimとして送ります。変更後はアプリ側からSSOをやり直してください。

SMTP導入後は、メール確認Stageを通過したユーザーだけにこの属性を保存するフローへ拡張します。メールStageを追加するだけで独自属性も自動更新されるとは扱わず、未確認／確認済みの双方でテストします。現時点でメール確認フローの自動送信は配備していません。

既存ユーザーを `hub/users.local.json` で管理している場合は、そこに明示した `email_verified: false` が再適用時に優先されます。本人確認後は台帳も整合させます。キー省略時は同じメールの確認済み状態を維持し、メール変更時は未確認へ戻すように修正しました。

## 管理者用の例外: 利用者をコードで追加

```bash
cp hub/users.example.json hub/users.local.json
chmod 600 hub/users.local.json
# ユーザー名・実際のメールアドレス・表示名を編集
sudo .hub-venv/bin/python hub/users.py hub/users.local.json
```

この方法は復旧・既存のコード管理用で、通常の新規利用者は上記の招待を使います。初期パスワードは `runtime/user-bootstrap.json` に保存します。対象本人へ別の安全な経路で渡し、Authentikのユーザー画面で変更してください。再適用で既存パスワードを変更しません。ファイルから行を消すだけではユーザーを削除せず、`active: false` を指定するとAuthentikのアカウントを無効にします。

通常の利用者は `media-users` にだけ所属させます。`homarr-admins` を追加するとHomarrの管理とNetBoxのSSO利用を許可します。SMTPは別途設定が必要です。メール未設定では招待・確認メールを送れません。管理者が登録するメールアドレスを確認してください。KavitaとVaultwardenは確認済みメールを要求します。`email_verified` は初期値falseです。SMTPでの確認フローを組むか、管理者が本人とアドレスを別経路で確認した場合にだけ、対象ユーザーのJSONをtrueへ変更します。未確認のアドレスを一括で確認済みにしません。

## 既存アカウントとの関係

既存のローカル管理者、ファイル、読書履歴、お気に入りは保持します。新しいSSOユーザーへ自動移行しません。NextcloudはOIDCのsubに基づく別ID、Navidromeは `sso_ユーザー名` を使い、既存adminと衝突させません。Vaultwardenも既存ユーザーへのメールアドレスだけによる自動紐付けを無効にしています。

SSOは共通の本人確認基盤を利用する仕組みです。パスワードに加え、構成したパスキーやMFAも利用できます。アプリ固有の権限・セッション・データを一括で同期する機能ではありません。利用停止時に即時遮断が必要なら、Authentikの無効化だけでなく各アプリのセッション失効・ユーザー停止も実施してください。

Vaultwardenでは、初回にマスターパスワードを設定し、保管庫を開くときに入力します。SSOやメールで暗号化キーを代替・復元することはできません。

## 緊急時とモバイルアプリ

ローカル管理者のログインは残しています。Navidromeの緊急用/APIポートはサーバーの `127.0.0.1:14533` です。音楽同期タイマーはこちらを使います。通常のWebアクセスは4533です。MeTubeの内部ポート18081もlocalhost限定です。

SubsonicクライアントはブラウザーのAuthentikログイン画面を処理できないことがあります。Web SSOの検証とモバイルクライアントの検証は別です。利用するクライアントに応じて、専用のアプリ認証とHTTPS接続を別途構成します。

参考: [Nextcloud OIDC](https://docs.nextcloud.com/server/latest/admin_manual/configuration_user/user_auth_oidc.html)、[Kavita OIDC](https://wiki.kavitareader.com/guides/admin-settings/open-id-connect/)、[Authentik](https://docs.goauthentik.io/)。

## 検証記録（2026-09-08）

招待フローの再適用、テスト利用者の登録、一般グループへの所属、1回限りのリンク消費を確認しました。登録POSTへ別メール・確認済み属性・管理者グループを追加しても受け付けず、管理者が指定した招待内容を保持することを確認しています。

Vaultwardenではテスト用の未確認アカウントが拒否され、同じテストアカウントを確認済みにするとSSO識別子経由でマスターパスワード設定画面へ進むことを確認しました。保管庫の作成・保存・拡張／スマホ同期は今回の確認範囲外です。テストのユーザー・招待・空のVaultwarden登録情報は撤去済みです。既存利用者のメール属性・パスワード・保管庫は変更していません。

CA検証ありでissuerとSSO識別子APIの応答を確認し、Vaultwardenコンテナはhealthyです。メール属性の再適用に関する5件のテストも成功しました。
