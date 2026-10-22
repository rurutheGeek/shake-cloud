# 基盤VMの受信を、firewall.yaml に書いたものだけに絞る。
#
# 送信元が複数のルールは送信元ごとに1行へ展開する（Proxmox の source は
# カンマ区切りも取れるが、1行1送信元のほうが画面とログで読みやすい）。
locals {
  rules = flatten([
    for rule in var.rules : [
      for source in(rule.from == null ? [null] : rule.from) : {
        proto   = rule.proto
        dport   = rule.dport
        source  = source == null ? null : var.sources[source]
        comment = source == null ? rule.comment : "${rule.comment}（${source}）"
      }
    ]
  ])
}

resource "proxmox_virtual_environment_firewall_rules" "inbound" {
  node_name = var.node_name
  vm_id     = var.vm_id

  dynamic "rule" {
    for_each = local.rules
    content {
      type    = "in"
      action  = "ACCEPT"
      proto   = rule.value.proto
      dport   = rule.value.dport
      source  = rule.value.source
      comment = rule.value.comment
      enabled = true
    }
  }
}

# 既定の拒否は、許可のルールが入ってから有効にする（逆だと間が全部落ちる）。
# NIC の firewall=1 が無い間は、ここを有効にしても何も絞られない。
resource "proxmox_virtual_environment_firewall_options" "vm" {
  node_name = var.node_name
  vm_id     = var.vm_id

  enabled       = true
  input_policy  = "DROP"
  output_policy = "ACCEPT"
  # DHCP・IPv6 の近隣探索は通す。MAC の偽装は止める。
  dhcp      = true
  ndp       = true
  macfilter = true
  ipfilter  = false
  radv      = false

  depends_on = [proxmox_virtual_environment_firewall_rules.inbound]
}
