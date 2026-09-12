# IaCの所有境界

更新日: 2026-09-11。状態: **00-bootstrap・10-platform は実機へ適用済み。クラウドAPI は Phase 4（ボリューム・セキュリティグループ）まで実装済み・実機検証済み**。

[配備・Git管理・ストレージ・復旧](operations.md)の「Gitと構成の所有者」は「**同じオブジェクトをFluxと自作API、または2つのTerraform stateで管理しません**」と定めています。この文書は、その原則をProxmoxの権限とVMIDの分割で**構造として**保証する方法を書きます。運用規約ではなく、権限が無いから触れない、という形にします。

## 誰が何を作るか

| 層 | 道具 | 対象 | 状態の置き場 |
| --- | --- | --- | --- |
| stateの置き場 | Terraform `state-store` | S3互換バケット | **ローカル**（自分が作る先に自分を置けないため） |
| Proxmoxの所有境界 | Terraform `00-bootstrap` | プール、ロール、自動化ユーザー、ACL、cloud imageの取得 | S3互換ストレージ |
| NetBoxの置き場 | Terraform `05-seed` | 最初の1台。NetBoxを使わず静的IP | S3互換ストレージ |
| 基盤VMとIP台帳 | Terraform `10-platform` | NetBoxのVM・IP採番、ProxmoxのVM | S3互換ストレージ |
| ゲストOS | Ansible | ユーザー、SSH、containerd、kubeadm、Compose配備 | 冪等な再実行 |
| クラスタ内の共通基盤・常用アプリ | Flux | Operator、Helm、Kustomize | Gitとクラスタ |
| 利用者が作る動的リソース | 自作クラウドAPI（**実装済み・実機検証済み: VM の作成・電源操作・削除、IP の採番、イメージのアップロード、SSH鍵、Webコンソール、ボリューム、セキュリティグループ、既存VMの引き取り。未実装: バケット**） | `cloud` プールのVM、バケット | API自身の永続化（cloud-01 の PostgreSQL） |

## 宣言ファイルと機構の分離

実際の値はYAMLに置き、`.tf` は機構だけを持ちます。Terraform・Ansible・テストが同じファイルを読むので、同じ事実が3か所で食い違いません。

ファイルは性質で2つに分かれます。**実測**は機械が実機から書き、**決めごと**は人が書きます。どちらも Git に入り、`terraform.tfvars` には何も残しません。

| ファイル | 性質 | 内容 | 読む側 |
| --- | --- | --- | --- |
| `platform/terraform/site.yaml` | **実測** | ノード名、ストレージ名、bridge、ゾーン、prefix、gateway、DNS | 全モジュール、テスト |
| `platform/terraform/pools.yaml` | 決めごと | プールとVMID範囲、自動化ユーザーに許すプール、台帳外VMID | `00-bootstrap`、`10-platform`、テスト |
| `platform/terraform/flavors.yaml` | 決めごと | 基盤VMのサイズとバルーニングの下限。クラウドAPIでは**利用者向けの雛形**として同じ名前を出すが、利用者は値を自由に指定できる（型から選ぶ必要はない） | `10-platform`、クラウドAPI、テスト |
| `platform/terraform/network.yaml` | 決めごと | prefix の中をどう切って配るか（管理用・クラウド用の範囲） | `10-platform`、テスト |
| `platform/terraform/access.yaml` | 決めごと | 基盤VMへ入れるSSH公開鍵。**順序が意味を持つ**（`05-seed` は専用の `seed_ssh_public_keys` を読む） | `05-seed`、`10-platform`、テスト |
| `platform/terraform/images.yaml` | 決めごと | 共有 cloud image のURLとチェックサム | `00-bootstrap`、`10-platform`、テスト |
| `platform/terraform/tags.yaml` | 決めごと | NetBoxタグとAnsibleグループの対応 | `10-platform`、テスト |
| `platform/terraform/hosts.yaml` | 決めごと | ホストの宣言。**正本** | `10-platform`、テスト |
| `platform/terraform/cloud.yaml` | 決めごと | クラウドAPIの上限の**既定値**と、プローブ用VMID | クラウドAPI（`render_site.py` 経由）、テスト |

