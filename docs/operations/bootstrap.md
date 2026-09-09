# 初回セットアップの順番

更新日: 2026-09-09。状態: **手順1〜7は実機（PVE 9.2.2）で確認済み**。

ゼロから最初のVMまでの**順序と理由**だけを書きます。操作そのものはコードにあります。詳細は[Terraformの実行](terraform.md)、[秘密値の管理](secrets.md)、[IaCの所有境界](../architecture/iac.md)へ。

## 0. 作業機

**Debian系のLinux**（Debian / Ubuntu）を前提にします。導入は[開発参加ガイド](../onboarding.md)の手順1にまとめてあります。要るのは Terraform 1.10以降、SOPS、age、Ansible、それに NetBox 動的インベントリ用の `pynetbox` と `pytz` です。

## 1. 鍵と資格情報

```bash
age-keygen -o ~/.config/sops/age/keys.txt
cp .sops.yaml.example .sops.yaml   # age1... の公開鍵へ置き換える
```

**`.sops.yaml` はリポジトリのルートに置きます。** sopsはカレントから上へ辿って設定を探すので、他の場所では見つかりません。`path_regex` は絶対パスに対して評価されます。

sopsが鍵を見つけられない場合は、環境変数 `SOPS_AGE_KEY_FILE` で鍵の場所を指定します。

雛形をコピーして実値を入れ、**必ず暗号化してから**次へ進みます。暗号化を忘れてコミットしようとすると `tools/check-publication.py` が止めます。

| ファイル | 中身 | どこで使うか |
| --- | --- | --- |
| `platform/sops/cloudflare.sops.yaml` | Cloudflare APIトークン | バケット作成だけ |
| `platform/sops/s3.sops.yaml` | S3のアクセスキー・エンドポイント・バケット名 | 全モジュールのstate |
| `platform/sops/proxmox-root.sops.yaml` | `root@pam` のAPIトークン | `00-bootstrap` だけ |
| `platform/sops/proxmox.sops.yaml` | `terraform@pve` のトークン | それ以外のモジュール |
| `platform/sops/netbox.sops.yaml` | NetBoxの書き込みトークン | `10-platform` |

`proxmox.sops.yaml` と `netbox.sops.yaml` の中身は、後の手順の出力から作ります。最初に用意するのは上2つと `proxmox-root` です。

## 2. Proxmox側の最初の資格情報

PVEの画面（データセンター → 権限 → APIトークン）で `root@pam` のトークンを作り、**「特権の分離」のチェックを外します**。`00-bootstrap` が作る `terraform@pve` は自分自身を作れないため、この1段だけ上位の資格情報が要ります。

あわせてPVEのWebシェルから、管理端末の公開鍵を `/root/.ssh/authorized_keys` へ登録します。鍵認証を作るために鍵認証は使えないので、ここも1回だけ手作業です。

## 3. state置き場を作る

```bash
tools/tf state-store apply
```

バケットを手で作りません。このモジュールだけ **stateがローカル**です（自分が作る先に自分のstateは置けないため）。事業者固有なのもここだけで、他のモジュールの `backend "s3"` は素のS3です。

出力の `bucket_name` と `endpoint` を `s3.sops.yaml` へ入れて暗号化します。

## 4. 実機の棚卸し

先に手動でSSHし、**ホスト鍵の指紋をProxmox側の実物と突き合わせてから** `yes` と答えます。中間者攻撃を検知する唯一の機会なので、ここは自動化しません。

```bash
cp platform/ansible/pve.ini.example platform/ansible/pve.ini
ansible-playbook -i platform/ansible/pve.ini platform/ansible/site.yml --tags survey
```

`.survey/<ホスト名>.md` の冒頭にある「Terraformへ転記する値」を埋めてから次へ進みます。`snippets` を持つストレージが無い場合、cloud-initの追加設定は投入できません。

## 5. Proxmoxの所有境界

```bash
tools/tf 00-bootstrap apply
```

プール・ロール・ACL・cloud imageの取得・開発VMのAPIトークンを作ります。出力の `automation_token_value` は `user@realm!id=uuid` の**完全な形**なので、そのまま `proxmox.sops.yaml` へ入れます（接頭辞を足すと二重になり401になります）。

**完了条件:** 2回目の `plan` が `No changes`。`terraform@pve` から `cloud` プールを操作できないこと。

## 6. 最初の1台とNetBox

`10-platform` はNetBoxにIPを採番させる設計なので、NetBox自身の置き場はそれでは作れません（鶏と卵）。`05-seed` だけNetBoxを使わず静的IPで1台作ります。

```bash
tools/tf 05-seed apply
```

Debianのcloud imageには `qemu-guest-agent` が無く、Terraformはエージェントの応答を待つので**applyが待ち状態になります**。別のシェルから流すと待ちが解けます。

```bash
cp platform/ansible/seed.ini.example platform/ansible/seed.ini
ansible-playbook -i platform/ansible/seed.ini platform/ansible/site.yml --tags guests
ansible-playbook -i platform/ansible/seed.ini platform/ansible/site.yml --tags netbox
```

