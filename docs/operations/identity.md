# 認証基盤（identity サービス・Authentik）

identity VM の Authentik は、**利用者の共通アカウント（誰であるかの確認）** を担います。クラウドポータル・Terraform・CLI はこの Authentik を OIDC の本人確認先にし、利用者を作りません。設計の背景は[ネットワーク・公開範囲・SSO](../architecture/network-auth.md)、クラウド側の境界は[クラウドAPIの構築](cloud.md#3-17)を参照してください。

- **入口:** `https://auth.apextox.dpdns.org`（`:9000` と `:9443` は 127.0.0.1 に閉じています）
- **VM:** identity（VMID 110、192.168.10.204）。Kubernetes の外に置き、クラスタ更新中でもログインできます。
- 作業機の検証用 `stacks/hub` の Authentik とは**別物**です。そこから移行していません。

## 配備

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/identity.yml'
```

- 秘密値（DB パスワード、secret key、`akadmin` の初期パスワード、ブートストラップトークン、OIDC クライアント `cloud` の秘密）は**すべて VM 上で自動生成**され、`/opt/identity-stack/secrets/` に置かれます。再実行しても作り直しません。
- 配備のたびに `manage.py configure` が走り、**冪等**に次を整えます。
  - グループ `users`・`admins`（`akadmin` は `admins`）
  - OIDC クライアント `cloud`（`sub` は `user_uuid`。プロバイダを作り直しても利用者の同一性が変わらないため）
  - OIDC クライアント `netbox`（NetBox の SSO。秘密だけは SOPS の `NETBOX_OIDC_CLIENT_SECRET` を正本にする。[NetBox の使い方](netbox.md#sso共通ログイン)）
  - 招待専用エンロールフロー `cloud-invitation-enrollment`（[利用者の招待](#利用者の招待管理者)）
  - パスワード再設定フロー `default-recovery-flow` と Email 認証器（[パスワード・パスキーの復旧](#パスワードパスキーの復旧)）
- 2 回目の実行はすべて `OK:` になります。

## 管理者の資格情報とバックアップ

| もの | 場所 |
| --- | --- |
| `akadmin` の初期パスワード | `/opt/identity-stack/secrets/bootstrap_password` |
| API 用ブートストラップトークン | `/opt/identity-stack/secrets/bootstrap_token` |
| OIDC クライアント `cloud` の秘密 | `/opt/identity-stack/secrets/oidc-cloud.json` |

取得例（`akadmin` で管理画面に入れないときの初期パスワード確認）:

```bash
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.204 \
  sudo cat /opt/identity-stack/secrets/bootstrap_password
```

`oidc-cloud.json` は **SOPS へ複製しません。** 正本はこの VM にあり、配備のたびに `cloud.yml` が直接写します。2 か所に持つと、Authentik 側で作り直したときに食い違います。

バックアップは VM 上で `manage.py backup`（`storage/` と配備ファイルを 1 つの tar にまとめる。既定 `backups/`）を取ります。手順と保管先は[バックアップと復旧](../architecture/operations.md#バックアップと復旧)に沿って決めます。

## グループ

`configure.py` が作るのは2つです。**アプリへの許可はこの2つに紐づきます。**

| グループ | 何のため | 主なアプリでの扱い |
| --- | --- | --- |
| `users` | 一般利用者 | クラウド、NetBox（閲覧のみ） |
| `admins` | 管理者 | クラウド（全体操作）、NetBox（superuser）、AWX など |

- `akadmin` は `admins` に入ります。**招待で作られた人は `users` に入ります。**
- 管理者の追加や既存ユーザーの移行は GUI で行います（**Directory → Users → 対象 → Groups**）。
- **グループ名を変えたら、既存ユーザーを新しいグループへ入れ直してください。** 旧グループを消しただけでは移りません。2026-09-12 の改名（`cloud-users`/`cloud-admins` → `users`/`admins`）で実際に起きました。旧 `cloud-users` にいた `ruruthegeek` と `shunyazhiyuan97` は**どちらも利用者アカウント**なので `users` へ移して解決しています（管理者は `akadmin` だけ。Authentik のイベントログの `add_user` 記録で確認）。
- `gaming-users` / `gaming-admins` は、ゲームポータルが `game_identity` スコープの `groups` クレームで使うため残しています。

## 利用者の招待（管理者）

**利用者の招待は、クラウド API でもポータルでもありません。** 認証基盤の管理者の仕事です。クラウドは、招待で作られた利用者が `users` に入っていることを前提に動きます。クラウド側に「招待」という資源は持たせません。

### GUI で発行する（ふつうはこちら）

管理画面 → **Directory → Invitations → New Invitation**。

1. **with Existing Enrollment Flow...** を選び、`cloud-invitation-enrollment` を指定します（招待ステージが付いた登録フローだけが並びます）。
2. **Custom attributes** に `{"username": "alice", "email": "alice@example.org"}` を入れます（`name` も付けられます）。ここで入れた値が本人のユーザー名・メールになります。
3. **Single use** を有効にし、**Expires** を設定して作成します。
4. 招待を展開して **Link to use the invitation** を **Copy Link** するか、**Send via Email**（Authentik の SMTP。現在は Gmail で送信可）で送ります。

グループは招待の属性では指定できず、**フローの User Write ステージ**（既定 `users`）で決まります。管理者にしたい人は、作成後に **Directory → Users → 対象 → Groups** で `admins` を追加します。

### CLI で発行する（任意）

日本語の招待メールとリンクの 0600 保存まで自動化したいときは、identity VM の `stacks/identity/invitations.py` を使います。フロー `cloud-invitation-enrollment` を管理し、`configure` は配備でも毎回走ります。

| 操作 | 呼び方（identity VM、または `stacks/identity/` で） |
| --- | --- |
| フローを作る・直す（冪等） | `python3 invitations.py configure [--group users]` |
| 招待を発行してリンクを保存・送信 | `python3 invitations.py invite --username <name> --email <mail> [--name <表示名>] [--email-owner-confirmed] [--no-email]` |
| 一覧（未使用・期限・使用済み） | `python3 invitations.py list` |
| 失効（リンクファイルも消す） | `python3 invitations.py revoke --name <名前>` |

identity VM での実行例:

```bash
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.204
sudo python3 /opt/identity-stack/invitations.py invite \
  --username alice --email alice@example.org --name '利用者A'
sudo python3 /opt/identity-stack/invitations.py list
```

設計上のポイント:

- **1 回限り・24 時間有効。** リンクを開いても登録を終えなかった場合は期限切れになります。Authentik の Invitation Stage は**リンクを開いた時点で消費する**ため、途中でブラウザーを閉じた場合も `revoke` して再発行します。
- **ユーザー名・メール・所属グループは招待が固定します。** 登録画面で入力できるのはパスワード（12 文字以上）だけです。管理者グループを自己指定する入口はありません。
- **グループの既定は `users`。** 他のサービス（メディアなど）へも招待するようになったら `configure --group` と宛先で分けます。1 つのフローに複数グループを持たせず、サービスごとに分ける方針です。
- **メールで送れます。** `.env` に `SMTP_HOST`・`SMTP_FROM`（必要なら `SMTP_USERNAME`/`SMTP_PASSWORD`/`SMTP_PORT`/`SMTP_SECURITY`）があれば、`invite` は招待メールを SMTP（現在は Gmail `shake.notify@gmail.com`）へ投げます。無ければ送らず、リンクを `runtime/invitations/<name>.json`（0600）に保存して管理者が別経路で渡します。`--no-email` で送信を止められます。トークンは端末の履歴やログに出しません（[SMTPとメール送信](smtp.md)）。
- **メール所有の確認は明示したときだけ。** 管理者が本人とアドレスを別経路で確認済みの場合に `--email-owner-confirmed` を付けると `email_verified=true` になります。付けなければ未確認のままです。

## 利用者本人の登録

1. 招待リンク（`https://auth.apextox.dpdns.org/if/flow/cloud-invitation-enrollment/?itoken=…`）を開きます。別アカウントでログイン済みなら、ログアウトするか別ブラウザープロファイルを使います。
2. 自分専用のパスワード（12 文字以上）を設定します。
3. **利用者設定からパスキーと「メール」確認コードを登録します。** 片方だけだと、失ったときに詰まります（次節）。
4. ポータルなど目的のアプリを開き、SSO でログインします。

## パスワード・パスキーの復旧

ログインは `識別 → パスワード → 認証器の検証` の順です。検証段階は `webauthn`・`totp`・`static`（バックアップコード）・`email` を受け付けます。**認証器を 1 つも登録していない利用者はこの段階を素通り**しますが、**パスキーを登録した人は失くしても検証段階が残る**ため、パスワードを再設定しただけでは戻れません。

`configure.py` が用意する 2 つの経路:

- **メール確認コード**（`default-authenticator-email-setup`）: 利用者設定から登録できる第二の認証器。**パスキーを失ったときの本線**です。SMTP で届くコードで検証段階を通過できます。
- **パスワード再設定**（`default-recovery-flow`）: ログイン画面の「パスワードを忘れた」から、識別 → メール → 新しいパスワード → ログインの順に進みます。これは**パスワードだけ**を戻すので、認証器を登録済みの人は上記のメール確認コードか、管理者の操作が別途必要です。

`akadmin` の復旧先は `.env` の `SMTP_FROM`（`ADMIN_EMAIL` で上書き可）です。**すべての認証器を失った**場合は、次のいずれかを使います。

1. 管理画面: **Directory → Users → 対象 → MFA Devices** で失ったデバイスを削除する。デバイスが無くなれば検証段階は素通りし、パスワードで戻れます。
2. ブートストラップトークンで API を直接叩く:
   ```bash
   GET  /api/v3/authenticators/admin/webauthn/?user=<user_pk>
   DELETE /api/v3/authenticators/admin/webauthn/<device_pk>/
   ```
3. オフライン時（API も管理画面も使えない）: identity VM で
   ```bash
   docker compose -f /opt/identity-stack/compose.yaml exec worker ak shell
   # WebAuthnDevice.objects.filter(user__username='akadmin').delete()
   ```

実機確認（2026-09-12）: `configure` を流し、`akadmin` の復旧先設定・Email 認証器フロー・復旧フロー作成を確認。復旧フローの executor で識別から `ak-stage-email` まで到達し、**Gmail から復旧メールが実送信**されることを確認しました。2 回目は全項目 `OK` で冪等です。

## パスキーだけでログインする（パスワードレス）

**有効（2026-09-12）。** `configure.py` が認証フローの識別ステージの **WebAuthn Authenticator Validation Stage** を同じフローの検証ステージへ向けると、ログイン画面でブラウザーのパスキー自動入力（条件付き UI）が出ます。パスキーで入ったあとは Authentik の既定ポリシー（`auth_method == auth_webauthn_pwl`）がパスワード段階と検証段階を飛ばすので、パスワードなしでログインできます。設定は識別ステージの 1 か所だけで、再適用で戻ります。

条件と注意:

- `auth.apextox.dpdns.org` の **HTTPS**、ブラウザーの conditional UI 対応、登録時と同じホスト名。
- 登録済みパスキーが **discoverable credential（resident key）** であること。そうでなければ自動入力は出ません。
- **パスワード経路は残します。** パスキーを失ったときは前節のメール復旧が使えます。

GUI で切り替えるなら **Flows and Stages → Stages → 識別ステージ → WebAuthn Authenticator Validation Stage** です。
