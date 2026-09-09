# cloud image の取得。Proxmox の query-url-metadata API は `/` に対する
# Sys.Audit と Sys.Modify を要求するため、絞った terraform@pve では拒否される。
# 特権が要る一度きりの作業なので、root@pam で動くこのモジュールが担当する。
# 以降の 05-seed / 10-platform は出来上がったファイルを参照するだけ。
#
# URL は latest ではなく日付入りのビルドを指定する。チェックサムは配布元の
# SHA512SUMS から転記する。
resource "proxmox_download_file" "cloud_image" {
  for_each = var.cloud_images

  node_name          = var.proxmox_node_name
  datastore_id       = each.value.datastore_id
  content_type       = each.value.content_type
  url                = each.value.url
  file_name          = each.value.file_name
  checksum           = each.value.checksum
  checksum_algorithm = each.value.checksum_algorithm

  # 手で置いた同名ファイルを黙って上書きしない。
  overwrite_unmanaged = false
}
