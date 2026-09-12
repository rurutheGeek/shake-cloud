output "instance_id" {
  description = "media-01 のインスタンスID（i-...）。"
  value       = shakecloud_instance.media.id
}

output "address" {
  description = "cloud API が採番したプライベートIP。Ansible の対象指定に使う。"
  value       = shakecloud_instance.media.private_ip_address
}

output "mac_address" {
  value = shakecloud_instance.media.mac_address
}

output "security_group_id" {
  description = "media-01 の SG。ルールの追加はこのグループへ行う。"
  value       = shakecloud_security_group.media.id
}

output "data_volume_id" {
  description = "原本を置くデータディスク。prevent_destroy で保護している。"
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
