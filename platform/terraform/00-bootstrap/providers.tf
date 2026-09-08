# 認証情報は環境変数から受け取る。HCL にも tfvars にも書かない。
#
#   sops exec-env platform/sops/proxmox-root.sops.yaml \
#     'terraform -chdir=platform/terraform/00-bootstrap apply'
#
# このルートモジュールだけは root@pam のトークンで実行する。ここで作る
# terraform@pve は自分自身を作れないため、ブートストラップの1段だけ
# 上位の資格情報が要る。以降の 10-platform は terraform@pve を使う。
provider "proxmox" {}
