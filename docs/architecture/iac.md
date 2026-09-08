# IaCの所有境界

更新日: 2026-09-09。状態: **00-bootstrapのみ実装済み。VM作成以降は未実装**。

[配備・Git管理・ストレージ・復旧](operations.md)の「Gitと構成の所有者」は「**同じオブジェクトをFluxと自作API、または2つのTerraform stateで管理しません**」と定めています。この文書は、その原則をProxmoxの権限とVMIDの分割で**構造として**保証する方法を書きます。運用規約ではなく、権限が無いから触れない、という形にします。

## 誰が何を作るか

| 層 | 道具 | 対象 | 状態の置き場 |
| --- | --- | --- | --- |
| Proxmoxの所有境界 | Terraform `00-bootstrap` | プール、ロール、自動化ユーザー、ACL | ローカルstate |
| 基盤VMとIP台帳 | Terraform `10-platform` | NetBoxのVM・IP採番、ProxmoxのVM | ローカルstate |
| ゲストOS | Ansible | ユーザー、SSH、containerd、kubeadm、Compose配備 | 冪等な再実行 |
| クラスタ内の共通基盤・常用アプリ | Flux | Operator、Helm、Kustomize | Gitとクラスタ |
| 利用者が作る動的リソース | 自作クラウドAPI（未実装） | `cloud` プールのVM、関数、バケット、DB | API自身の永続化 |

## VMIDとプールの分割

`platform/terraform/00-bootstrap/pools.tf` が正本です。

| VMID | プール | 所有者 | 用途 |
| --- | --- | --- | --- |
| 100–399 | `platform` | 管理者Terraform | public-edge、vpn-01、identity、home-assistant、storage-s3、k8s、game |
| 400–499 | `dev` | 管理者Terraform | 開発VM。利用者は電源とコンソールのみ |
| 900–999 | `lab` | 管理者Terraform | 検証・復元ドリル。使い捨て |
| 5000–5999 | `cloud` | 自作クラウドAPI（将来） | 利用者がAPI・Providerで作るVM |

`cloud` プールは**空のまま先に作ります**。枠を予約しておくことで、後から自作APIを載せるときにVMIDの再採番や既存VMの移動が要りません。

## ロールとトークン

| ロール | 与える権限 | 割り当て先 | 到達範囲 |
| --- | --- | --- | --- |
| `TerraformAdmin` | VM.\*（Config含む）、Pool.Audit | `terraform@pve` | `/pool/platform`、`/pool/dev`、`/pool/lab` |
| `TerraformStorage` | Datastore.Audit / AllocateSpace / AllocateTemplate | `terraform@pve` | `/storage` |
| `DevVMOperator` | VM.Audit、VM.PowerMgmt、VM.Console | `dev-a@pve`、`dev-b@pve` | `/vms/400`、`/vms/401` |
| `CloudApiOperator` | TerraformAdminと同等 | **未割り当て**（将来の `cloudapi@pve`） | `/pool/cloud` のみ |

`terraform@pve` は `/pool/cloud` に権限を持ちません。逆に将来の `cloudapi@pve` は `/pool/platform` に権限を持ちません。**利用者向けの削除APIが基盤VMへ届かないことを、ACLの形で保証します。**

`DevVMOperator` に `VM.Config.*` を含めないのは意図的です。電源とコンソールは自由に使えますが、CPU・RAM・ディスク・NICの正本はTerraformのままです。利用者の操作でIaCと実機が乖離しません。これは開発VMの中で何をしてよいかの制限ではありません。VMの外側の形だけを固定します。

## モジュールの入力を将来のAPIと揃える

[最小クラウドとTerraform Provider](cloud.md)の `homelab_instance` は image・CPU・RAM・disk・network を受け取ります。`platform/terraform/modules/managed-host` の入力を同じ形にして、`flavors.yaml`（`small` など）の名前も共用します。

**将来のGo APIはこのモジュールを呼びません。** APIはProxmox APIを直接叩きます。揃えるのは入力の形だけで、TerraformをAPIの内側に隠しません。隠すと、APIの障害時にTerraformも使えなくなります。

## stateの分離

- `00-bootstrap` と `10-platform` は別のstateです。前者は `root@pam`、後者は `terraform@pve` で実行します。
- 自作APIはTerraform stateを共有しません。APIは自分のジョブ・バックエンドIDを持ちます。
- 利用者側の `homelab` Provider のstateは各自の開発VM上に置きます。クラウドが停止していても手元に残る場所である必要があります。

## 秘密値

Proxmox・NetBoxの資格情報は[SOPS+age](../operations/secrets.md)で暗号化してGitに置きます。**Terraformのstateはこれとは別の話です。** stateには復号後の値が平文で入り得ます。取り扱いは[Terraformの実行手順](../operations/terraform.md)を参照してください。
