resource "proxmox_virtual_environment_role" "platform_admin" {
  role_id    = "TerraformAdmin"
  privileges = var.platform_admin_privileges
}

resource "proxmox_virtual_environment_role" "storage" {
  role_id    = "TerraformStorage"
  privileges = var.storage_privileges
}

resource "proxmox_virtual_environment_role" "dev_operator" {
  role_id    = "DevVMOperator"
  privileges = var.dev_operator_privileges
}

# 自作クラウドAPI用のロールを先に作る。この時点では誰にも割り当てない。
# 利用者向け削除APIが基盤VMへ届かないことを、後付けの規約ではなく
# ACLの形で保証するための枠。実装は Phase 12。
resource "proxmox_virtual_environment_role" "cloud_api_operator" {
  role_id    = "CloudApiOperator"
  privileges = var.platform_admin_privileges
}
