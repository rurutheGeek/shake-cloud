terraform {
  required_version = ">= 1.9.0"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.112"
    }
    netbox = {
      source  = "e-breuninger/netbox"
      version = "~> 4.0"
    }
  }
}
