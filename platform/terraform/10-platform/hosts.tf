locals {
  # 実機の事実。ノード名・ストレージ名・bridge名。正本は ../site.yaml。
  site = yamldecode(file("${path.module}/../site.yaml"))

  # 宣言。実測できない決めごとの正本。
  network = yamldecode(file("${path.module}/../network.yaml"))
  access  = yamldecode(file("${path.module}/../access.yaml"))

  # このモジュールが読む値。実機に聞いていないものが残っていれば site.tf が
  # plan を止める。
  site_unknown = [for name, value in {
    "storage.vm_disks" = local.site.storage.vm_disks
    "network.bridge"   = local.site.network.bridge
    "network.prefix"   = local.site.network.prefix
    "network.gateway"  = local.site.network.gateway
  } : name if value == "UNMEASURED"]

  # 共有 cloud image の宣言。正本は ../images.yaml。00-bootstrap が取得し、
  # ここは出来上がったファイルを指すだけ。volid を手で書き写さない。
  image_spec = yamldecode(file("${path.module}/../images.yaml"))
  image      = local.image_spec.images[coalesce(var.image_name, local.image_spec.default_image)]
  image_file_id = format("%s:%s/%s",
    local.site.storage.admin_images,
    try(local.image.content_type, "import"),
    local.image.file_name,
  )

  flavors = yamldecode(file("${path.module}/../flavors.yaml")).flavors
  hosts   = yamldecode(file("${path.module}/../hosts.yaml")).hosts

  # 範囲の正本は ../pools.yaml。00-bootstrap も同じファイルを読む。
  pool_vmid_ranges = {
    for name, pool in yamldecode(file("${path.module}/../pools.yaml")).pools :
    name => { from = pool.vmid_from, to = pool.vmid_to }
  }
}

module "host" {
  for_each = local.hosts

  source = "../modules/managed-host"

  name        = each.key
  description = try(each.value.description, "")
  vm_id       = each.value.vm_id
  pool_id     = each.value.pool
  # cloud プールは自作クラウドAPIの予約枠。管理者Terraformは使わない。
  pool_vmid_range = local.pool_vmid_ranges[each.value.pool]

  # flavor が既定で、hosts.yaml が上書きできる。手で広げた基盤VMを
  # 台帳が縮めに行かないようにするための逃げ道で、利用者向けの語彙
  # （flavor）はそのまま保つ。
  cpu_cores      = try(each.value.cpu_cores, local.flavors[each.value.flavor].cpu_cores)
  memory_mib     = try(each.value.memory_mib, local.flavors[each.value.flavor].memory_mib)
  memory_min_mib = try(each.value.memory_min_mib, local.flavors[each.value.flavor].memory_min_mib)
  disk_gib       = each.value.disk_gib
  data_disk_gib  = try(each.value.data_disk_gib, 0)

  node_name       = local.site.node_name
  vm_datastore_id = local.site.storage.vm_disks
  image_file_id   = local.image_file_id
  network_bridge  = local.site.network.bridge
  # VLAN 切替はこの1か所（network.yaml）で行う。null の間はタグなし。
  network_vlan_id   = local.network.vlan.management.vlan_id
  bridge_vlan_aware = local.site.network.bridge_vlan_aware

  gateway     = local.site.network.gateway
  dns_servers = local.site.network.dns_servers
  dns_domain  = var.dns_domain

  username = var.vm_username
  # 開発VMには管理鍵と本人の鍵だけが入る。利用者どうしで鍵を共有しない。
  # 順序を保つ。並べ替えるだけで cloud-init ドライブに差分が出る。
  ssh_public_keys = concat(
    local.access.admin_ssh_public_keys,
    lookup(local.access.host_ssh_public_keys, each.key, []),
  )

  on_boot = try(each.value.on_boot, false)
  started = try(each.value.started, true)

  proxmox_tags = try(each.value.tags, [])
  netbox_tags  = try(each.value.tags, [])

  netbox_site_id     = tonumber(netbox_site.this.id)
  netbox_cluster_id  = tonumber(netbox_cluster.this.id)
  netbox_ip_range_id = tonumber(netbox_ip_range.management.id)

  # タグ名での参照は暗黙の依存にならないので明示する。
  depends_on = [netbox_tag.this]
}
