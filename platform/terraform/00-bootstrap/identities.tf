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

# 開発VMの利用者。
#
# GUI用のパスワードはここでは設定できない。Proxmox は /access/password を
# API トークンで叩かせず、ticket（利用者名＋パスワードでのログイン）を要求する。
# そのため生成と設定は platform/ansible/pve-users.yml が SSH 経由で行う。
# 手作業へ戻したのではなく、担当をAnsibleへ移しただけ。
resource "proxmox_virtual_environment_user" "dev" {
  for_each = var.dev_vm_owners

  user_id = each.key
  comment = "Developer VM operator for VMID ${each.value}. Managed by 00-bootstrap."
  enabled = true

  lifecycle {
    # パスワードの担当は platform/ansible/pve-users.yml。Terraform が
    # 触ろうとすると /access/password で 403 になるので、差分を見ない。
    ignore_changes = [password]
  }
}

# tools/devvm が使うAPIトークン。privileges_separation = false で
# ユーザーと同じ権限（＝自分のVMの電源とコンソールだけ）を持つ。
resource "proxmox_user_token" "dev" {
  for_each = var.dev_vm_owners

  user_id               = proxmox_virtual_environment_user.dev[each.key].user_id
  token_name            = var.dev_token_name
  comment               = "Used by tools/devvm."
  privileges_separation = false
}

# ACLは自分のVMだけ。相手のVMは一覧に出ず、操作もできない。
resource "proxmox_acl" "dev" {
  for_each = var.dev_vm_owners

  path      = "/vms/${each.value}"
  role_id   = proxmox_virtual_environment_role.dev_operator.role_id
  user_id   = proxmox_virtual_environment_user.dev[each.key].user_id
  propagate = false
}

# bridge の割り当てに要る SDN.Use。プールやストレージとはパスが違うので
# 別のACLにする。propagate でゾーン配下の bridge を含める。
resource "proxmox_acl" "automation_network" {
  path      = local.sdn_acl_path
  role_id   = proxmox_virtual_environment_role.network.role_id
  user_id   = proxmox_virtual_environment_user.automation.user_id
  propagate = true
}

# 自作クラウドAPIの実行アカウント。
#
# ここが所有境界の要になる。terraform@pve は /pool/cloud に権限を持たず、
# cloudapi@pve は /pool/platform・/pool/dev・/pool/lab に権限を持たない。
# 「利用者向けの削除APIが基盤VMへ届かない」ことを、運用規約ではなく
# ACLの形で保証する。設計は docs/architecture/iac.md。
resource "proxmox_virtual_environment_user" "cloudapi" {
  user_id = var.cloudapi_user_id
  comment = "Self-built cloud API. Managed by platform/terraform/00-bootstrap."
  enabled = true
}

resource "proxmox_user_token" "cloudapi" {
  user_id               = proxmox_virtual_environment_user.cloudapi.user_id
  token_name            = var.cloudapi_token_name
  comment               = "Used by cloud/api on cloud-01."
  privileges_separation = false
}

# **cloud プールだけ。** ここを for_each で automation_pools と共有しない。
# 共有すると片方を足したときにもう片方の到達範囲が黙って広がる。
resource "proxmox_acl" "cloudapi_pool" {
  path      = "/pool/${proxmox_virtual_environment_pool.this["cloud"].pool_id}"
  role_id   = proxmox_virtual_environment_role.cloud_api_operator.role_id
  user_id   = proxmox_virtual_environment_user.cloudapi.user_id
  propagate = true
}

# 利用者VMのディスク置き場。/storage 全体には与えない。
# 置き場は site.yaml が正本なので、tfvars へ手で入れ直す必要はない。
resource "proxmox_acl" "cloudapi_vm_storage" {
  path      = local.vm_storage_acl_path
  role_id   = proxmox_virtual_environment_role.cloud_api_storage.role_id
  user_id   = proxmox_virtual_environment_user.cloudapi.user_id
  propagate = true
}

# イメージと seed ISO の専用ストレージ。Datastore.Allocate を含むので、
# 利用者VMのディスク置き場とは必ず別のストレージにする。
# パスは storage.tf が作ったストレージから引くので、両者がずれない。
resource "proxmox_acl" "cloudapi_image_storage" {
  path      = "/storage/${proxmox_storage_directory.cloud_images.id}"
  role_id   = proxmox_virtual_environment_role.cloud_api_images.role_id
  user_id   = proxmox_virtual_environment_user.cloudapi.user_id
  propagate = true
}

# 共有ISO（管理者が admin_images に置いた既存ファイル）を、複製せずに
# CD-ROM として使うための読み取り専用ACL。Datastore.Audit だけなので、
# ストレージの一覧は読めるが、書き込み・削除はできない。
resource "proxmox_acl" "cloudapi_shared_iso_storage" {
  path      = local.admin_images_acl_path
  role_id   = proxmox_virtual_environment_role.cloud_api_shared_iso.role_id
  user_id   = proxmox_virtual_environment_user.cloudapi.user_id
  propagate = true
}

# NICに bridge を割り当てるための SDN.Use。terraform@pve と同じロールを
# 同じパスへ与える。ゾーンは共有の物理ネットワークなので分けられない。
resource "proxmox_acl" "cloudapi_network" {
  path      = local.sdn_acl_path
  role_id   = proxmox_virtual_environment_role.network.role_id
  user_id   = proxmox_virtual_environment_user.cloudapi.user_id
  propagate = true
}

# ノードの空き容量を読むためだけのACL。読み取り専用なので、ここが
# /pool/cloud の外へ出ている唯一の例外になる。
resource "proxmox_acl" "cloudapi_node_audit" {
  path      = "/nodes/${local.site.node_name}"
  role_id   = proxmox_virtual_environment_role.cloud_api_node_audit.role_id
  user_id   = proxmox_virtual_environment_user.cloudapi.user_id
  propagate = false
}
