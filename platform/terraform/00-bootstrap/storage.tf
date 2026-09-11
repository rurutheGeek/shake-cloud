# クラウドAPI専用のストレージ。利用者がアップロードしたイメージと、
# インスタンスごとの cloud-init seed ISO が入る。
#
# **既存の local を使い回さない。** アップロードしたISOの削除には
# Datastore.Allocate が要る（ISOはVMの持ち物にならないので VM.Config.Disk では
# 消せない）。この権限はストレージ定義そのものも消せるため、local に与えると
# cloudapi@pve がバックアップや管理者のイメージごと載った定義を消せてしまう。
# 専用ストレージへ閉じ込め、そこにだけ与える。
#
# 同じSSD上なので**容量は分離されない**。分離されるのは権限だけで、容量は
# API側のクォータで抑える。
resource "proxmox_storage_directory" "cloud_images" {
  id    = local.site.storage.cloud_images
  path  = local.site.storage.cloud_images_path
  nodes = [local.site.node_name]

  # import は利用者のディスクイメージ、iso は seed ISO。
  content = ["import", "iso"]

  # ディレクトリが無ければ作る。手で mkdir する手順を残さないため。
  create_base_path = true
  create_subdirs   = true
}