## 7. 基盤VMと利用者

NetBoxは `services-01` のlocalhostにしか出ていないので、SSHポート転送を張ってから実行します。

```bash
ssh -N -L 8001:127.0.0.1:8000 debian@<services-01のIP>
tools/tf 10-platform apply
ansible-playbook -i platform/ansible/pve.ini platform/ansible/site.yml --tags pve-users
```

`hosts.yaml` に書いたVMがNetBoxの採番付きで作られ、開発VMのパスワードが設定されます。利用者へ渡す値は `tools/tf 00-bootstrap output -json dev_credentials` と `sops --decrypt platform/sops/pve-users.sops.yaml` から取り出します。

**完了条件:** `plan` が `No changes`、`ansible-playbook` が `changed=0`、利用者が自分のVMだけを見られること。

## 残っている手作業

**コードで管理できるものはすべてコードにします。** ここに列挙したものが現時点で残っている手作業のすべてです。この表を増やさないこと、そして「未」を減らしていくことが方針です。

| 手作業 | なぜ残っているか | コード化 |
| --- | --- | --- |
| Cloudflare APIトークンの発行 | **APIを叩くためのキーは、APIでは作れません。** どこかで一度だけ人が発行する必要があります。R2バケット自体は `platform/terraform/state-store` が作ります | 原理的に不可 |
| Proxmoxホストへの初回SSH公開鍵の登録 | 同じ理由。鍵認証を作るために鍵認証は使えません。PVEのWebシェルから1回だけ | 原理的に不可 |
| SSHホスト鍵の指紋確認 | 中間者攻撃を検知する唯一の機会です。自動承認すると確認の意味がなくなります | **意図的に自動化しません** |
| age鍵の生成と保管場所の決定 | 生成自体はスクリプト化できますが、秘密鍵をどこに何個置くかは人が決めます | 生成は可・未 |
| Proxmox `root@pam` トークンの発行 | SSHが通れば `pveum` で作れます | 可・**未** |
| ~~`dev-a@pve` / `dev-b@pve` のパスワードとAPIトークン~~ | **コード化済み。** トークンは `00-bootstrap`、パスワードは `platform/ansible/site.yml --tags pve-users`（Proxmoxが `/access/password` をAPIトークンで受けないため、SSH経由の `pveum`） | 済 |
| 棚卸し結果を `terraform.tfvars` へ転記 | `.survey/` の出力から生成できます | 可・**未** |
| NetBoxの読み取り専用アイデンティティ | `manage.py seed` はありますが `media-stack` タグ固定なので小改修が要ります | 可・**未** |
| NetBoxへのSSHポート転送 | systemdユニットかスクリプトにできます | 可・**未** |

「原理的に不可」と「意図的に自動化しません」以外は、順次コードへ移します。手順書に手作業を書き足して済ませません。

## つまずいたときの対応表

| 症状 | 原因 | 対応 |
| --- | --- | --- |
| stateの移行で `NoSuchBucket` | バケット名かエンドポイントの誤り | `s3.sops.yaml` の `TF_STATE_BUCKET` と `AWS_ENDPOINT_URL_S3` を確認 |
| `config file not found, or has no creation rules` | `.sops.yaml` がルートに無い | ルートへ置く |
| `no matching creation rules found` | `path_regex` が区切り文字に一致しない | `platform[\\/]sops[\\/]` を使う |
| `Failed to get the data key required to decrypt` | sopsが秘密鍵を見つけられない | `SOPS_AGE_KEY_FILE` を設定してシェルを開き直す |
| `Host key verification failed` | ホスト鍵が未登録 | 指紋を突き合わせてから手動SSHで登録 |
| `invalid privilege 'VM.Monitor'` | PVEの版で廃止された権限 | 棚卸しの権限一覧を見て `platform_admin_privileges` を直す |
| APIが `401` を返す | トークン文字列が二重になっている | `output -raw automation_token_value` は完全な形。接頭辞を足さない |
| 権限があるはずなのに一覧が空 | トークンの「特権の分離」が有効 | `pveum user token modify <user> <id> --privsep 0` |
| `Permission check failed (/sdn/zones/.../vmbr0, SDN.Use)` | PVE 8.2以降はbridge割り当てにSDN.Useが要る | `00-bootstrap` の `sdn_acl_path` を実機のゾーン名に合わせる |
| イメージ取得が `Permission check failed` | URLメタデータAPIは `/` の権限を要求する | 取得は `00-bootstrap`（root@pam）で行う。`terraform@pve` では実行しない |
| `terraform apply` がVM作成後に戻ってこない | cloud imageに qemu-guest-agent が無い | 別シェルで `site.yml --tags guests` を流す。エージェントが上がれば待ちが解ける |
| Ansibleが `world writable directory` と言う | リポジトリが誰でも書ける場所にある | `ansible.cfg` が無視される。`ANSIBLE_CONFIG` を明示するか、パーミッションを直す |
| `UNPROTECTED PRIVATE KEY FILE` | 秘密鍵のパーミッションが緩い | `chmod 600` する |
