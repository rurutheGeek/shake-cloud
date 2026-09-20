locals {
  # 実機の事実。正本は ../site.yaml（tools/site-yaml.py が実機から生成する）。
  site = yamldecode(file("${path.module}/../site.yaml"))

  # 宣言。実測できない決めごとの正本。
  spec = yamldecode(file("${path.module}/../router.yaml"))

  # ビルド宣言。imagebuilder の出力名と router モジュールの取り込み名を
  # 1か所に保つ。dist/ は platform/openwrt/build.sh が作る。
  openwrt    = yamldecode(file("${path.module}/../../openwrt/openwrt.yaml"))
  image_path = "${path.module}/../../openwrt/dist/${local.openwrt.output_image}"

  # VMID の範囲の正本は ../pools.yaml。00-bootstrap と同じファイルを読む。
  pool = yamldecode(file("${path.module}/../pools.yaml")).pools[local.spec.vm.pool]
}

# Image Builder が作った raw イメージを Proxmox へ置く。content_type = import の
# ストレージでないと VM の import_from に渡せない。管理者Terraform は
# /storage に Datastore.AllocateTemplate を持つのでアップロードできる。
resource "proxmox_virtual_environment_file" "image" {
  node_name    = local.site.node_name
  datastore_id = local.site.storage.admin_images
  content_type = "import"

  source_file {
    path      = local.image_path
    file_name = local.openwrt.output_image
    # 再ビルドしたイメージを差し替えとして検出させる。dist/ が無い間
    # （CI の validate など）は null にして、plan を止めない。
    checksum = try(filesha256(local.image_path), null)
  }
}

# OpenWrt は cloud-init を使わない。設定はイメージ（platform/openwrt/rootfs）に
# 焼いてあり、初回起動時に /etc/shakecloud/apply が反映する。
#
# agent を有効にしない。managed-host と同じ待ち（qemu-guest-agent が応答する
# まで apply が止まる）に入り、OpenWrt には agent が入っていない。
resource "proxmox_virtual_environment_vm" "router" {
  name        = local.spec.vm.name
  description = local.spec.vm.description
  node_name   = local.site.node_name
  vm_id       = local.spec.vm.vm_id
  pool_id     = local.spec.vm.pool
  tags        = sort(local.spec.vm.tags)

  agent {
    enabled = false
  }

  # ホスト再起動後にルータが自力で戻る。他の VM より先に起動する順番
  # （startup order）は **Terraform では設定できない**。Proxmox は起動順の設定に
  # `Sys.Modify` on `/` を要求し（PVE/API2/Qemu.pm の special case）、
  # terraform@pve にその広い権限は与えていない。初回に docs/operations/router.md
  # の手順で `qm set` して、Terraform は触らない（ignore_changes）。
  on_boot = true

  # agent が無いので ACPI で止める。destroy 時に停止を待たせる。
  stop_on_destroy = true

  operating_system {
    type = "l26"
  }

  cpu {
    cores = local.spec.vm.cpu_cores
    type  = "host"
  }

  # floating を書かないので固定割り当て（バルーニングなし）。
  memory {
    dedicated = local.spec.vm.memory_mib
  }

  # rootfs_partition_mib（openwrt.yaml）ぶんのパーティション入り raw を取り込み、
  # 1GiB のディスクへ収める。**中の rootfs パーティションは 512MiB のまま**なので、
  # データを増やすときは openwrt.yaml を変えてイメージを作り直す。
  disk {
    datastore_id = local.site.storage.vm_disks
    import_from  = proxmox_virtual_environment_file.image.id
    interface    = "virtio0"
    size         = 1
    discard      = "on"
  }

  # net0 = WAN（ONU 側の nic0 を載せた bridge）、net1 = LAN（既存 vmbr0）。
  # OpenWrt 側では eth0 / eth1 の順になる。
  #
  # link_down（disconnected）で既存 LAN へ影響させない。切替までは両方 down で
  # 構築し、切替日に router.yaml の wan_connected / lan_connected を true に
  # する。Proxmox は bridge が無いと VM を起動できないので、**先にホストへ
  # vmbr1 を作る**（router.md）。
  network_device {
    bridge       = local.spec.network.wan_bridge
    model        = "virtio"
    disconnected = !local.spec.network.wan_connected
  }

  network_device {
    bridge       = local.site.network.bridge
    model        = "virtio"
    disconnected = !local.spec.network.lan_connected
  }

  boot_order = ["virtio0"]

  # シリアルコンソール。切替前に LAN が使えないときの入口（qm terminal）。
  serial_device {}

  lifecycle {
    # 電源状態は作成時にだけ設定する。以降は人が電源を操作してよい
    # （managed-host と同じ理由。Terraform が勝手に起動し直さない）。
    # startup はホストで設定するので、差分として消しに行かせない。
    ignore_changes = [started, startup]

    precondition {
      condition     = local.spec.vm.vm_id >= local.pool.vmid_from && local.spec.vm.vm_id <= local.pool.vmid_to
      error_message = "VMID ${local.spec.vm.vm_id} は ${local.spec.vm.pool} プールの範囲 ${local.pool.vmid_from}-${local.pool.vmid_to} の外です。docs/architecture/iac.md を参照。"
    }

    # WAN と LAN が同じ bridge だと、ルータの中で折り返して既存 LAN が
    # 壊れる。宣言の取り違えを plan で止める。
    precondition {
      condition     = local.spec.network.wan_bridge != local.site.network.bridge
      error_message = "WAN bridge (${local.spec.network.wan_bridge}) と LAN bridge (${local.site.network.bridge}) が同じです。router.yaml と site.yaml を確認してください。"
    }
  }
}
