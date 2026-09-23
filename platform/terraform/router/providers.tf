# 認証情報は環境変数から受け取る（tools/tf router が SOPS から渡す）。
# NetBox は使わない。ゲートウェイのアドレスは台帳の採番対象ではない。
provider "proxmox" {}
