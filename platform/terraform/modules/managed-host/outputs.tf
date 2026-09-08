output "name" {
  value = var.name
}

output "vm_id" {
  value = var.vm_id
}

output "ip_address" {
  description = "NetBox が採番したアドレス。プレフィックス長を含む。"
  value       = netbox_available_ip_address.primary.ip_address
}

output "address" {
  description = "プレフィックス長を除いたアドレス。SSHやAnsibleの接続先。"
  value       = split("/", netbox_available_ip_address.primary.ip_address)[0]
}
