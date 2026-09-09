# NetBox を載せる最初の1台だけを作る。**NetBox provider を使わない**のが要点。
# 10-platform は NetBox に採番させる設計なので、NetBox 自身の置き場は
# それでは作れない（鶏と卵）。stacks/netbox/README.md が
# 「NetBox本体を作る初回だけ静的なSSH指定を使用します」と書いているのと
# 同じ理由で、ここだけ静的なIPを直接指定する。
#
#   sops exec-env platform/sops/proxmox.sops.yaml \
#     'terraform -chdir=platform/terraform/05-seed apply'
provider "proxmox" {}
