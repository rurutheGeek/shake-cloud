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

resource "shakecloud_key_pair" "media" {
  key_name   = var.key_name
  public_key = trimspace(file(pathexpand(var.ssh_public_key_path)))
}

resource "shakecloud_security_group" "media" {
  group_name  = var.name
  description = "media-01: LAN から SSH と HTTP/HTTPS だけ"
}

resource "shakecloud_security_group_rule" "ssh" {
  group_id    = shakecloud_security_group.media.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 22
  to_port     = 22
  cidr        = local.lan_cidr
  description = "SSH from the LAN"
}

resource "shakecloud_security_group_rule" "http" {
  group_id    = shakecloud_security_group.media.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 80
  to_port     = 80
  cidr        = local.lan_cidr
  description = "HTTP from the LAN (redirect and ACME)"
}

resource "shakecloud_security_group_rule" "https" {
  group_id    = shakecloud_security_group.media.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 443
  to_port     = 443
  cidr        = local.lan_cidr
  description = "HTTPS from the LAN"
}

resource "shakecloud_instance" "media" {
  image_id = var.image_id

  # 明示サイズ。instance_type は使わない。
  vcpus          = var.vcpus
  memory_mib     = var.memory_mib
  memory_min_mib = var.memory_min_mib
  ballooning     = var.ballooning
  root_disk_gib  = var.root_disk_gib

  key_name           = shakecloud_key_pair.media.key_name
  security_group_ids = [shakecloud_security_group.media.id]

  # user_data は作成時だけの入力で、API からは読めない。データディスクの
  # serial を含むので、volume を作り直すとVMも置換になる。volume の拡張は
  # ModifyVolume の in-place で、置換にならない。
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
    # 原本の置き場。VM や state の操作で消さない。意図的に消す手順は README。
    # tags は RequiresReplace なので、変えるとこのガードに当たる。
    prevent_destroy = true
  }
}

resource "shakecloud_volume_attachment" "data" {
  volume_id = shakecloud_volume.data.id
  # instance_id は instance の作成後に決まる。API が接続を終えるまで待つ。
  instance_id = shakecloud_instance.media.id
  # device は省略。空いている最小の virtio スロットになる。
}
