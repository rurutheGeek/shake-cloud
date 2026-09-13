variable "name" {
  description = "ゲストのホスト名。tags.Name に入り、変えるとVMは作り直される。"
  type        = string
  default     = "monitor-01"
}

variable "ssh_public_key_path" {
  description = <<-EOT
    cloud API の鍵ペアへ登録するSSH公開鍵のファイル。秘密鍵ではない。
    正本は platform/terraform/access.yaml の admin_ssh_public_keys で、
    その鍵の公開鍵ファイルをここで指す。VM初回起動時は cloud-init の
    meta-data 経由で debian ユーザーへ入る。
  EOT
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}

variable "key_name" {
  description = "cloud API 上の鍵ペア名。同じ名前を他のサービスVMと共有してもよい。"
  type        = string
  default     = "monitor-01"
}

variable "image_id" {
  description = "起動元の共有 cloud image。images.yaml の debian13 が cloud へ共有される。"
  type        = string
  default     = "img-debian13"
}

# Prometheus と Grafana を同居させる開始予算（M01）。実測で確定する。
variable "vcpus" {
  type    = number
  default = 2
}

variable "memory_mib" {
  type    = number
  default = 2048
}

variable "memory_min_mib" {
  description = "バルーニングでホストが回収できる下限。"
  type        = number
  default     = 1024
}

variable "ballooning" {
  type    = bool
  default = true
}

variable "root_disk_gib" {
  description = "OS用。小さくはできない。"
  type        = number
  default     = 32
}

variable "data_disk_gib" {
  description = "Prometheusの時系列とGrafanaの状態を置くデータディスク。縮小はできない。"
  type        = number
  default     = 32
}

variable "data_mount_path" {
  description = "データディスクをマウントするゲスト内のパス。未マウントのままDockerを起動しない。"
  type        = string
  default     = "/srv/monitoring"
}
