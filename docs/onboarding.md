# 開発参加ガイド

更新日: 2026-09-09。状態: **本文の手順は実機で確認済み**。

開発VMを使い始めるまでの案内です。**必要なのは SSH クライアントとブラウザだけ**で、手元の作業機に何かを入れる必要はありません。

基盤側の作業（Terraform / Ansible / NetBox / 秘密値の管理）はこの文書の範囲外です。そちらは[初回セットアップの順番](operations/bootstrap.md)と[IaCの所有境界](architecture/iac.md)にあります。

## 読む順番

1. **[共通ログインの使い方](services/identity.md)** — 招待を受けてアカウントを作り、パスキーを登録します（`users` グループ）。
2. **[接続先一覧](operations/urls.md)** — クラウド・AWX・NetBox・ドキュメントの URL。
3. **この文書** — 開発VMへの入り方・鍵・電源。
4. **[開発VMの使い方](services/devvm.md)** — VM の詳細と `tools/devvm`。
5. **[クラウドの使い方](services/cloud.md)** — ポータル・アクセスキー・CLI・Terraform で VM/S3/DB/関数を作る。
6. **[shakecloud CLI](operations/cli.md)** と **[Terraform Provider](operations/terraform-provider.md)** — 開発で使う道具。
7. **[サービスの置き場所とクラウドVMでの作り方](operations/services.md)** — 開発コードをどこに置くか。

設計・進捗（[IaCの所有境界](architecture/iac.md)・[配備台帳](operations/handover.md)）は開発には必須ではありません。

## 1. 使えるもの

ミニPC1台（Ryzen 9 8945HS / 61GiB RAM / 1TB NVMe）の Proxmox VE 上です。

| 名前 | IP | 用途 |
| --- | --- | --- |
| dev-a | 192.168.10.202 | 開発VM |
| dev-b | 192.168.10.203 | 開発VM |

中身は Debian 13。Terraform・Docker・git・age が入っています。ホームディレクトリの `~/tf` は各自の作業場所です。

Proxmox の画面は **`https://pve.apextox.dpdns.org:8006`** です（Let's Encrypt 証明書）。IP 直（`https://192.168.10.126:8006`）は名前が合わず警告が出ます。

## 2. 入る

**ログインパスワードは構成管理者から受け取ってください。** ユーザー名は `debian` です。

```bash
ssh debian@192.168.10.203
```

`192.168.10.126:22` に届く場所からなら、Proxmox ホストを踏み台にして入れます。`~/.ssh/config` に書いておくと `ssh dev-b` だけで済みます。

```
Host pve-jump
  HostName 192.168.10.126
  User root

Host dev-b
  HostName 192.168.10.203
  User debian
  ProxyJump pve-jump
```

VS Code の Remote-SSH もこの設定をそのまま使います。

`192.168.10.0/24` はNATの内側です。外から届かせる方法はまだ決まっていません（[VPNの比較](architecture/vpn.md)を検討中）。

## 3. 公開鍵で入れるようにする

パスワードを毎回打たずに済みます。手元の作業機で鍵を作り、VMへ登録します。

鍵がまだ無ければ作ります。実行場所: 手元の作業機

```bash
ssh-keygen -t ed25519
```

登録します。パスワードを1回だけ聞かれます。実行場所: 手元の作業機

```bash
ssh-copy-id debian@192.168.10.203
```

`ssh-copy-id` が無い環境なら同じことを手で行います。

```bash
cat ~/.ssh/id_ed25519.pub | ssh debian@192.168.10.203 "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

次から鍵で入れます。

```bash
ssh debian@192.168.10.203
```

この方法で足した鍵は、VMを作り直すと消えます。作り直しても残したい場合は構成管理者へ渡してください。VM作成時に配る鍵として登録されます。

## 4. 起動と停止

開発VMは自動起動しません（`onboot: false`）。止まっているとSSHで入れないので、ブラウザから起動します。

`https://192.168.10.126:8006` を開き、Realm に「Proxmox VE authentication server」を選んでログインします。ユーザー名とパスワードは構成管理者から受け取ってください。自分のVMだけが一覧に出ます。

| ボタン | 動作 |
| --- | --- |
| Start | 起動 |
| Shutdown | 正常終了。**通常の停止はこれ** |
| Stop | 電源を切る。応答しないときだけ |
| Reboot | 正常な再起動 |
| Console | 画面に直接つなぐ。SSHで入れなくなったときの復旧用 |

CLIから操作したい場合は、リポジトリの `tools/devvm` が同じことをします。使うには Proxmox の API トークンが要るので、必要なら構成管理者へ言ってください。必須ではありません。

## 5. 今後

開発VM（dev-a / dev-b）はいまも構成管理者が作って渡します。**自分用のサービスVM・S3・DB・関数が欲しくなったら、クラウドポータルから自分で作れます**（[クラウドの使い方](services/cloud.md)）。設計は[最小クラウドとProvider](architecture/cloud.md)にあります。

## 6. 詰まったら

| 症状 | 見るところ |
| --- | --- |
| SSHがつながらない | VMが止まっている可能性。ブラウザから Start する |
| `Permission denied` | ユーザー名は `debian`。パスワードは構成管理者へ確認 |
| SSHで入れなくなった | ブラウザの Console から入って直す |
| ブラウザが証明書を警告する | IP 直で開いていないか確認する（`pve.apextox.dpdns.org` を使う） |
| 自分のVMが一覧に出ない | ログインした利用者に紐づくVMだけが見える。構成管理者へ確認 |
