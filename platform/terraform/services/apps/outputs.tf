output "instance_id" {
  description = "apps-01 のインスタンスID（i-...）。"
  value       = shakecloud_instance.apps.id
}

output "address" {
  description = "cloud API が採番したプライベートIP。DNS と Ansible の対象指定に使う。"
  value       = shakecloud_instance.apps.private_ip_address
}

output "mac_address" {
  value = shakecloud_instance.apps.mac_address
}

output "security_group_id" {
  description = "apps-01 の SG。ルールの追加はこのグループへ行う。"
  value       = shakecloud_security_group.apps.id
}

output "data_volume_id" {
  description = "各アプリのデータを置くデータディスク。prevent_destroy で保護している。"
  value       = shakecloud_volume.data.id
}

output "data_device_path" {
  description = "ゲストが見るデータディスクのパス（/dev/disk/by-id/virtio-...）。"
  value       = shakecloud_volume_attachment.data.device_path
}

output "data_mount_path" {
  description = "ゲストがデータディスクをマウントするパス。"
  value       = var.data_mount_path
}
