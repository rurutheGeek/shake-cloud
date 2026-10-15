#!/bin/sh
# rootfs/ を Flint 3 へ置く。置くだけで、設定の反映（apply-router）はしない。
#
#   platform/flint3/deploy.sh [host]     # 既定は 192.168.10.5（AP 構成の管理IP）
set -eu

host="${1:-192.168.10.5}"
key="${FLINT3_SSH_KEY:-$HOME/.ssh/id_ed25519_pve}"
root="$(cd "$(dirname "$0")" && pwd)/rootfs"

tar -C "$root" --owner=0 --group=0 -cf - . | ssh -o BatchMode=yes -i "$key" "root@$host" 'tar -C / -xf - && chmod +x /etc/init.d/shakecloud-ecm /etc/hotplug.d/iface/99-shakecloud-ecm /etc/hotplug.d/iface/95-shakecloud-tailscale-routes /etc/hotplug.d/net/90-mld-personal /etc/hotplug.d/iface/92-lan-prefix-route-on-lan /etc/hotplug.d/iface/89-mape-ce-address /etc/hotplug.d/iface/90-mape-ports /etc/hotplug.d/iface/91-lan-prefix-route /etc/shakecloud/apply-router /etc/shakecloud/rollback-router /etc/shakecloud/install-node-exporter /etc/shakecloud/network-counts'
echo "deployed to $host"
