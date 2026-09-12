variable "automation_user_id" {
  description = "10-platform が使う自動化ユーザー。realm を含めて指定する。"
  type        = string
  default     = "terraform@pve"
}

variable "automation_token_name" {
  description = "自動化ユーザーのAPIトークン名。"
  type        = string
  default     = "terraform"
}

variable "dev_vm_owners" {
  description = <<-EOT
    開発VMの割り当て。PVEユーザーIDからVMIDへの対応。
    ACLは `/vms/<VMID>` にだけ付くので、相手のVMは一覧にも出ない。
    GUI用のパスワードと devvm 用のAPIトークンもここから作る。
    値は output から取り出して SOPS へ入れる（手で発行しない）。
  EOT
  type        = map(number)
  default = {
    "dev-a@pve" = 400
    "dev-b@pve" = 401
  }
}

variable "dev_token_name" {
  description = "開発VMの利用者が tools/devvm で使うAPIトークンの名前。"
  type        = string
  default     = "devvm"
}

variable "platform_admin_privileges" {
  description = <<-EOT
    TerraformAdmin ロールの権限。VMの作成・構成・電源・cloud-initまで。
    PVEの版によって存在しない権限があると作成に失敗するため変数にしている。
    実機の権限名は実機の読み取り（survey-pve.yml）が取得する `pveum role list` を見る。
    PVE 9.2 では VM.Monitor が廃止されている。guest agent 経由のIP取得には
    VM.GuestAgent.Audit が要る。bridge の割り当てに要る SDN.Use は
    パスが違うため sdn_privileges / sdn_acl_path で別に扱う。
  EOT
  type        = set(string)
  default = [
    "VM.Allocate",
    "VM.Audit",
    "VM.Clone",
    "VM.Config.CDROM",
    "VM.Config.CPU",
    "VM.Config.Cloudinit",
    "VM.Config.Disk",
    "VM.Config.HWType",
    "VM.Config.Memory",
    "VM.Config.Network",
    "VM.Config.Options",
    "VM.Console",
    "VM.GuestAgent.Audit",
    "VM.Migrate",
    "VM.PowerMgmt",
    "Pool.Allocate",
    "Pool.Audit",
  ]
}

variable "storage_privileges" {
  description = "TerraformStorage ロールの権限。ディスク確保とイメージ取得。"
  type        = set(string)
  default = [
    "Datastore.Audit",
    "Datastore.AllocateSpace",
    "Datastore.AllocateTemplate",
  ]
}

variable "dev_operator_privileges" {
  description = <<-EOT
    DevVMOperator ロールの権限。**電源とコンソールだけ**を与える。
    VM.Config.* を含めない。CPU・RAM・ディスク・NICの正本はTerraformのまま。
  EOT
  type        = set(string)
  default     = ["VM.Audit", "VM.PowerMgmt", "VM.Console"]
}

variable "sdn_privileges" {
  description = <<-EOT
    TerraformNetwork ロールの権限。PVE 8.2 以降、VMへ bridge を割り当てるには
    `/sdn/zones/<ゾーン>/<bridge>` に対する SDN.Use が要る。プールやストレージ
    とはパスが異なるので、別のロールとACLにしている。
  EOT
  type        = set(string)
  default     = ["SDN.Use"]
}

variable "cloud_api_shared_iso_privileges" {
  description = <<-EOT
    共有ISOの読み取り専用ロール。管理者が admin_images（local）へ置いた既存の
    ISO を、複製せずに利用者VMのCD-ROMとして付けられるようにする。

    **Datastore.Audit だけ**を与える。Allocate 系を渡すとクラウドAPIがローカルの
    バックアップや管理者イメージを消せてしまう。読み取りでもストレージの一覧は
    見えるので、API が公開するのは isos.yaml で宣言した共有ISOだけにする。
  EOT
  type        = set(string)
  default     = ["Datastore.Audit"]
}

variable "cloudapi_user_id" {
  description = <<-EOT
    自作クラウドAPIの実行アカウント。realm を含めて指定する。
    このユーザーは `/pool/cloud` にしか権限を持たない。基盤VM（platform / dev /
    lab）へは一覧にも出ない。設計は docs/architecture/iac.md。
  EOT
  type        = string
  default     = "cloudapi@pve"
}

variable "cloudapi_token_name" {
  description = "クラウドAPIが使うAPIトークン名。"
  type        = string
  default     = "cloudapi"
}

