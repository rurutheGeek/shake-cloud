# Proxmox 本体の管理画面（:8006）の証明書。Proxmox 標準の ACME で Let's Encrypt から取る。
#
# 名前は ../dns.yaml の pve（内部IP）。インターネットへは公開しないので、
# 検証は DNS-01（Cloudflare）で行う。更新は Proxmox の pve-daily-update が自動で行う。
#
# プラグインは `/` に対する Sys.Modify を要するので、root@pam で動くこのモジュールが持つ。
# Cloudflare のトークンは Proxmox 本体（/etc/pve/priv/acme）に置かれるが、Terraform には
# write-only 属性で渡すので state には残らない。
#
# **ACME アカウントの作成は API トークンでは通らない。** root@pam のトークンでも
# "Permission check failed (user != root@pam)" で断られる（2026-09-10 実測）。
# Proxmox が受けるのは root@pam 本人のログイン（ticket 認証）だけなので、
# tools/tf は proxmox-root.sops.yaml にパスワードがあれば ticket 認証で流す。
# 画面での手作業には落とさない。

locals {
  dns = yamldecode(file("${path.module}/../dns.yaml"))
}

resource "proxmox_acme_account" "letsencrypt" {
  name      = "letsencrypt"
  directory = "https://acme-v02.api.letsencrypt.org/directory"
  # 必須項目だが、Let's Encrypt は 2025 年から期限切れの通知メールを送っていない。
  # 個人のアドレスを外部へ渡さないため、このゾーンの役割アドレスにする（受信はしない）。
  contact = "acme@${local.dns.zone}"
  # 値を入れることが利用規約への同意になる。規約が改訂されたら
  # GET /cluster/acme/tos の値へ更新する。
  tos = "https://letsencrypt.org/documents/LE-SA-v1.8-July-06-2026.pdf"
}

resource "proxmox_acme_dns_plugin" "cloudflare" {
  plugin = "cloudflare"
  api    = "cf"
  data_wo = {
    CF_Token   = var.cloudflare_dns_api_token
    CF_Zone_ID = local.dns.cloudflare_zone_id
  }
  # data_wo は state に残らないので、トークンを入れ替えたらこの数を上げて反映させる。
  data_wo_version  = 1
  validation_delay = 30
}

resource "proxmox_acme_certificate" "node" {
  node_name = local.site.node_name
  account   = proxmox_acme_account.letsencrypt.name
  domains = [{
    domain = "pve.${local.dns.zone}"
    plugin = proxmox_acme_dns_plugin.cloudflare.plugin
  }]
}
