locals {
  # Ansible の動的インベントリが見るタグ。正本は ../tags.yaml。
  netbox_tags = keys(yamldecode(file("${path.module}/../tags.yaml")).tags)

  state_backend = {
    bucket                      = var.state_bucket
    region                      = "auto"
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_s3_checksum            = true
  }
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


# services-01（05-seed）は NetBox より先に存在するので、台帳には後からここで載せる。
# これが無いと Ansible の動的インベントリに出てこず、services-01 だけ手書きの
# インベントリ（seed.ini）で配備し続けることになる。VM 本体は 05-seed の持ち物で、
# ここは台帳の器と primary IP だけを作る。
data "terraform_remote_state" "seed" {
  backend = "s3"
  config  = merge(local.state_backend, { key = "shake-cloud/05-seed/terraform.tfstate" })
}

locals {
  seed_prefix_length = split("/", local.network.management.range_start)[1]
}

resource "netbox_virtual_machine" "seed" {
  name        = data.terraform_remote_state.seed.outputs.name
  description = "NetBox など台帳・共有サービスの置き場（05-seed が作る）。"
  cluster_id  = tonumber(netbox_cluster.this.id)
  site_id     = tonumber(netbox_site.this.id)
  status      = "active"
  tags        = ["services"]

  depends_on = [netbox_tag.this]
}

resource "netbox_interface" "seed" {
  name               = "primary"
  virtual_machine_id = tonumber(netbox_virtual_machine.seed.id)
  enabled            = true
}

resource "netbox_ip_address" "seed" {
  ip_address   = "${data.terraform_remote_state.seed.outputs.address}/${local.seed_prefix_length}"
  status       = "active"
  object_type  = "virtualization.vminterface"
  interface_id = tonumber(netbox_interface.seed.id)
  dns_name     = data.terraform_remote_state.seed.outputs.name
  tags         = ["services"]

  depends_on = [netbox_tag.this]
}

resource "netbox_primary_ip" "seed" {
  virtual_machine_id = tonumber(netbox_virtual_machine.seed.id)
  ip_address_id      = tonumber(netbox_ip_address.seed.id)
}
