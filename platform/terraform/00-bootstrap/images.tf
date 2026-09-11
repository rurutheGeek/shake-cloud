# cloud image の取得。Proxmox の query-url-metadata API は `/` に対する
# Sys.Audit と Sys.Modify を要求するため、絞った terraform@pve では拒否される。
# 特権が要る一度きりの作業なので、root@pam で動くこのモジュールが担当する。
# 以降の 05-seed / 10-platform は出来上がったファイルを参照するだけ。
#
# 宣言の正本は ../images.yaml。**tfvars ではない。** 秘密値ではないうえ、
# 手元にファイルが無い人が plan を打つと消す差分が出るため。
resource "proxmox_download_file" "cloud_image" {
  for_each = local.images

  node_name          = local.site.node_name
  datastore_id       = coalesce(try(each.value.datastore_id, null), local.site.storage.admin_images)
  content_type       = try(each.value.content_type, "import")
  url                = each.value.url
  file_name          = each.value.file_name
  checksum           = each.value.checksum
  checksum_algorithm = try(each.value.checksum_algorithm, "sha512")

  # 手で置いた同名ファイルを黙って上書きしない。
  overwrite_unmanaged = false
}

# クラウドAPI が利用者VMのディスクを作る元。cloudapi@pve は admin_images（local）を
# 読めない（2026-09-10 実測で 403）ので、shared_with_cloud の付いたイメージは
# cloudapi@pve が権限を持つ cloud-images にも同じものを置く。
# local へ権限を広げないのは、そこにバックアップや管理者のイメージも載っているため。
resource "proxmox_download_file" "cloud_shared_image" {
  for_each = { for name, image in local.images : name => image if try(image.shared_with_cloud, false) }

  node_name           = local.site.node_name
  datastore_id        = proxmox_storage_directory.cloud_images.id
  content_type        = "import"
  url                 = each.value.url
  file_name           = each.value.file_name
  checksum            = each.value.checksum
  checksum_algorithm  = try(each.value.checksum_algorithm, "sha512")
  overwrite_unmanaged = false
}
