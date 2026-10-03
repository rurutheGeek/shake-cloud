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

resource "shakecloud_key_pair" "apps" {
  key_name   = var.key_name
  public_key = trimspace(file(pathexpand(var.ssh_public_key_path)))
}

resource "shakecloud_security_group" "apps" {
  group_name  = var.name
  description = "apps-01: LAN から SSH・HTTP/HTTPS・印刷（IPP）"
}

resource "shakecloud_security_group_rule" "ssh" {
  group_id    = shakecloud_security_group.apps.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 22
  to_port     = 22
  cidr        = local.lan_cidr
  description = "SSH from the LAN"
}

resource "shakecloud_security_group_rule" "http" {
  group_id    = shakecloud_security_group.apps.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 80
  to_port     = 80
  cidr        = local.lan_cidr
  description = "HTTP from the LAN (redirect and ACME)"
}

resource "shakecloud_security_group_rule" "https" {
  group_id    = shakecloud_security_group.apps.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 443
  to_port     = 443
  cidr        = local.lan_cidr
  description = "HTTPS from the LAN"
}

# CUPS の印刷中継。LAN と VPN の端末が 631 へ直接つなぐ（Caddy を通さない）。
resource "shakecloud_security_group_rule" "ipp" {
  group_id    = shakecloud_security_group.apps.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 631
  to_port     = 631
  cidr        = local.lan_cidr
  description = "IPP (CUPS) from the LAN"
}

# プリンターは mDNS（AirPrint の広告）で探す。応答を受け取れるようにする。
resource "shakecloud_security_group_rule" "mdns" {
  group_id    = shakecloud_security_group.apps.id
  direction   = "ingress"
  protocol    = "udp"
  from_port   = 5353
  to_port     = 5353
  cidr        = local.lan_cidr
  description = "mDNS from the LAN (printer discovery)"
}

# Nextcloud の「印刷」アクションが叩く小さなAPI。media-01 だけに開ける。
resource "shakecloud_security_group_rule" "print_api" {
  group_id    = shakecloud_security_group.apps.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 6320
  to_port     = 6320
  cidr        = "192.168.10.101/32"
  description = "Print API from media-01"
}

# node_exporter。監視（monitor-01）だけに開ける。
resource "shakecloud_security_group_rule" "node_exporter" {
  group_id    = shakecloud_security_group.apps.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 9100
  to_port     = 9100
  cidr        = "192.168.10.102/32"
  description = "node_exporter from monitor-01"
}

# Eufy のカメラ（eufyCam S4）は P2P で、カメラ側から UDP を送ってくる。
# カメラのアドレスだけに開ける（platform/ansible/eufy-security-ws.yml と同じアドレス）。
resource "shakecloud_security_group_rule" "eufy_camera" {
  group_id    = shakecloud_security_group.apps.id
  direction   = "ingress"
  protocol    = "udp"
  from_port   = 1
  to_port     = 65535
  cidr        = "192.168.10.4/32"
  description = "UDP from the Eufy camera (P2P)"
}

resource "shakecloud_instance" "apps" {
  image_id = var.image_id

  # 明示サイズ。instance_type は使わない。
  vcpus          = var.vcpus
  memory_mib     = var.memory_mib
  memory_min_mib = var.memory_min_mib
  ballooning     = var.ballooning
  root_disk_gib  = var.root_disk_gib

  key_name           = shakecloud_key_pair.apps.key_name
  security_group_ids = [shakecloud_security_group.apps.id]

  user_data = templatefile("${path.module}/cloud-init.yaml", {
    data_device     = local.data_device
    data_mount_path = var.data_mount_path
  })

  # Purpose は用途（service / dev）。ポータルでの絞り込みに使う。
  tags = { Name = var.name, Purpose = "service" }
}

resource "shakecloud_volume" "data" {
  size_gib = var.data_disk_gib
  tags     = { Name = "${var.name}-data" }

  lifecycle {
    # 各アプリのデータ（Vaultwarden のDB、Home Assistant の設定など）。VM や state の
    # 操作で消さない。
    prevent_destroy = true
  }
}

resource "shakecloud_volume_attachment" "data" {
  volume_id = shakecloud_volume.data.id
  # instance_id は instance の作成後に決まる。API が接続を終えるまで待つ。
  instance_id = shakecloud_instance.apps.id
  # device は省略。空いている最小の virtio スロットになる。
}
