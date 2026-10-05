# endpoint と access_key は SHAKECLOUD_ENDPOINT / SHAKECLOUD_ACCESS_KEY から読む。
provider "shakecloud" {}

locals {
  # LAN の CIDR は site.yaml が正本。SG の送信元をここで二重管理しない。
  site     = yamldecode(file("${path.module}/../../site.yaml"))
  lan_cidr = local.site.network.prefix

  # HTTPS の入口（core-01）。名前はすべて入口を指し、入口がここへ中継する
  # （platform/terraform/dns.yaml の edge）。core-01 はまだこのVMを知らないが、
  # 最初から開けておく（入口へ寄せるときにSGを触らない）。
  edge_cidr = "192.168.10.200/32"

  # 公開の入口（negitoroserver、旧 shakeserver 時代から同じ）。Cloudflare →
  # negitoroserver が nginx stream で web-01:443 へ PROXY protocol 付きで中継し、
  # 80 は sslh が HTTP として中継する。tailnet のアドレスがそのまま送信元になる。
  relay_cidr = "100.92.253.28/32"

  # ゲストが見るデータディスクのパス。serial は volume ID から決まるので、
  # デバイス名（vda/vdb）の順序に依存しない。VM 起動後に API が接続するため、
  # cloud-init はこのパスを待ってから Docker を起動する。
  data_device = "/dev/disk/by-id/virtio-${shakecloud_volume.data.serial}"
}

resource "shakecloud_key_pair" "web" {
  key_name   = var.key_name
  public_key = trimspace(file(pathexpand(var.ssh_public_key_path)))
}

resource "shakecloud_security_group" "web" {
  group_name  = var.name
  description = "web-01: LAN から SSH、入口と negitoroserver から HTTP/HTTPS"
}

resource "shakecloud_security_group_rule" "ssh" {
  group_id    = shakecloud_security_group.web.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 22
  to_port     = 22
  cidr        = local.lan_cidr
  description = "SSH from the LAN"
}

resource "shakecloud_security_group_rule" "http" {
  group_id    = shakecloud_security_group.web.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 80
  to_port     = 80
  cidr        = local.edge_cidr
  description = "HTTP from the edge only"
}

resource "shakecloud_security_group_rule" "https" {
  group_id    = shakecloud_security_group.web.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 443
  to_port     = 443
  cidr        = local.edge_cidr
  description = "HTTPS from the edge only"
}

# 公開の入口（negitoroserver）。TLS は nginx が CloudFlare Origin 証明書で
# 終端し、PROXY protocol で実クライアント IP を受け取る。
resource "shakecloud_security_group_rule" "http_relay" {
  group_id    = shakecloud_security_group.web.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 80
  to_port     = 80
  cidr        = local.relay_cidr
  description = "HTTP from the public relay (negitoroserver)"
}

resource "shakecloud_security_group_rule" "https_relay" {
  group_id    = shakecloud_security_group.web.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 443
  to_port     = 443
  cidr        = local.relay_cidr
  description = "HTTPS from the public relay (negitoroserver, PROXY protocol)"
}

# node_exporter。監視（monitor-01）だけに開ける。
resource "shakecloud_security_group_rule" "node_exporter" {
  group_id    = shakecloud_security_group.web.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 9100
  to_port     = 9100
  cidr        = "192.168.10.210/32"
  description = "node_exporter from monitor-01"
}

resource "shakecloud_instance" "web" {
  image_id = var.image_id

  # 明示サイズ。instance_type は使わない。
  vcpus          = var.vcpus
  memory_mib     = var.memory_mib
  memory_min_mib = var.memory_min_mib
  ballooning     = var.ballooning
  root_disk_gib  = var.root_disk_gib

  key_name           = shakecloud_key_pair.web.key_name
  security_group_ids = [shakecloud_security_group.web.id]

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
    # アプリのデータ（静的配信物・ログなど）。VM や state の操作で消さない。
    prevent_destroy = true
  }
}

resource "shakecloud_volume_attachment" "data" {
  volume_id = shakecloud_volume.data.id
  # instance_id は instance の作成後に決まる。API が接続を終えるまで待つ。
  instance_id = shakecloud_instance.web.id
  # device は省略。空いている最小の virtio スロットになる。
}
