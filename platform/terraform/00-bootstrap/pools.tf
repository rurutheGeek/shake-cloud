# VMIDとプールの分割。正本は ../pools.yaml。
# 10-platform とテストが同じファイルを読むので、範囲が3か所で食い違わない。
# 設計の説明は docs/architecture/iac.md。
locals {
  # 実機の事実。ノード名・ストレージ名・bridge名。正本は ../site.yaml。
  site = yamldecode(file("${path.module}/../site.yaml"))

  # 共有 cloud image の宣言。正本は ../images.yaml。
  images = yamldecode(file("${path.module}/../images.yaml")).images

  # このモジュールが読む値。実機に聞いていないものが残っていれば site.tf が
  # plan を止める。UNMEASURED のまま apply すると /storage/UNMEASURED という
  # 壊れたACLができてしまう。
  site_unknown = [for name, value in {
    "storage.vm_disks"     = local.site.storage.vm_disks
    "storage.admin_images" = local.site.storage.admin_images
    "network.sdn_zone"     = local.site.network.sdn_zone
  } : name if value == "UNMEASURED"]

  # NICへ bridge を割り当てるのに要る SDN.Use のパス。
  # 素の Linux bridge は既定ゾーンに入る。ゾーン名は site.yaml が正本。
  sdn_acl_path        = "/sdn/zones/${local.site.network.sdn_zone}"
  vm_storage_acl_path = "/storage/${local.site.storage.vm_disks}"

  pool_spec = yamldecode(file("${path.module}/../pools.yaml"))
  pools     = local.pool_spec.pools

  # 自動化ユーザーへ権限を与えるプール。cloud は含まれない。
  automation_pools = local.pool_spec.automation_pools
}

resource "proxmox_virtual_environment_pool" "this" {
  for_each = local.pools

  pool_id = each.key
  comment = each.value.comment
}
