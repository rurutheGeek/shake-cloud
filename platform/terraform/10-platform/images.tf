# cloud image。URLとチェックサムは配布元から転記する。latest ではなく
# 日付入りのビルドを指定しないと、再実行で中身が変わる。
resource "proxmox_download_file" "cloud_image" {
  node_name          = var.proxmox_node_name
  datastore_id       = var.image_datastore_id
  content_type       = var.image_content_type
  url                = var.cloud_image_url
  file_name          = var.cloud_image_file_name
  checksum           = var.cloud_image_checksum
  checksum_algorithm = var.cloud_image_checksum_algorithm
  # 手で置いた同名ファイルを黙って上書きしない。
  overwrite_unmanaged = false
}
