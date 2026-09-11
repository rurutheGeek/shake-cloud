terraform {
  required_version = ">= 1.10.0"

  # 他のモジュールと同じ置き場。bucket・endpoint・鍵は tools/tf が渡す。
  backend "s3" {
    key                         = "shake-cloud/20-dns/terraform.tfstate"
    region                      = "auto"
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_s3_checksum            = true
    use_lockfile                = true
  }

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.24"
    }
  }
}
