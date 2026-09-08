locals {
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

  cpu_cores  = local.flavors[each.value.flavor].cpu_cores
  memory_mib = local.flavors[each.value.flavor].memory_mib
  disk_gib   = each.value.disk_gib

  node_name       = var.proxmox_node_name
  vm_datastore_id = var.vm_datastore_id
  image_file_id   = proxmox_download_file.cloud_image.id
  network_bridge  = var.network_bridge
  network_vlan_id = var.network_vlan_id

  gateway     = var.gateway
  dns_servers = var.dns_servers
  dns_domain  = var.dns_domain

  username = var.vm_username
  # 開発VMには管理鍵と本人の鍵だけが入る。利用者どうしで鍵を共有しない。
  ssh_public_keys = concat(var.admin_ssh_public_keys, lookup(var.host_ssh_public_keys, each.key, []))

  on_boot = try(each.value.on_boot, false)
  started = try(each.value.started, true)

  proxmox_tags = try(each.value.tags, [])
  netbox_tags  = try(each.value.tags, [])

  netbox_site_id    = tonumber(netbox_site.this.id)
  netbox_cluster_id = tonumber(netbox_cluster.this.id)
  netbox_prefix_id  = tonumber(netbox_prefix.management.id)

  # タグ名での参照は暗黙の依存にならないので明示する。
  depends_on = [netbox_tag.this]
}
