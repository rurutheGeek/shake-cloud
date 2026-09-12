# NetBoxの初回構築

NetBoxもこのリポジトリから構築します。このディレクトリは旧メディアスタックの配備用です。**新しい基盤の Kubernetes（kubeadm）と AWX 24.6.1 は稼働済み**で、NetBox は services-01 のままです（[配備台帳](../../docs/operations/handover.md)）。

起動順序は **Docker → NetBox → 配備先登録 → NetBox動的インベントリ → アプリ配備** です。NetBox本体を作る初回だけ静的なSSH指定を使用します。

## 同じホストで起動

リポジトリのルートから:

```bash
sudo bash stacks/scripts/install-docker.sh
sudo python3 stacks/netbox/manage.py init
sudo python3 stacks/netbox/manage.py lock
sudo python3 stacks/netbox/manage.py up
```

NetBoxは `http://<ホスト>:8000` です。Ansible の `netbox` ロールで配備すると LAN に公開します（`netbox_bind_address`）。手元だけで試すときは `.env` の `BIND_ADDRESS=127.0.0.1` のまま、`ssh -N -L 8000:127.0.0.1:8000 ubuntu@HOST` で接続します。管理者名の既定はadmin、初期パスワードはstacks/netbox/secrets/superuser_passwordに保存します。既存の管理者パスワード・DB・Secret Key・API pepperは再実行で変更しません。

## Ansibleで別ホストへ構築

```bash
cp platform/ansible/seed.ini.example platform/ansible/seed.ini
# 接続先を編集
ansible-playbook -i platform/ansible/seed.ini platform/ansible/site.yml --tags netbox
```

配備先は/opt/netbox-stack、状態は/srv/netbox-stack/storageです。既存Dockerを使う場合は `-e install_docker=false` を指定します。初回以降の.envは既存設定を保持するため、変更は対象ホストで行います。

## Ansible用の登録

NetBoxでSite、DeviceまたはVirtual Machine、インターフェース、IPアドレスを作成し、Primary IP・Active・media-stackタグを設定します。DeviceではDevice TypeとRoleも必要です。

専用のインベントリ閲覧ユーザーへ必要なモデルのview権限を付与し、そのユーザーのv2 APIトークンを作成します。Write enabledを無効にし、表示された `nbt_<key>.<token>` 全体をplatform/ansible/netbox.envのNETBOX_TOKENへ保存します。NETBOX_AUTH_TYPE=Bearerを使用します。URLは配備先なら `http://<ホスト>:8000`、SSH転送ならhttp://localhost:8000です。

## Terraform用の書き込みアイデンティティ

Ansible動的インベントリが使うトークンは読み取り専用です。Terraformは台帳へ書き込むため、**別のユーザーとトークン**を使います。片方の設定ミスがもう片方の範囲を書き換えないようにするためです。

```bash
sudo python3 stacks/netbox/manage.py seed-terraform
```

`terraform` ユーザーと書き込み可トークンを作り、`dcim`・`virtualization`・`ipam`・`tenancy`・`extras` に対する view/add/change/delete を与えます。superuserにはしません。再実行しても既存トークンは作り直しません。既存の権限が想定と違う場合はエラーで止まり、権限を広げません。

秘密値は `stacks/netbox/secrets/terraform-token.json` に保存されます。`NETBOX_API_TOKEN` に入れる値は、そのファイルの `key` と `token` から `nbt_<key>.<token>` の形に組み立てます。組み立てた値は[SOPS](../../docs/operations/secrets.md)で暗号化して `platform/sops/netbox.sops.yaml` へ置きます。

## タグの語彙

Ansibleのグループ分けはNetBoxのタグを見ます。`platform/ansible/inventory.netbox.yml` が正本です。

| タグ | Ansibleグループ | 用途 |
| --- | --- | --- |
| `media-stack` | `media` | 既存のメディアスタック。**意味を変えない** |
| `managed-by-terraform-admin` | `terraform_managed` | 管理者Terraformが作ったもの |
| `k8s-cp` / `k8s-worker` | `k8s_cp` / `k8s_worker` | Kubernetesノード |
| `identity` | `identity` | Authentikと専用DB |
| `devbox` | `devbox` | 開発VM |
| `edge` / `vpn` / `storage` | 同名 | 公開入口、セルフホストVPN、Garage |
| `lab` | `lab` | 検証・復元ドリル用の使い捨て |

インベントリの絞り込みから `media-stack` タグを外しました。Proxmox上にはメディアスタック以外のホストも載るためです。`hosts: media` と `--limit` の意味は変わりません。

## 永続化とバックアップ

storage/postgresはNetBox専用PostgreSQL 18、storage/media・reports・scriptsはアプリのファイル、storage/queueは永続キューです。アプリ4サービスのstorageとは別です。秘密値はsecretsに保存し、DBと一緒に移行します。キャッシュは再生成します。

```bash
sudo python3 stacks/netbox/manage.py backup --destination /mnt/backup/netbox
```

稼働中のサービスを停止してstate.tar・deployment.tarを作り、元のサービスを再開します。失敗したバックアップは.incompleteのまま残します。復元は新しい空ディレクトリへdeployment.tarを展開し、別の空storageへstate.tarを数値UID/GIDを保持して展開します。.envのSTORAGE_ROOTを修正し、同じCPUアーキテクチャ・固定済みイメージでmanage.py upを実行します。PostgreSQLのメジャー変更には別途DB移行が必要です。バックアップには秘密値を含むため、アクセス制限と暗号化を行ってください。

イメージはlockでdigest固定します。更新時はバックアップ後に `lock --refresh-images` と `up` を実行します。

参照: [NetBox Docker](https://github.com/netbox-community/netbox-docker)、[API認証](https://netboxlabs.com/docs/netbox/integrations/rest-api/)。
