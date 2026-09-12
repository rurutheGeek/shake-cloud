locals {
  # 公開鍵の正本。access.yaml は 10-platform も読む。順序が意味を持つので
  # seed 専用の並び（seed_ssh_public_keys）を使う。
  access = yamldecode(file("${path.module}/../access.yaml"))
}

resource "proxmox_virtual_environment_vm" "services" {
  name        = var.name
  description = "NetBox など台帳・共有サービスの置き場。10-platform が動くための前提を作る過渡的なホスト。"
  node_name   = var.proxmox_node_name
  vm_id       = var.vm_id
  pool_id     = var.pool_id
  on_boot     = true
  started     = true
  tags        = sort(var.tags)

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

  memory {
    dedicated = var.memory_mib
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
        address = var.ipv4_cidr
        gateway = var.gateway
      }
    }

    user_account {
      username = var.username
      keys     = local.access.seed_ssh_public_keys
    }
  }

  lifecycle {
    # 電源状態は作成時のみ設定する。10-platform と同じ方針。
    ignore_changes = [started]
  }
}
