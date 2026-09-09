output "automation_token_id" {
  description = "10-platform が使うトークンのID。秘密値ではない。"
  value       = "${var.automation_user_id}!${var.automation_token_name}"
}

output "automation_token_value" {
  description = <<-EOT
    自動化トークンの秘密値。**表示は一度だけにして SOPS へ入れる。**

    出力は `user@realm!id=uuid` の**完全な形**なので、PROXMOX_VE_API_TOKEN へは
    そのまま入れる。`automation_token_id` を接頭辞として足さない。

      terraform -chdir=platform/terraform/00-bootstrap output -raw automation_token_value

    この値は state にも平文で入る。state は .gitignore 対象・権限0600で保持し、
    バックアップ側で暗号化する。詳細は docs/operations/terraform.md。
  EOT
  value       = proxmox_user_token.automation.value
  sensitive   = true
}

output "vmid_ranges" {
  description = "プールごとのVMID範囲。hosts.yaml の検証に使う。"
  value       = { for name, pool in local.pools : name => "${pool.vmid_from}-${pool.vmid_to}" }
}

output "reserved_cloud_pool" {
  description = "自作クラウドAPI用に予約したプール。自動化ユーザーは権限を持たない。"
  value       = proxmox_virtual_environment_pool.this["cloud"].pool_id
}
