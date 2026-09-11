output "hosts" {
  description = "作成したホストと NetBox が採番したアドレス。"
  value = {
    for name, host in module.host : name => {
      vm_id   = host.vm_id
      address = host.address
      cidr    = host.ip_address
    }
  }
}

output "ansible_hint" {
  description = "NetBox 動的インベントリでの確認方法。"
  value       = "ansible-inventory -i platform/ansible/inventory.netbox.yml --graph"
}

output "cloud_ip_range_id" {
  description = <<-EOT
    クラウドAPIが採番に使う NetBox IP Range のID。cloud/api の設定へ入れる。
    範囲の宣言は ../network.yaml の cloud。
  EOT
  value       = netbox_ip_range.cloud.id
}
