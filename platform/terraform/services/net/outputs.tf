output "instance_id" {
  description = "net-01 のインスタンスID（i-...）。cloud-inventory.yml に書く。"
  value       = shakecloud_instance.net.id
}

output "address" {
  description = "cloud API が採番したプライベートIP。SSH と Ansible の対象指定に使う。"
  value       = shakecloud_instance.net.private_ip_address
}

output "mac_address" {
  value = shakecloud_instance.net.mac_address
}

output "security_group_id" {
  description = "net-01 の SG。ルールの追加はこのグループへ行う。"
  value       = shakecloud_security_group.net.id
}
