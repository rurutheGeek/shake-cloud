output "vm_id" {
  description = "router-01 の VMID。"
  value       = proxmox_virtual_environment_vm.router.vm_id
}

output "image_file_id" {
  description = "取り込んだ OpenWrt イメージ。再ビルド後は plan で差し替わる。"
  value       = proxmox_virtual_environment_file.image.id
}

output "lan_mac_address" {
  description = "LAN 側 NIC の MAC。Aterm など他機器の静的な設定を書くときに使う。"
  value       = proxmox_virtual_environment_vm.router.mac_addresses[1]
}
