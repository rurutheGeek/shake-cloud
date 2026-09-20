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
  prefix      = local.site.network.prefix
  status      = "active"
  site_id     = tonumber(netbox_site.this.id)
  description = "LAN shared with existing devices. Allocation happens from the range below."
  tags        = [netbox_tag.this["managed-by-terraform-admin"].name]
}

# 実際の採番元。**Prefix 全体ではなくこの範囲だけ**を使う。
# Prefix から採番するとゲートウェイやDHCPが配る帯まで対象になる。
resource "netbox_ip_range" "management" {
  start_address = local.network.management.range_start
  end_address   = local.network.management.range_end
  status        = "active"
  description   = "Static allocations owned by platform/terraform/10-platform"
  tags          = [netbox_tag.this["managed-by-terraform-admin"].name]
}

# 動的Prefix。将来の自作クラウドAPIだけがここから採番する。
# 今は台帳へ枠を作るだけで、誰も使わない。範囲を分けておくことで、
# APIを載せたときに管理者Terraformと採番を奪い合わない。
resource "netbox_prefix" "cloud" {
  count = local.network.cloud.prefix == null ? 0 : 1

  # count が 0 のときこの値は使われないが、null のままだと
  # terraform validate が「必須引数が無い」で落ちる（count を見ない）ため、
  # 使われない側にも文字列を入れておく。
  prefix      = coalesce(local.network.cloud.prefix, local.site.network.prefix)
  status      = "active"
  site_id     = tonumber(netbox_site.this.id)
  description = "Owned by the self-built cloud API. Allocation happens from the range below."
  tags        = [netbox_tag.this["managed-by-cloud-api"].name]
}

# クラウドAPIの採番元。**このstateはこの範囲を作るだけで、中のIPは触らない。**
# 個々のアドレスは cloud/api が実行時に available-ips で取り、Terraform の
# state には入らない。管理者Terraformとクラウドが同じアドレスを配らないことを、
# 範囲を分けることで保証する。
resource "netbox_ip_range" "cloud" {
  start_address = local.network.cloud.range_start
  end_address   = local.network.cloud.range_end
  status        = "active"
  description   = "Allocated at runtime by cloud/api. Not managed by Terraform."
  tags          = [netbox_tag.this["managed-by-cloud-api"].name]
}

# 機器帯（AP・プリンタ・Pi・Proxmox ホスト）。静的な機器が使う。
# 個々のアドレスは tools/netbox-dhcp-sync.py が reserved として登録し、
# dnsmasq の予約へ変換する。**Terraform は帯だけを持つ。**
resource "netbox_ip_range" "infrastructure" {
  start_address = local.network.infrastructure.range_start
  end_address   = local.network.infrastructure.range_end
  status        = "active"
  description   = "Static LAN devices (AP, printer, Pis, Proxmox host). Owned by tools/netbox-dhcp-sync.py."
  tags          = [netbox_tag.this["managed-by-terraform-admin"].name]
}

# DHCP プール。dnsmasq が配り、リースは tools/netbox-dhcp-sync.py が
# status=dhcp の IPAddress として台帳へ写す。**Terraform は帯だけを持つ。**
resource "netbox_ip_range" "dhcp" {
  start_address = local.network.dhcp.range_start
  end_address   = local.network.dhcp.range_end
  status        = "active"
  description   = "DHCP pool served by dnsmasq. Leases are mirrored by tools/netbox-dhcp-sync.py."
  tags          = [netbox_tag.this["managed-by-terraform-admin"].name]
}