variable "cloud_api_privileges" {
  description = <<-EOT
    CloudApiOperator ロールの権限。**TerraformAdmin とは別に持つ。**
    利用者がAPI経由で作るVMに要るものだけを入れる。

    - VM.Config.CDROM は必須。任意の user-data を渡すために、APIが NoCloud の
      seed ISO を作って CD-ROM として接続するから。Proxmox 内蔵の cloud-init
      ドライブは使わない。upload API が content=snippets を受け付けないので、
      cicustom 方式は絞ったトークンでは成立しない。
    - VM.Config.Network はNICだけでなく、セキュリティグループの実体である
      VM単位のFWルールにも要る。クラスタ階層の /cluster/firewall/groups は
      `/` の Sys.Modify を要求するので使えない。
    - VM.Clone と VM.Migrate は**入れない**。APIはテンプレートから複製せず、
      単一ノードなので移送もしない。権限は要る分だけにする。
    - VM.Config.Cloudinit も**入れない**。seed ISO 方式では Proxmox 内蔵の
      cloud-init ドライブを一切触らないため要らず、持たせないことで
      cicustom への誤書き込みも起きなくなる。実機検証で seed ISO 方式が
      成立しないと分かったら、ここへ戻して内蔵ドライブへ切り替える。
  EOT
  type        = set(string)
  default = [
    "VM.Allocate",
    "VM.Audit",
    "VM.Config.CDROM",
    "VM.Config.CPU",
    "VM.Config.Disk",
    "VM.Config.HWType",
    "VM.Config.Memory",
    "VM.Config.Network",
    "VM.Config.Options",
    "VM.Console",
    "VM.GuestAgent.Audit",
    "VM.PowerMgmt",
    "Pool.Allocate",
    "Pool.Audit",
  ]
}

variable "cloud_api_storage_privileges" {
  description = <<-EOT
    CloudApiStorage ロールの権限。**利用者VMのディスクを置くストレージ**へ与える。
    Datastore.Allocate は**含めない**。VMが持つディスクの削除は VM.Config.Disk で
    通るため要らず、含めるとストレージ定義そのものを消せてしまう。
    Datastore.Audit はアドミッション制御（実空き容量の取得）に要る。
  EOT
  type        = set(string)
  default = [
    "Datastore.Audit",
    "Datastore.AllocateSpace",
  ]
}

variable "cloud_api_image_privileges" {
  description = <<-EOT
    CloudApiImages ロールの権限。**イメージと seed ISO を置く専用ストレージ**
    だけへ与える。

    Datastore.AllocateTemplate はアップロードに、Datastore.Allocate は削除に要る。
    アップロードしたISO・イメージはVMの持ち物にならないので、VM.Config.Disk では
    消せないため。Datastore.Allocate はストレージ定義自体も触れる強い権限なので、
    利用者VMのディスク置き場とは**別のストレージ**を用意し、そこだけに与える。
  EOT
  type        = set(string)
  default = [
    "Datastore.Audit",
    "Datastore.AllocateSpace",
    "Datastore.AllocateTemplate",
    "Datastore.Allocate",
  ]
}

variable "cloud_api_node_audit_privileges" {
  description = <<-EOT
    CloudApiNodeAudit ロールの権限。読み取りだけ。

    アドミッション制御（作成前に実空き容量を見る）が使う
    `GET /nodes/<node>/status` は、**プールではなく `/nodes/<node>` に対する
    Sys.Audit** を要求する。/pool/cloud だけに絞ったトークンでは 403 になり、
    空きRAMを読めないまま作成を通してしまう。
    ノードのタスク状態（UPIDのポーリング）も、これがあると
    トークンの持ち主に依存せず読める。
  EOT
  type        = set(string)
  default     = ["Sys.Audit"]
}

variable "cloudflare_dns_api_token" {
  description = <<-EOT
    Proxmox 本体の証明書を DNS-01 で取るための Cloudflare トークン（ゾーンの読み取りと
    DNS の編集だけ）。tools/tf が platform/sops/cloudflare-dns.sops.yaml から
    TF_VAR_cloudflare_dns_api_token で渡す。acme.tf が write-only 属性へ渡すので、
    plan にも state にも残らない。
  EOT
  type        = string
  sensitive   = true
  ephemeral   = true
}
