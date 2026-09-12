terraform {
  required_version = ">= 1.10.0"

  # state はサービスごとに分ける。キーは I05 が決めた
  # shake-cloud/services/<name>/terraform.tfstate の規約に従う。
  # bucket・endpoint・資格情報は tools/tf が platform/sops/s3.sops.yaml から渡す。
  backend "s3" {
    key                         = "shake-cloud/services/media/terraform.tfstate"
    region                      = "auto"
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_s3_checksum            = true
    use_lockfile                = true
  }

  required_providers {
    # まだ Registry には公開していない。dev override で
    # ~/.terraform.d/plugins のバイナリを指す（docs/operations/terraform-provider.md）。
    shakecloud = {
      source = "ruruthegeek/shakecloud"
    }
  }
}
