# 基盤VMの受信を ../firewall.yaml の許可だけに絞る。core-01 は 05-seed が持つ。
module "firewall" {
  for_each = { for name, rules in local.firewall.hosts : name => rules if contains(keys(local.hosts), name) }

  source = "../modules/vm-firewall"

  node_name = local.site.node_name
  vm_id     = local.hosts[each.key].vm_id
  rules     = each.value
  sources   = local.firewall.sources

  depends_on = [module.host]
}
