variable "cloudflare_account_id" {
  description = "R2 バケットを作る Cloudflare アカウントID。"
  type        = string
}

variable "bucket_name" {
  description = <<-EOT
    Terraform の state を置くバケット。**旧環境のバケットを流用しません。**
    このプロジェクト専用に新規で作ります。
  EOT
  type        = string
  default     = "shake-cloud-state"
}

variable "location" {
  description = "R2 のロケーションヒント。空なら Cloudflare が選ぶ。日本なら apac。"
  type        = string
  default     = null
}
