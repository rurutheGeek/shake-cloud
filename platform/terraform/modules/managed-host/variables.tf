# 入力の形は cloud.md の shakecloud_instance（image・CPU・RAM・disk・network →
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
  description = "メモリの上限。バルーニング時の最大。"
  type        = number
}

variable "memory_min_mib" {
  description = <<-EOT
    バルーニングでホストが回収できる下限。null なら固定割り当て
    （バルーニングなし）。上限と同じ値でも固定になる。
  EOT
  type        = number
  default     = null
}

variable "disk_gib" {
  type = number
}

variable "data_disk_gib" {
  description = <<-EOT
    追加のデータディスク（GiB）。0 なら作らない。OS とデータを分けると、
    OS を作り直してもデータが残り、バックアップの単位も分けられる。
    フォーマットとマウントは Ansible 側で行う（cloud image は自動でやらない）。
  EOT
  type        = number
  default     = 0
}

variable "node_name" {
  description = "Proxmox のノード名。実機の読み取りの結果から入れる。"
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

variable "netbox_ip_range_id" {
  description = <<-EOT
    IPを採番させる IP Range。**Prefix ではなく Range を使う。**
    Prefix 全体から採番すると、ゲートウェイやDHCPが配る帯まで対象になる。
    採番の一意性は NetBox が保証する。
  EOT
  type        = number
}
