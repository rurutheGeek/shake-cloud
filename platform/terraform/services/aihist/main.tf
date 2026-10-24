# endpoint と access_key は SHAKECLOUD_ENDPOINT / SHAKECLOUD_ACCESS_KEY から読む。
provider "shakecloud" {}

# 各マシンが push するときのトークン。tools/tf が platform/sops/aihist.sops.yaml の
# AIHIST_TOKEN から渡す。画面で発行したマシンごとのトークンは DB にある。
variable "aihist_token" {
  type      = string
  sensitive = true
}

# AI の会話履歴。イメージは rurutheGeek/aihist のリリースから CI が作る
# （.github/workflows/release.yml）。版を上げるときはタグとダイジェストを両方変える。
# ディスクには aihist.db と原本の raw/ が入る（2026-10-24 時点で約8GB）。
# 消すとディスクも消えるので、destroy の前に中身を写す。
resource "shakecloud_service" "aihist" {
  name            = "aihist"
  image           = "ghcr.io/ruruthegeek/aihist:0.35.0@sha256:79662e092f60dd3d535105ed195a4ce39a96c28bb0cedf99e5dc05f172eb61c4"
  port            = 8080
  memory_mib      = 256
  disk_size_gib   = 32
  disk_mount_path = "/data"
  env             = { TZ = "Asia/Tokyo" }
  secrets         = { AIHIST_TOKEN = var.aihist_token }
}
