# 自動化ユーザー。10-platform はこのトークンで実行する。
# パスワードは設定しない。APIトークンでしか使わないため。
resource "proxmox_virtual_environment_user" "automation" {
  user_id = var.automation_user_id
  comment = "Terraform automation. Managed by platform/terraform/00-bootstrap."
  enabled = true
}

# privileges_separation = false は、トークンがユーザーと同じ権限を持つ設定。
# ユーザー側の権限がすでにプール単位まで絞ってあるので、ACLを二重に
# 定義せずに済む。トークン単独で権限を広げているわけではない。
resource "proxmox_user_token" "automation" {
  user_id               = proxmox_virtual_environment_user.automation.user_id
  token_name            = var.automation_token_name
  comment               = "Used by platform/terraform/10-platform."
  privileges_separation = false
}

resource "proxmox_acl" "automation_pools" {
  for_each = toset(local.automation_pools)

  path      = "/pool/${proxmox_virtual_environment_pool.this[each.key].pool_id}"
  role_id   = proxmox_virtual_environment_role.platform_admin.role_id
  user_id   = proxmox_virtual_environment_user.automation.user_id
  propagate = true
}

resource "proxmox_acl" "automation_storage" {
  path      = "/storage"
  role_id   = proxmox_virtual_environment_role.storage.role_id
  user_id   = proxmox_virtual_environment_user.automation.user_id
  propagate = true
}

# 開発VMの利用者。パスワードはTerraformで管理しない（stateへ秘密値を
# 入れないため）。作成後に本人がGUIまたは `pveum passwd` で設定する。
resource "proxmox_virtual_environment_user" "dev" {
  for_each = var.dev_vm_owners

  user_id = each.key
  comment = "Developer VM operator for VMID ${each.value}. Password is set out of band."
  enabled = true
}

# ACLは自分のVMだけ。相手のVMは一覧に出ず、操作もできない。
resource "proxmox_acl" "dev" {
  for_each = var.dev_vm_owners

  path      = "/vms/${each.value}"
  role_id   = proxmox_virtual_environment_role.dev_operator.role_id
  user_id   = proxmox_virtual_environment_user.dev[each.key].user_id
  propagate = false
}
