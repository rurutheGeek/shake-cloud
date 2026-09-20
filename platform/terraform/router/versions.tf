terraform {
  required_version = ">= 1.10.0"

  # ルータは基盤VM（10-platform）ともサービスVM（services/*）とも所有が違う。
  # NetBox の採番にも cloud プールにも載らないゲートウェイなので、state を
  # 分けて誤って destroy の巻き添えにしない。キーは iac.md の規約に従う。
  backend "s3" {
    key                         = "shake-cloud/router/terraform.tfstate"
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
