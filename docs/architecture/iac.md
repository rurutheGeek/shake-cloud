# IaCの所有境界

更新日: 2026-09-09。状態: **00-bootstrapのみ実装済み。VM作成以降は未実装**。

[配備・Git管理・ストレージ・復旧](operations.md)の「Gitと構成の所有者」は「**同じオブジェクトをFluxと自作API、または2つのTerraform stateで管理しません**」と定めています。この文書は、その原則をProxmoxの権限とVMIDの分割で**構造として**保証する方法を書きます。運用規約ではなく、権限が無いから触れない、という形にします。

## 誰が何を作るか

| 層 | 道具 | 対象 | 状態の置き場 |
| --- | --- | --- | --- |
| Proxmoxの所有境界 | Terraform `00-bootstrap` | プール、ロール、自動化ユーザー、ACL、cloud imageの取得 | S3互換ストレージ |
| NetBoxの置き場 | Terraform `05-seed` | 最初の1台。NetBoxを使わず静的IP | S3互換ストレージ |
| 基盤VMとIP台帳 | Terraform `10-platform` | NetBoxのVM・IP採番、ProxmoxのVM | S3互換ストレージ |
| ゲストOS | Ansible | ユーザー、SSH、containerd、kubeadm、Compose配備 | 冪等な再実行 |
| クラスタ内の共通基盤・常用アプリ | Flux | Operator、Helm、Kustomize | Gitとクラスタ |
| 利用者が作る動的リソース | 自作クラウドAPI（未実装） | `cloud` プールのVM、関数、バケット、DB | API自身の永続化 |

## 宣言ファイルと機構の分離

実際の値はYAMLに置き、`.tf` は機構だけを持ちます。Terraform・Ansible・テストが同じファイルを読むので、同じ事実が3か所で食い違いません。

| ファイル | 内容 | 読む側 |
| --- | --- | --- |
| `platform/terraform/pools.yaml` | プールとVMID範囲、自動化ユーザーに許すプール | `00-bootstrap`、`10-platform`、テスト |
| `platform/terraform/flavors.yaml` | VMのサイズ。名前は将来のクラウドAPIと共用 | `10-platform`、テスト |
| `platform/terraform/tags.yaml` | NetBoxタグとAnsibleグループの対応 | `10-platform`、テスト |
| `platform/terraform/hosts.yaml` | ホストの宣言。**正本** | `10-platform`、テスト |

`tests/test_platform_inventory.py` が整合を検査します。VMIDが範囲外・重複、未宣言のタグやflavor、`cloud` プールの使用、`automation_pools` への `cloud` の混入、`media` グループ式の変更は、実機へ触る前にここで落ちます。

## VMIDとプールの分割

`platform/terraform/pools.yaml` が正本です。

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

- **stateはK11の外のS3互換ストレージに置きます。** K11は単一SSDなので、そこにstateを置くとディスク1枚の故障で「Terraformが現状を把握できない」状態になります。またK11が停止していてもstateを読める必要があります（`cloud.md`「クラウド停止中も使える場所へ保持」）。現在の実体はCloudflare R2ですが、`backend "s3"` に事業者固有の設定を書いていないので、`cloud.md` が計画しているGarageへ移すときも endpoint と bucket の差し替えだけで済みます。
- ルートモジュールごとに別のstateです（`shake-cloud/<モジュール>/terraform.tfstate`）。`00-bootstrap` は `root@pam`、それ以外は `terraform@pve` で実行します。
- 自作APIはTerraform stateを共有しません。APIは自分のジョブ・バックエンドIDを持ちます。
- 利用者側の `homelab` Provider のstateは各自の開発VM上に置きます。クラウドが停止していても手元に残る場所である必要があります。

## 秘密値

Proxmox・NetBoxの資格情報は[SOPS+age](../operations/secrets.md)で暗号化してGitに置きます。**Terraformのstateはこれとは別の話です。** stateには復号後の値が平文で入り得ます。取り扱いは[Terraformの実行手順](../operations/terraform.md)を参照してください。
