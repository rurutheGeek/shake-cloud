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
    ユーザーのパスワードはTerraformで管理しない。作成後に本人が
    `pveum passwd <user>` またはGUIで設定する。stateへ秘密値を入れないため。
  EOT
  type        = map(number)
  default = {
    "dev-a@pve" = 400
    "dev-b@pve" = 401
  }
}

variable "platform_admin_privileges" {
  description = <<-EOT
    TerraformAdmin ロールの権限。VMの作成・構成・電源・cloud-initまで。
    PVEの版によって存在しない権限があると作成に失敗するため変数にしている。
    実機の権限名は棚卸し（survey-pve.yml）が取得する `pveum role list` を見る。
    PVE 9.2 では VM.Monitor が廃止されている。bridge の割り当てには
    SDN.Use、guest agent 経由のIP取得には VM.GuestAgent.Audit が要る。
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
    "SDN.Use",
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
