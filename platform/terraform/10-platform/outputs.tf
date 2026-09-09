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
