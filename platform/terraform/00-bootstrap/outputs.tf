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
  description = "クラウドAPIが使うプール。terraform@pve は権限を持たない。"
  value       = proxmox_virtual_environment_pool.this["cloud"].pool_id
}

output "cloud_image_file_ids" {
  description = "05-seed / 10-platform の image_file_id へ渡す値。"
  value       = { for name, image in proxmox_download_file.cloud_image : name => image.id }
}

output "dev_credentials" {
  description = <<-EOT
    開発VMの利用者へ渡す値。**手で発行しない。** ここから SOPS へ入れて、
    利用者へは暗号化した経路で渡す。

      terraform -chdir=platform/terraform/00-bootstrap output -json dev_credentials

    token は tools/devvm の PVE_TOKEN に入れる値で、user@realm!name=uuid の完全な形。
    GUI用のパスワードは platform/ansible/pve-users.yml が別に発行する。
  EOT
  value = {
    for user_id, vm_id in var.dev_vm_owners : user_id => {
      vm_id = vm_id
      token = proxmox_user_token.dev[user_id].value
    }
  }
  sensitive = true
}

output "cloudapi_token_id" {
  description = "クラウドAPIが使うトークンのID。秘密値ではない。"
  value       = "${var.cloudapi_user_id}!${var.cloudapi_token_name}"
}

output "cloudapi_token_value" {
  description = <<-EOT
    クラウドAPIのトークンの秘密値。**表示は一度だけにして SOPS へ入れる。**

    automation_token_value と同じく `user@realm!id=uuid` の**完全な形**で出る。
    接頭辞を足さない。cloud/api の PROXMOX_API_TOKEN へそのまま入れる。

      terraform -chdir=platform/terraform/00-bootstrap output -raw cloudapi_token_value

    この値も state に平文で入る。取り扱いは docs/operations/terraform.md。
  EOT
  value       = proxmox_user_token.cloudapi.value
  sensitive   = true
}
