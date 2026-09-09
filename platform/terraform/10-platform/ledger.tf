locals {
  # Ansible の動的インベントリが見るタグ。正本は ../tags.yaml。
  # media-stack は seed_inventory.py が作る既存タグなのでここでは扱わない。
  netbox_tags = keys(yamldecode(file("${path.module}/../tags.yaml")).tags)
}

resource "netbox_tag" "this" {
  for_each = toset(local.netbox_tags)

  name = each.key
  slug = each.key
}

resource "netbox_site" "this" {
  name   = var.netbox_site_name
  slug   = lower(replace(var.netbox_site_name, " ", "-"))
  status = "active"
}

resource "netbox_cluster_type" "proxmox" {
  name = "Proxmox VE"
  slug = "proxmox-ve"
}

resource "netbox_cluster" "this" {
  name            = var.netbox_cluster_name
  cluster_type_id = tonumber(netbox_cluster_type.proxmox.id)
  site_id         = tonumber(netbox_site.this.id)
}

# 基盤VMが載るネットワーク。台帳としての登録で、ここからは採番しない。
resource "netbox_prefix" "management" {
  prefix      = var.management_prefix
  status      = "active"
  site_id     = tonumber(netbox_site.this.id)
  description = "LAN shared with existing devices. Allocation happens from the range below."
  tags        = [netbox_tag.this["managed-by-terraform-admin"].name]
}

# 実際の採番元。**Prefix 全体ではなくこの範囲だけ**を使う。
# Prefix から採番するとゲートウェイやDHCPが配る帯まで対象になる。
resource "netbox_ip_range" "management" {
  start_address = var.management_range_start
  end_address   = var.management_range_end
  status        = "active"
  description   = "Static allocations owned by platform/terraform/10-platform"
  tags          = [netbox_tag.this["managed-by-terraform-admin"].name]
}

# 動的Prefix。将来の自作クラウドAPIだけがここから採番する。
# 今は台帳へ枠を作るだけで、誰も使わない。範囲を分けておくことで、
# APIを載せたときに管理者Terraformと採番を奪い合わない。
resource "netbox_prefix" "cloud" {
  count = var.cloud_prefix == null ? 0 : 1

  prefix      = var.cloud_prefix
  status      = "reserved"
  site_id     = tonumber(netbox_site.this.id)
  description = "Reserved for the self-built cloud API. Not used yet."
  tags        = [netbox_tag.this["managed-by-cloud-api"].name]
}
