# 1. NetBox に台帳の器を作る。
resource "netbox_virtual_machine" "this" {
  name         = var.name
  description  = var.description
  cluster_id   = var.netbox_cluster_id
  site_id      = var.netbox_site_id
  status       = "active"
  vcpus        = var.cpu_cores
  memory_mb    = var.memory_mib
  disk_size_mb = var.disk_gib * 1024
  tags         = var.netbox_tags
}

resource "netbox_interface" "primary" {
  name               = "primary"
  virtual_machine_id = tonumber(netbox_virtual_machine.this.id)
  enabled            = true
}

# 2. IPの採番は NetBox にさせる。Git 側では番号を決めない。
#    一意性の保証を IPAM に任せるのがハイブリッド方式の要点。
#    採番元は Prefix ではなく IP Range。ゲートウェイやDHCPの帯を避けるため。
resource "netbox_available_ip_address" "primary" {
  ip_range_id  = var.netbox_ip_range_id
  status       = "active"
  object_type  = "virtualization.vminterface"
  interface_id = tonumber(netbox_interface.primary.id)
  dns_name     = var.name
  tags         = var.netbox_tags
}

# NetBox の primary IP を設定する。これが無いと nb_inventory の
# has_primary_ip フィルタに掛かって、Ansible の動的インベントリに出てこない。
resource "netbox_primary_ip" "primary" {
  virtual_machine_id = tonumber(netbox_virtual_machine.this.id)
  ip_address_id      = tonumber(netbox_available_ip_address.primary.id)
}

# 3. 採番された値をそのまま cloud-init へ渡して Proxmox に作る。
resource "proxmox_virtual_environment_vm" "this" {
  name        = var.name
  description = var.description
  node_name   = var.node_name
  vm_id       = var.vm_id
  pool_id     = var.pool_id
  on_boot     = var.on_boot
  started     = var.started
  tags        = sort(var.proxmox_tags)

  agent {
    enabled = true
  }

  operating_system {
    type = "l26"
  }

  cpu {
    cores = var.cpu_cores
    type  = "host"
  }

  # dedicated が上限、floating がバルーニングの下限。floating を省くと
  # 固定割り当てになる。空き容量の見積もりは上限で行い、回収分を余剰に
  # 数えない（flavors.yaml を参照）。
  memory {
    dedicated = var.memory_mib
    floating  = var.memory_min_mib
  }

  disk {
    datastore_id = var.vm_datastore_id
    import_from  = var.image_file_id
    interface    = "virtio0"
    size         = var.disk_gib
    discard      = "on"
  }

  network_device {
    bridge  = var.network_bridge
    model   = "virtio"
    vlan_id = var.network_vlan_id
  }

  initialization {
    datastore_id = var.vm_datastore_id
    interface    = "ide2"

    dns {
      domain  = var.dns_domain
      servers = var.dns_servers
    }

    ip_config {
      ipv4 {
        address = netbox_available_ip_address.primary.ip_address
        gateway = var.gateway
      }
    }

    user_account {
      username = var.username
      keys     = var.ssh_public_keys
    }
  }

  lifecycle {
    # 電源状態は作成時にだけ設定する。以降は利用者の devvm start/stop や
    # Proxmox GUI の操作を正とし、Terraform が起動し直さない。
    ignore_changes = [started]

    precondition {
      condition     = var.vm_id >= var.pool_vmid_range.from && var.vm_id <= var.pool_vmid_range.to
      error_message = "VMID ${var.vm_id} is outside the ${var.pool_id} pool range ${var.pool_vmid_range.from}-${var.pool_vmid_range.to}. See docs/architecture/iac.md."
    }
  }
}
