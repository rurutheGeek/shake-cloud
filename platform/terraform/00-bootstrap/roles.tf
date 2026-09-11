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

# 自作クラウドAPIのロール。利用者向け削除APIが基盤VMへ届かないことを、
# 後付けの規約ではなく ACL の形で保証する。割り当て先は identities.tf。
#
# 権限は TerraformAdmin と共用しない。共用していると、片方に必要な権限を
# 足したときにもう片方の到達範囲が黙って広がる。
resource "proxmox_virtual_environment_role" "cloud_api_operator" {
  role_id    = "CloudApiOperator"
  privileges = var.cloud_api_privileges
}

# ストレージは2つに分ける。利用者VMのディスク置き場には Datastore.Allocate を
# 与えず、イメージと seed ISO の置き場にだけ与える。理由は variables.tf。
resource "proxmox_virtual_environment_role" "cloud_api_storage" {
  role_id    = "CloudApiStorage"
  privileges = var.cloud_api_storage_privileges
}

resource "proxmox_virtual_environment_role" "cloud_api_images" {
  role_id    = "CloudApiImages"
  privileges = var.cloud_api_image_privileges
}

resource "proxmox_virtual_environment_role" "network" {
  role_id    = "TerraformNetwork"
  privileges = var.sdn_privileges
}

# 空き容量の実測に要る読み取り専用ロール。ストレージの Datastore.Audit とは
# パスが違う（/nodes/<node> と /storage/<id>）ので別のロールにする。
resource "proxmox_virtual_environment_role" "cloud_api_node_audit" {
  role_id    = "CloudApiNodeAudit"
  privileges = var.cloud_api_node_audit_privileges
}
