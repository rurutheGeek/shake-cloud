terraform {
  required_version = ">= 1.10.0"

  # state は S3 互換ストレージに置く。ミニPCのSSD1枚に依存させないため。
  # ここには事業者に依存しない設定だけを書く。bucket・endpoint・鍵は
  # tools/tf が platform/sops/s3.sops.yaml から渡す。現在の実体は
  # Cloudflare R2 だが、Garage や MinIO へ移すときも変えるのはその2つだけ。
  # skip_* は AWS 固有のリージョン・認証チェックを外すためのもの。
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
