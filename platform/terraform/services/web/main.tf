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

# --- 外向き（egress）---
# EC2 と同じで、新しいグループは外向きが全許可。公開サイトが突破されても
# 自宅LANへ横展開できないよう、明示の宛先だけにする。
# 注意: 既定の「全許可」2本（0.0.0.0/0 と ::/0 の all）はグループ作成時に
# API が付ける。Terraform では作れないので、作成後に import して削除して
# ある（README の手順）。ロールも配備のたびに残っていないか確認して消す。
# IPv6 の外向きは開けない（LAN 側の IPv6 へ届かせないため。不自由は無い）。

# DNS はホームルータ（AdGuard Home）だけ。53 以外のポートで名前は引けない。
resource "shakecloud_security_group_rule" "egress_dns_udp" {
  group_id    = shakecloud_security_group.web.id
  direction   = "egress"
  protocol    = "udp"
  from_port   = 53
  to_port     = 53
  cidr        = "192.168.10.1/32"
  description = "DNS to the home router (AdGuard)"
}

resource "shakecloud_security_group_rule" "egress_dns_tcp" {
  group_id    = shakecloud_security_group.web.id
  direction   = "egress"
  protocol    = "tcp"
  from_port   = 53
  to_port     = 53
  cidr        = "192.168.10.1/32"
  description = "DNS (TCP) to the home router (AdGuard)"
}

resource "shakecloud_security_group_rule" "egress_ntp" {
  group_id    = shakecloud_security_group.web.id
  direction   = "egress"
  protocol    = "udp"
  from_port   = 123
  to_port     = 123
  cidr        = "0.0.0.0/0"
  description = "NTP"
}

# ポケモン系 PostgreSQL（apps-01）。この1台だけに開ける。
resource "shakecloud_security_group_rule" "egress_pkdb" {
  group_id    = shakecloud_security_group.web.id
  direction   = "egress"
  protocol    = "tcp"
  from_port   = 5432
  to_port     = 5432
  cidr        = "192.168.10.105/32"
  description = "PostgreSQL (pkdb) to apps-01"
}

# インターネット向け。apt・Docker・git（ssh.github.com:443）・Resend など。
# LAN 内向きの 80/443 も通るが、PVE の 8006 や SSH は通らない。
resource "shakecloud_security_group_rule" "egress_http" {
  group_id    = shakecloud_security_group.web.id
  direction   = "egress"
  protocol    = "tcp"
  from_port   = 80
  to_port     = 80
  cidr        = "0.0.0.0/0"
  description = "HTTP for package and image updates"
}

resource "shakecloud_security_group_rule" "egress_https" {
  group_id    = shakecloud_security_group.web.id
  direction   = "egress"
  protocol    = "tcp"
  from_port   = 443
  to_port     = 443
  cidr        = "0.0.0.0/0"
  description = "HTTPS (updates, git over 443, Resend)"
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

