# 認証情報は環境変数から受け取る。HCL にも tfvars にも書かない。
#
#   sops exec-env platform/sops/proxmox.sops.yaml \
#     'sops exec-env platform/sops/netbox.sops.yaml \
#        "terraform -chdir=platform/terraform/10-platform plan"'
#
# Proxmox: PROXMOX_VE_ENDPOINT / PROXMOX_VE_API_TOKEN（terraform@pve）
# NetBox : NETBOX_SERVER_URL / NETBOX_API_TOKEN（書き込み可の terraform ユーザー）
#
# root@pam のトークンはここでは使わない。00-bootstrap 専用。
provider "proxmox" {}

provider "netbox" {}
