# Garage（S3互換オブジェクトストア）

更新日: 2026-09-11。状態: **構築済み・実クライアントで確認済み**。バケットとS3キーのAPI（クラウドAPI Phase 7）はこれから。

S3を自作クラウドの一部にするための土台です。Garageを **storage-s3 VM（VMID 130、192.168.10.206）** に単一ノードで置きます。

## 1. 実体

| | 値 |
| --- | --- |
| VM | `storage-s3`（VMID 130、platform プール、2 vCPU / 1 GiB / OS 16GiB） |
| データ | 専用ディスク 32GiB（`/srv/garage`。OS と分けてある） |
| 版 | Garage v2.4.1（x86_64-musl。バイナリの sha256 をロールに固定） |
| S3 API | `http://192.168.10.206:3900`、region `garage` |
| 管理API | `http://192.168.10.206:3903`（Bearerトークン） |
| replication factor | **1（冗長性なし）** |

**唯一の保存先・唯一のバックアップにはしません。** 単一ノード・RF1 なので、ディスクが壊れればデータは失われます。

## 2. 宣言と配備

- VMは `platform/terraform/hosts.yaml` の `storage-s3`（`10-platform` が作成。データディスクは `managed-host` の `data_disk_gib`）。
- 中身は Ansible ロール `platform/ansible/roles/garage` と `platform/ansible/garage.yml`。

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook \
     -i platform/ansible/inventory.netbox.yml platform/ansible/garage.yml'
```

ロールが行うこと:

1. データディスクを ext4 でフォーマット（初回だけ）し、UUID で `/srv/garage` へマウント。
2. Garage バイナリを版とチェックサムを固定して設置。
3. 設定 `/etc/garage.toml` を**初回だけ**書く（`rpc_secret`・管理トークンはそこで生成。以降は上書きしない）。
4. systemd ユニットで `garage server --single-node`（単一ノードのレイアウトを自動で割り当てる）。

再実行は `changed=0` です。

**はまりどころ**: Terraform の `proxmox_virtual_environment_vm` は `agent { enabled = true }` のとき、ゲストの qemu-guest-agent が応答するまで Read で待ちます。Debian cloud image には入っていないので、**VM を作った直後の plan/apply は止まったように見えます**。`common` ロール（`garage.yml` に含まれる）が入れてくれます。先に Terraform を流して止まったら、Ansible を一度流してから再 plan してください。

## 3. 確認

```bash
# ホスト上で
sudo garage -c /etc/garage.toml status

# 実クライアント（awscli）で。鍵はください（下記）
export AWS_ENDPOINT_URL='http://192.168.10.206:3900' AWS_DEFAULT_REGION='garage'
export AWS_ACCESS_KEY_ID='<key id>' AWS_SECRET_ACCESS_KEY='<secret>'
aws s3 cp hello.txt s3://<bucket>/hello.txt
aws s3 ls s3://<bucket>/
aws s3 cp s3://<bucket>/hello.txt -
aws s3 rm s3://<bucket>/hello.txt
```

2026-09-11 に、Garage で作ったバケットとキーに対し、awscli で **PUT・LIST・GET・削除**がすべて通り、削除後に一覧が空になることを確認しました。

## 4. セキュリティとアクセス

- **S3 API は SigV4 署名で認証**します。ブラウザ用の Forward Auth は挟みません。
- **管理API は Bearer トークン**です。`/etc/garage.toml` の `admin_token` は全権なので、クラウドAPIには**用途別に絞った管理トークン**（`garage admin-token create --scope ...`）を渡す予定です。
- いまは管理系と同じ物理LANに開いています。**VLAN分離が済むまで、利用者VMからも S3 API・管理API に届きます。** 管理APIの到達先をクラウドAPIだけに絞るのは VLAN 切替後です。
- データのバックアップは Garage 自身を唯一の保存先にせず、別ディスク・別機器へ取ります（[配備・Git管理・ストレージ・復旧](../architecture/operations.md)）。
