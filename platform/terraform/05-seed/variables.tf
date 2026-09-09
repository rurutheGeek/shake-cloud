variable "proxmox_node_name" {
  type = string
}

variable "vm_datastore_id" {
  description = "VMディスクと cloud-init ドライブを置くストレージ。"
  type        = string
}

variable "image_file_id" {
  description = <<-EOT
    cloud image のファイルID。00-bootstrap の `cloud_image_file_ids` 出力から
    転記する（例 local:import/debian-13-genericcloud-amd64-....qcow2）。
    取得そのものは特権が要るため 00-bootstrap（root@pam）が担当する。
  EOT
  type        = string
}

variable "name" {
  type    = string
  default = "services-01"
}

variable "vm_id" {
  description = "platform プールの範囲（100-399）に収める。"
  type        = number
  default     = 150

  validation {
    condition     = var.vm_id >= 100 && var.vm_id <= 399
    error_message = "services host must live in the platform pool range 100-399. See docs/architecture/iac.md."
  }
}

variable "pool_id" {
  type    = string
  default = "platform"
}

variable "cpu_cores" {
  type    = number
  default = 2
}

variable "memory_mib" {
  type    = number
  default = 4096
}

variable "disk_gib" {
  type    = number
  default = 48
}

variable "network_bridge" {
  type = string
}

variable "network_vlan_id" {
  type    = number
  default = null
}

variable "ipv4_cidr" {
  description = <<-EOT
    静的アドレス。プレフィックス長を含める（例 192.168.10.200/24）。
    **ルータのDHCP配布範囲の外**であることを確認してから指定する。
    NetBox 稼働後、この1台は台帳へ手で登録する。以降のVMは採番に任せる。
  EOT
  type        = string
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

variable "username" {
  description = "cloud image が作る管理ユーザー。Debian の cloud image は debian。"
  type        = string
  default     = "debian"
}

variable "ssh_public_keys" {
  type = list(string)
}

variable "tags" {
  type    = list(string)
  default = ["managed-by-terraform-admin", "seed"]
}
