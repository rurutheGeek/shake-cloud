output "name" {
  value = proxmox_virtual_environment_vm.services.name
}

output "vm_id" {
  value = proxmox_virtual_environment_vm.services.vm_id
}

output "address" {
  description = "SSH と Ansible の接続先。プレフィックス長を除いたもの。"
  value       = split("/", var.ipv4_cidr)[0]
}

output "next_step" {
  value = "ansible-playbook -i platform/ansible/seed.ini platform/ansible/bootstrap-netbox.yml"
}