### 例外: 実行中に変わる値は1か所だけ

`cloud.yaml` の上限は**既定値**で、`admins` が `PUT /v1/limits` で上書きできます。上書きは API の管理DBに入ります。ここだけ「Gitの宣言が唯一の正本」から外れるので、形を決めてあります。

**管理DBには、管理者が実際に変えた項目だけが入ります。**触っていない上限の行は存在せず、読み出しのたびに `cloud.yaml` の既定値と重ね合わせます。同じ上限が2か所に書かれることは無く、`GET /v1/limits` は実効値・既定値・上書きぶんを別々に返すので、どちらが効いているかが常に分かります。上書きを消せば既定値へ戻ります。

上限を運用中に変えられる必要があったのは、容量の判断が実測に依存するからです（[配備台帳](operations.md#measured-budget)）。実測で変わる値のために Git のコミットと再配備を要求すると、いちばん急いでいるときに動けません。

`site.yaml` は `tools/site-yaml.py --api` が読み取り専用トークンで生成します。**手で書きません。**候補が1つに絞れないときは推測せず候補名を出して止まります。

### なぜ tfvars に置かないか

`terraform.tfvars` は `.gitignore` 対象です。そこにしか宣言が無いと、**そのファイルを持たない作業機で plan を打ったときに Terraform は「宣言が無い＝消す」と読みます。**

実際に起きました。cloud image の宣言が tfvars にしかなく、別の作業機での plan が

```
proxmox_download_file.cloud_image["debian13"] will be destroyed
(because key ["debian13"] is not in for_each map)
```

を出しました。消えると基盤VMを作り直せなくなります。同じ形の穴がSSH公開鍵にもありました（全VMから鍵が剥がれる）。

**秘密でない宣言を tfvars に置かない**というのがここから得た規則です。URL・チェックサム・公開鍵・ストレージ名・IP範囲はいずれも秘密ではありません。秘密値は今まで通り SOPS 経由の環境変数で渡します。

`tests/test_platform_inventory.py` が整合を検査します。VMIDが範囲外・重複、未宣言のタグやflavor、`cloud` プールの使用、`automation_pools` への `cloud` の混入、`media` グループ式の変更は、実機へ触る前にここで落ちます。

## VMIDとプールの分割

`platform/terraform/pools.yaml` が正本です。

| VMID | プール | 所有者 | 用途 |
| --- | --- | --- | --- |
| 100–399 | `platform` | 管理者Terraform | public-edge、vpn-01、identity、home-assistant、storage-s3、k8s、game |
| 400–499 | `dev` | 管理者Terraform | 開発VM。利用者は電源とコンソールのみ |
| 900–999 | `lab` | 管理者Terraform | 検証・復元ドリル。使い捨て |
| 5000–5999 | `cloud` | 自作クラウドAPI | 利用者がAPI・Providerで作るVM |

`cloud` プールは**空のまま先に作りました**。枠を予約しておいたので、APIを載せるときにVMIDの再採番や既存VMの移動が要りません。VMIDの採番はAPI自身が管理DBで行い、`GET /cluster/nextid` は使いません。あれは競合するうえ、APIの予約を見ていないためです。

## ロールとトークン

| ロール | 与える権限 | 割り当て先 | 到達範囲 |
| --- | --- | --- | --- |
| `TerraformAdmin` | VM.\*（Config含む）、Pool.Audit | `terraform@pve` | `/pool/platform`、`/pool/dev`、`/pool/lab` |
| `TerraformStorage` | Datastore.Audit / AllocateSpace / AllocateTemplate | `terraform@pve` | `/storage` |
| `TerraformNetwork` | SDN.Use | `terraform@pve`、`cloudapi@pve` | SDNゾーン |
| `DevVMOperator` | VM.Audit、VM.PowerMgmt、VM.Console | `dev-a@pve`、`dev-b@pve` | `/vms/400`、`/vms/401` |
| `CloudApiOperator` | VM.\*（Clone・Migrate・Config.Cloudinit を除く）、Pool | `cloudapi@pve` | `/pool/cloud` のみ |
| `CloudApiStorage` | Datastore.Audit / AllocateSpace | `cloudapi@pve` | 利用者VMのディスク置き場 |
| `CloudApiImages` | 上記＋AllocateTemplate / Allocate | `cloudapi@pve` | `cloud-images` のみ |
| `CloudApiNodeAudit` | Sys.Audit | `cloudapi@pve` | `/nodes/<ノード名>` |

`terraform@pve` は `/pool/cloud` に権限を持ちません。逆に `cloudapi@pve` は `/pool/platform` に権限を持ちません。**利用者向けの削除APIが基盤VMへ届かないことを、ACLの形で保証します。**

`CloudApiOperator` の権限リストを `TerraformAdmin` と共用しないのも同じ理由です。共用していると、片方に必要な権限を足したときに**もう片方の到達範囲が黙って広がります**。

`CloudApiNodeAudit` だけが `/pool/cloud` の外に出ます。作成前に空きRAMを見る `GET /nodes/<node>/status` が `/nodes/<node>` の `Sys.Audit` を要求するためで、読み取り専用です。これが無いと**容量を見ないまま作成を通します**。

`Datastore.Allocate` を `cloud-images` にだけ与えるのは、アップロードしたISOがVMの持ち物にならず `VM.Config.Disk` では消せないためです。ストレージ定義そのものも触れる強い権限なので、他のストレージへは広げません。

`DevVMOperator` に `VM.Config.*` を含めないのは意図的です。電源とコンソールは自由に使えますが、CPU・RAM・ディスク・NICの正本はTerraformのままです。利用者の操作でIaCと実機が乖離しません。これは開発VMの中で何をしてよいかの制限ではありません。VMの外側の形だけを固定します。

## モジュールの入力を将来のAPIと揃える

[最小クラウドとTerraform Provider](cloud.md)の `shakecloud_instance` は image・CPU・RAM・disk・network を受け取ります。`platform/terraform/modules/managed-host` の入力を同じ形にして、`flavors.yaml`（`small` など）の名前も共用します。

**ただし利用者側は名前から選ぶ必要はありません。**クラウドAPIは CPU・メモリ・ディスク・バルーニングの有無を直接受け取り、`flavors.yaml` の名前は値を埋める雛形として出すだけです。基盤VM側（`hosts.yaml`）はこれまでどおり名前で指定し、台ごとに上書きします。

**将来のGo APIはこのモジュールを呼びません。** APIはProxmox APIを直接叩きます。揃えるのは入力の形だけで、TerraformをAPIの内側に隠しません。隠すと、APIの障害時にTerraformも使えなくなります。

## stateの分離

- **stateはK11の外のS3互換ストレージに置きます。** K11は単一SSDなので、そこにstateを置くとディスク1枚の故障で「Terraformが現状を把握できない」状態になります。またK11が停止していてもstateを読める必要があります（`cloud.md`「クラウド停止中も使える場所へ保持」）。現在の実体はCloudflare R2ですが、`backend "s3"` に事業者固有の設定を書いていないので、`cloud.md` が計画しているGarageへ移すときも endpoint と bucket の差し替えだけで済みます。
- ルートモジュールごとに別のstateです（`shake-cloud/<モジュール>/terraform.tfstate`）。`00-bootstrap` は `root@pam`、それ以外は `terraform@pve` で実行します。
- 自作APIはTerraform stateを共有しません。APIは自分のジョブ・バックエンドIDを持ちます。
- 利用者側の `homelab` Provider のstateは各自の開発VM上に置きます。クラウドが停止していても手元に残る場所である必要があります。

## 秘密値

Proxmox・NetBoxの資格情報は[SOPS+age](../operations/secrets.md)で暗号化してGitに置きます。**Terraformのstateはこれとは別の話です。** stateには復号後の値が平文で入り得ます。取り扱いは[Terraformの実行手順](../operations/terraform.md)を参照してください。
