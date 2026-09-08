# 入力の形は cloud.md の homelab_instance（image・CPU・RAM・disk・network →
# ID・IP・状態）に合わせている。将来のGo APIはこのモジュールを呼ばず、
# Proxmox APIを直接叩く。揃えるのは入力の形だけ。

variable "name" {
  description = "ホスト名。NetBoxのVM名、Proxmoxの名前、DNS名に使う。"
  type        = string
}

variable "description" {
  description = "用途。NetBoxとProxmoxの両方へ書く。"
  type        = string
  default     = ""
}

variable "vm_id" {
  description = "Proxmox の VMID。プールの範囲内であることを precondition で検査する。"
  type        = number
}

variable "pool_id" {
  description = "所属する Proxmox プール。"
  type        = string
}

variable "pool_vmid_range" {
  description = "プールに割り当てられた VMID の範囲。00-bootstrap の pools.tf が正本。"
  type = object({
    from = number
    to   = number
  })
}

variable "cpu_cores" {
  type = number
}

variable "memory_mib" {
  type = number
}

variable "disk_gib" {
  type = number
}

variable "node_name" {
  description = "Proxmox のノード名。棚卸しの結果から入れる。"
  type        = string
}

variable "vm_datastore_id" {
  description = "VMディスクを置くストレージ名。"
  type        = string
}

variable "image_file_id" {
  description = "cloud image のファイルID。proxmox_download_file の id を渡す。"
  type        = string
}

variable "network_bridge" {
  type = string
}

variable "network_vlan_id" {
  description = "VLAN を使わない場合は null。"
  type        = number
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

variable "username" {
  description = "cloud-init が作る管理ユーザー。"
  type        = string
}

variable "ssh_public_keys" {
  description = "cloud-init が配る公開鍵。開発VMには本人の鍵だけを渡す。"
  type        = list(string)
}

variable "on_boot" {
  description = "ホスト起動時に自動起動するか。開発VM・ゲームVMは false。"
  type        = bool
  default     = false
}

variable "started" {
  description = <<-EOT
    **作成時の電源状態のみ**。作成後はTerraformが追跡しない
    （lifecycle.ignore_changes）。利用者の電源操作と衝突しないため。
  EOT
  type        = bool
  default     = true
}

variable "proxmox_tags" {
  type    = list(string)
  default = []
}

variable "netbox_tags" {
  description = "NetBoxのタグ名。Ansibleのグループ分けはこれを見る。"
  type        = list(string)
  default     = []
}

variable "netbox_site_id" {
  type = number
}

variable "netbox_cluster_id" {
  type = number
}

variable "netbox_prefix_id" {
  description = "IPを採番させるPrefix。採番の一意性はNetBoxが保証する。"
  type        = number
}
