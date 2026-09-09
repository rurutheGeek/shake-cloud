terraform {
  required_version = ">= 1.10.0"

  # state は Cloudflare R2 に置く。ミニPCのSSD1枚に依存させないため。
  # bucket・endpoint・鍵は口座固有なのでコードに書かない。tools/tf が
  # platform/sops/r2.sops.yaml から環境変数と -backend-config で渡す。
  # R2 は S3 互換だがリージョンと認証フローが違うので skip_* で回避する。
  backend "s3" {
    key                         = "shake-cloud/05-seed/terraform.tfstate"
    region                      = "auto"
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_s3_checksum            = true
    use_lockfile                = true
  }

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.112"
    }
  }
}
