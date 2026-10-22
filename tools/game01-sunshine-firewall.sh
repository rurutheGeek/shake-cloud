#!/bin/sh
# game-01（Bazzite）の Sunshine のポートを受け付ける送信元を揃える。何度実行してもよい。
#
#   tools/game01-sunshine-firewall.sh
#
# 送信元以外からの Sunshine は、game-01 の firewalld にある priority -10 の reject が拒む。
# tailnet（100.64.0.0/10）は Tailscale のポリシーで自分の端末だけが届く（platform/tailscale/acl.json）。
# game-01 へは dev-01 を経由して入る（dev-01 の ~/.ssh/config の game-01）。
set -eu

JUMP="${GAME01_JUMP:-debian@192.168.10.202}"
KEY="${PVE_SSH_KEY:-$HOME/.ssh/id_ed25519_pve}"
SOURCES='192.168.10.0/24 192.168.40.0/24 100.64.0.0/10'
PORTS='47984/tcp 47989/tcp 48010/tcp 47999/udp 48100/udp 48200/udp'

script=$(cat <<EOF
set -eu
for source in $SOURCES; do
	for port in $PORTS; do
		rule="rule family=ipv4 priority=-20 source address=\$source port port=\${port%/*} protocol=\${port#*/} accept"
		sudo -n firewall-cmd --permanent --zone=FedoraWorkstation --query-rich-rule="\$rule" >/dev/null ||
			sudo -n firewall-cmd --permanent --zone=FedoraWorkstation --add-rich-rule="\$rule" >/dev/null
	done
done
sudo -n firewall-cmd --reload >/dev/null
sudo -n firewall-cmd --zone=FedoraWorkstation --list-rich-rules | grep -c 'priority="-20"'
EOF
)
# 手元で組み立てた $script を送る（展開はこちら側でしてよい）。
# shellcheck disable=SC2087
ssh -o BatchMode=yes -i "$KEY" "$JUMP" "ssh -o BatchMode=yes game-01 sh" <<EOF
$script
EOF
