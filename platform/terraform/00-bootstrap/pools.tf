# VMIDとプールの分割。正本は ../pools.yaml。
# 10-platform とテストが同じファイルを読むので、範囲が3か所で食い違わない。
# 設計の説明は docs/architecture/iac.md。
locals {
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
