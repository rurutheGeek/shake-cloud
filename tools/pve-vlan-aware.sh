#!/bin/sh
# K11 の vmbr0 を VLAN 対応にする（DMZ の VM を VLAN 30 で出すため）。
# K11 の上で root で実行する。タグ無しの通信（サーバーの区画）はそのまま流れる。
#
#   sh pve-vlan-aware.sh apply     # 変更して、10 分後に自動で元へ戻す予約をする
#   sh pve-vlan-aware.sh confirm   # 戻す予約を取り消す（変更を確定する）
#   sh pve-vlan-aware.sh rollback  # すぐ元へ戻す
#
# 変更後に K11 へ SSH でき、VM がサーバーの区画で通信できることを確かめてから
# confirm する。つながらなくなったら何もしなくても 10 分で元に戻る。
set -eu

CONF=/etc/network/interfaces
BACKUP=/root/interfaces.pre-vlan-aware
UNIT=shakecloud-vlan-rollback

case "${1:-}" in
apply)
	if grep -q 'bridge-vlan-aware yes' "$CONF"; then
		echo "already vlan-aware"
		exit 0
	fi
	cp -p "$CONF" "$BACKUP"
	systemd-run --unit="$UNIT" --on-active=600 /bin/sh "$(readlink -f "$0")" rollback
	awk '
		{ print }
		/^iface vmbr0 / { in_vmbr0 = 1; next }
		in_vmbr0 && /^[[:space:]]*bridge-fd/ {
			print "\tbridge-vlan-aware yes"
			print "\tbridge-vids 2-4094"
			in_vmbr0 = 0
		}
	' "$BACKUP" >"$CONF"
	ifreload -a
	echo "applied; rolls back in 10 minutes unless confirmed"
	;;
confirm)
	systemctl stop "$UNIT.timer" 2>/dev/null || true
	echo "confirmed"
	;;
rollback)
	[ -f "$BACKUP" ] || { echo "no backup" >&2; exit 1; }
	cp -p "$BACKUP" "$CONF"
	ifreload -a
	logger -t shakecloud "vmbr0 vlan-aware rolled back"
	echo "rolled back"
	;;
*)
	echo "usage: $0 apply|confirm|rollback" >&2
	exit 2
	;;
esac
