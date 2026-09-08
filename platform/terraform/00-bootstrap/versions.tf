terraform {
  required_version = ">= 1.9.0"

  required_providers {
    proxmox = {
      source = "bpg/proxmox"
      # 版は .terraform.lock.hcl で固定する。Renovate で更新を確認する。
      version = "~> 0.112"
    }
  }
}
