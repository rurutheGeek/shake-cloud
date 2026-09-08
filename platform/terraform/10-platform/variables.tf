# 実機依存の値。既定値を置かない。棚卸し（platform/ansible/survey-pve.yml）の
# 出力から転記する。推測で埋めない。

variable "proxmox_node_name" {
  description = "Proxmox のノード名。"
  type        = string
}

variable "vm_datastore_id" {
  description = "VMディスクと cloud-init ドライブを置くストレージ名。"
  type        = string
}

variable "image_datastore_id" {
  description = "cloud image を置くストレージ名。content に iso または import を含むもの。"
  type        = string
}

variable "image_content_type" {
  description = <<-EOT
    cloud image の content 種別。PVE 8.4 以降は import が使える。
    使えない版では iso を指定し、ファイル名を .img にする。
  EOT
  type        = string
  default     = "import"
}

variable "cloud_image_url" {
  description = "cloud image のURL。**latest ではなく日付入りのビルドを指定する**。"
  type        = string
}

variable "cloud_image_file_name" {
  description = "Proxmox 上でのファイル名。"
  type        = string
}

variable "cloud_image_checksum" {
  description = "cloud image のチェックサム。配布元の SHA512SUMS から転記する。"
  type        = string
}

variable "cloud_image_checksum_algorithm" {
  type    = string
  default = "sha512"
}

variable "network_bridge" {
  description = "VMを接続する bridge。"
  type        = string
}

variable "network_vlan_id" {
  description = "VLAN を使わない場合は null のままにする。"
  type        = number
  default     = null
}

variable "management_prefix" {
  description = <<-EOT
    基盤VMのIPを採番する Prefix。**動的用（将来のクラウドAPI）とは分ける。**
    既存LANと重複しない範囲を、棚卸しの経路表から決める。
  EOT
  type        = string
}

variable "cloud_prefix" {
  description = <<-EOT
    自作クラウドAPIが採番する Prefix。今は台帳へ登録するだけで誰も使わない。
    分けておくことで、管理者Terraformとクラウドが同じ範囲を奪い合わない。
    決まっていなければ null のままでよい。
  EOT
  type        = string
  default     = null
}

variable "gateway" {
  type = string
}

variable "dns_servers" {
  type = list(string)
}

variable "dns_domain" {
  type    = string
  default = null
}

variable "vm_username" {
  description = "cloud image が作る管理ユーザー名。Debian の cloud image は debian。"
  type        = string
  default     = "debian"
}

variable "admin_ssh_public_keys" {
  description = "全ホストへ配る管理用の公開鍵。Ansible の接続元。"
  type        = list(string)
}

variable "host_ssh_public_keys" {
  description = <<-EOT
    ホスト固有の公開鍵。開発VMには本人の鍵だけを足す（鍵は共有しない）。
    キーは hosts.yaml のホスト名。
  EOT
  type        = map(list(string))
  default     = {}
}

variable "netbox_site_name" {
  type    = string
  default = "Homelab"
}

variable "netbox_cluster_name" {
  type    = string
  default = "k11"
}
