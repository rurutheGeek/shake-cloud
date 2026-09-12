# 実機依存の値。既定値を置かない。実機の読み取り（platform/ansible/survey-pve.yml）の
# 出力から転記する。推測で埋めない。

variable "image_name" {
  description = <<-EOT
    使う cloud image。../images.yaml の images の key を指す。
    null なら同ファイルの default_image。volid は名前から組み立てるので、
    00-bootstrap の出力を手で書き写す必要はない。
  EOT
  type        = string
  default     = null
}

# network_vlan_id は variables ではない。切替の値を1か所に保つため、
# ../network.yaml の vlan.management.vlan_id を hosts.tf が直接読む。

variable "dns_domain" {
  type    = string
  default = null
}

variable "vm_username" {
  description = "cloud image が作る管理ユーザー名。Debian の cloud image は debian。"
  type        = string
  default     = "debian"
}

variable "netbox_site_name" {
  type    = string
  default = "Homelab"
}

variable "netbox_cluster_name" {
  type    = string
  default = "k11"
}
