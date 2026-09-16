# endpoint と access_key は SHAKECLOUD_ENDPOINT / SHAKECLOUD_ACCESS_KEY から読む。
provider "shakecloud" {}

locals {
  # LAN の CIDR は site.yaml が正本。SG の送信元をここで二重管理しない。
  site     = yamldecode(file("${path.module}/../../site.yaml"))
  lan_cidr = local.site.network.prefix
}

resource "shakecloud_key_pair" "net" {
  key_name   = var.key_name
  public_key = trimspace(file(pathexpand(var.ssh_public_key_path)))
}

resource "shakecloud_security_group" "net" {
  group_name  = var.name
  description = "net-01: LAN から SSH だけ。Tailscale subnet router"
}

resource "shakecloud_security_group_rule" "ssh" {
  group_id    = shakecloud_security_group.net.id
  direction   = "ingress"
  protocol    = "tcp"
  from_port   = 22
  to_port     = 22
  cidr        = local.lan_cidr
  description = "SSH from the LAN"
}

resource "shakecloud_instance" "net" {
  image_id = var.image_id

  # 明示サイズ。instance_type は使わない。Tailscale 専用なので極小。
  vcpus      = var.vcpus
  memory_mib = var.memory_mib

  # ballooning がオフのとき API は memory_min_mib を 0 で返す。明示すると
  # `Provider produced inconsistent result after apply` になるため、
  # オンのときだけ送る。
  memory_min_mib = var.ballooning ? var.memory_min_mib : null
  ballooning     = var.ballooning
  root_disk_gib  = var.root_disk_gib

  key_name           = shakecloud_key_pair.net.key_name
  security_group_ids = [shakecloud_security_group.net.id]

  # ユーザー・guest agent・SSH だけ。Tailscale の導入と登録は
  # platform/ansible/net.yml（roles/tailscale）が行う。認証キーを
  # user_data へ入れると state に平文で残るため、ここには置かない。
  user_data = file("${path.module}/cloud-init.yaml")

  tags = { Name = var.name }
}
