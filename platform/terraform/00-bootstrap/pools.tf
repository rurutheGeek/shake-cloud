# VMIDとプールの分割。所有者の境界を規約ではなく権限で保証する。
# 詳細は docs/architecture/iac.md を参照。
locals {
  pools = {
    platform = {
      comment   = "管理者Terraform。恒久基盤。VMID 100-399"
      vmid_from = 100
      vmid_to   = 399
    }
    dev = {
      comment   = "開発VM。利用者は電源とコンソールのみ。VMID 400-499"
      vmid_from = 400
      vmid_to   = 499
    }
    lab = {
      comment   = "検証・復元ドリル。使い捨て。VMID 900-999"
      vmid_from = 900
      vmid_to   = 999
    }
    cloud = {
      comment   = "自作クラウドAPI用の予約枠。現時点では空。VMID 5000-5999"
      vmid_from = 5000
      vmid_to   = 5999
    }
  }

  # 自動化ユーザーへ権限を与えるプール。cloud は**含めない**。
  # 将来の cloudapi@pve だけが /pool/cloud を触れる状態を先に作る。
  automation_pools = ["platform", "dev", "lab"]
}

resource "proxmox_virtual_environment_pool" "this" {
  for_each = local.pools

  pool_id = each.key
  comment = each.value.comment
}
