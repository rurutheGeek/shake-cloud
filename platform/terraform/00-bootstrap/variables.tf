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
    実機の権限名は棚卸し（survey-pve.yml）が取得する `pveum role list` を見る。
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

variable "proxmox_node_name" {
  description = "cloud image の取得先ノード。棚卸しの結果から入れる。"
  type        = string
  default     = null
}

variable "cloud_images" {
  description = <<-EOT
    取得する cloud image。キーは 05-seed / 10-platform から参照するときの名前。
    `latest` ではなく日付入りのビルドを指定する。再実行で中身が変わらないため。
  EOT
  type = map(object({
    datastore_id       = string
    content_type       = optional(string, "import")
    url                = string
    file_name          = string
    checksum           = string
    checksum_algorithm = optional(string, "sha512")
  }))
  default = {}

  validation {
    condition     = length(var.cloud_images) == 0 || var.proxmox_node_name != null
    error_message = "proxmox_node_name is required when cloud_images is set."
  }
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

variable "sdn_acl_path" {
  description = <<-EOT
    SDN.Use を与えるパス。素の Linux bridge は既定ゾーン localnetwork に入る。
    実機のゾーン名は `pvesh get /cluster/sdn/zones` で確認する。
  EOT
  type        = string
  default     = "/sdn/zones/localnetwork"
}
