# 他のモジュールが backend "s3" で使うバケット。手で作らない。
resource "cloudflare_r2_bucket" "state" {
  account_id = var.cloudflare_account_id
  name       = var.bucket_name
  location   = var.location

  lifecycle {
    # state の入れ物を取り違えて消さないための保険。
    # 意図して作り直すときだけ、この行を外す。
    prevent_destroy = true
  }
}
