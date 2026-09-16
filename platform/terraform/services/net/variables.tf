variable "name" {
  description = "ゲストのホスト名。tags.Name に入り、変えるとVMは作り直される。"
  type        = string
  default     = "net-01"
}

variable "ssh_public_key_path" {
  description = <<-EOT
    cloud API の鍵ペアへ登録するSSH公開鍵のファイル。秘密鍵ではない。
    正本は platform/terraform/access.yaml の admin_ssh_public_keys で、
    その鍵の公開鍵ファイルをここで指す。
  EOT
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}

variable "key_name" {
  description = "cloud API 上の鍵ペア名。同じ名前を他のサービスVMと共有してもよい。"
  type        = string
  default     = "net-01"
}

variable "image_id" {
  description = "起動元の共有 cloud image。images.yaml の debian13 が cloud へ共有される。"
  type        = string
  default     = "img-debian13"
}

# Tailscale subnet router 専用。API の最小メモリは 512MiB。
variable "vcpus" {
  type    = number
  default = 1
}

variable "memory_mib" {
  type    = number
  default = 512
}

variable "memory_min_mib" {
  description = "バルーニングでホストが回収できる下限。"
  type        = number
  default     = 512
}

variable "ballooning" {
  type    = bool
  default = false
}

variable "root_disk_gib" {
  description = "OS用。API の最小は 10GiB。"
  type        = number
  default     = 10
}
