# LAN の中の名前を Cloudflare へ書く。宣言の正本は ../dns.yaml。
#
# 値は内部IPで、Cloudflare のプロキシは通さない（proxied = false）。
# プロキシを通すと Cloudflare の公開アドレスに化け、LAN から届かなくなる。

locals {
  dns = yamldecode(file("${path.module}/../dns.yaml"))

  state_backend = {
    bucket                      = var.state_bucket
    region                      = "auto"
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_s3_checksum            = true
  }

  # 台帳に居るホストのアドレスは、作ったモジュールの出力から引く。
  # dns.yaml へ書き写すと、採番し直したときに黙って食い違う。
  known_hosts = merge(
    { for name, host in data.terraform_remote_state.platform.outputs.hosts : name => host.address },
    { (data.terraform_remote_state.seed.outputs.name) = data.terraform_remote_state.seed.outputs.address },
  )

  # address があればそれ、無ければ host の出力。どちらにも無ければここで止まる。
  addresses = {
    for name, record in local.dns.records :
    name => try(record.address, local.known_hosts[record.host])
  }
}

data "terraform_remote_state" "platform" {
  backend = "s3"
  config  = merge(local.state_backend, { key = "shake-cloud/10-platform/terraform.tfstate" })
}

data "terraform_remote_state" "seed" {
  backend = "s3"
  config  = merge(local.state_backend, { key = "shake-cloud/05-seed/terraform.tfstate" })
}

resource "cloudflare_dns_record" "this" {
  for_each = local.dns.records

  zone_id = local.dns.cloudflare_zone_id
  name    = "${each.key}.${local.dns.zone}"
  type    = "A"
  content = local.addresses[each.key]
  ttl     = 300
  proxied = false
  comment = "${each.value.description} / platform/terraform/20-dns"
}
