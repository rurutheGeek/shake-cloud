# endpoint と access_key は SHAKECLOUD_ENDPOINT / SHAKECLOUD_ACCESS_KEY から読む。
provider "shakecloud" {}

locals {
  # LAN の CIDR は site.yaml が正本。SG の送信元をここで二重管理しない。
  site     = yamldecode(file("${path.module}/../../site.yaml"))
  lan_cidr = local.site.network.prefix

  # ゲストが見るデータディスクのパス。serial は volume ID から決まるので、
  # デバイス名（vda/vdb）の順序に依存しない。VM 起動後に API が接続するため、
  # cloud-init はこのパスを待ってから Docker を起動する。
  data_device = "/dev/disk/by-id/virtio-${shakecloud_volume.data.serial}"
}

resource "shakecloud_key_pair" "monitor" {
  key_name   = var.key_name
  public_key = trimspace(file(pathexpand(var.ssh_public_key_path)))
}

resource "shakecloud_security_group" "monitor" {
  group_name  = var.name
  description = "monitor-01: LAN から SSH と HTTP/HTTPS だけ"
}

resource "shakecloud_security_group_rule" "ssh" {
  group_id    = shakecloud_security_group.monitor.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 22
  to_port     = 22
  cidr        = local.lan_cidr
  description = "SSH from the LAN"
}

resource "shakecloud_security_group_rule" "http" {
  group_id    = shakecloud_security_group.monitor.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 80
  to_port     = 80
  cidr        = local.lan_cidr
  description = "HTTP from the LAN (redirect and ACME)"
}

resource "shakecloud_security_group_rule" "https" {
  group_id    = shakecloud_security_group.monitor.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 443
  to_port     = 443
  cidr        = local.lan_cidr
  description = "HTTPS from the LAN"
}

resource "shakecloud_instance" "monitor" {
  image_id = var.image_id

  # 明示サイズ。instance_type は使わない。
  vcpus          = var.vcpus
  memory_mib     = var.memory_mib
  memory_min_mib = var.memory_min_mib
  ballooning     = var.ballooning
  root_disk_gib  = var.root_disk_gib

  key_name           = shakecloud_key_pair.monitor.key_name
  security_group_ids = [shakecloud_security_group.monitor.id]

  user_data = templatefile("${path.module}/cloud-init.yaml", {
    data_device     = local.data_device
    data_mount_path = var.data_mount_path
  })

  tags = { Name = var.name }
}

resource "shakecloud_volume" "data" {
  size_gib = var.data_disk_gib
  tags     = { Name = "${var.name}-data" }

  lifecycle {
    # Prometheus の時系列。VM や state の操作で消さない。意図的に消す手順は README。
    prevent_destroy = true
  }
}

resource "shakecloud_volume_attachment" "data" {
  volume_id = shakecloud_volume.data.id
  # instance_id は instance の作成後に決まる。API が接続を終えるまで待つ。
  instance_id = shakecloud_instance.monitor.id
  # device は省略。空いている最小の virtio スロットになる。
}
