#!/bin/bash
# Flint 3 の切替試験。配線を変えずに、時間を区切って Flint 3 をルーターにし、
# 確認結果を記録して、必ず router-01 の構成へ戻す。
#
#   platform/flint3/trial.sh prepare   # ONU を VLAN 100 で Flint 3 へ届ける道を作る（通信は止まらない）
#   platform/flint3/trial.sh run       # 試験（約12分。その間インターネットが切れる）
#   platform/flint3/trial.sh cleanup   # prepare で作った道を消す
#   platform/flint3/trial.sh switch    # 自動では戻さない切替。期限までに heartbeat が無ければ戻る
#   platform/flint3/trial.sh heartbeat 300   # 期限を今から 300 秒後へ延ばす
#   platform/flint3/trial.sh rollback  # router-01 の構成へ戻す
#
# LAN 内の固定アドレスの端末（dev-02）から実行する。ONU は K11 の nic0（vmbr1）に
# つながっているので、K11 で nic1.100 を vmbr1 へ入れ、Flint 3 は eth0.100 を
# 上流として使う。K11 と Flint 3 の間のケーブル1本に、LAN（タグなし）と
# ONU（タグ 100）が同居する。
#
# 戻す仕組みは3重:
#   1. このスクリプトが試験の最後に戻す
#   2. Flint 3 の apply-router が 10 分で自分の設定を戻して再起動する
#   3. K11 のタイマーが 14 分で router-01 のリンクを上げる
set -euo pipefail

key="${FLINT3_SSH_KEY:-$HOME/.ssh/id_ed25519_pve}"
pve="root@192.168.10.10"
ap_ip=192.168.10.5
gw_ip=192.168.10.1
vlan=100
minutes="${TRIAL_MINUTES:-8}"
out="${TRIAL_OUT:-$HOME/flint3-trial}"
ssh_opts=(-o BatchMode=yes -o ConnectTimeout=5 -i "$key")
# 試験中は Flint 3 が 192.168.10.1 を名乗る。known_hosts には router-01 の鍵が
# あるので、Flint 3 の鍵（192.168.10.5 として登録済み）で照合する。
flint_gw=(ssh "${ssh_opts[@]}" -o HostKeyAlias="$ap_ip" "root@$gw_ip")
flint_ap=(ssh "${ssh_opts[@]}" "root@$ap_ip")
host=(ssh "${ssh_opts[@]}" "$pve")

net0='virtio=BC:24:11:67:7F:25,bridge=vmbr1,firewall=0'
net1='virtio=BC:24:11:84:B9:80,bridge=vmbr0'

log() { echo "$(date +%T) $*" | tee -a "$out/trial.log"; }

prepare() {
	# 先に Flint 3 側で受け口を作る。逆順だと、タグ付きのフレームが br-lan を
	# 素通りして LAN へ流れる。
	"${flint_ap[@]}" "ip link show eth0.$vlan >/dev/null 2>&1 || { ip link add link eth0 name eth0.$vlan type vlan id $vlan; echo 0 > /proc/sys/net/ipv6/conf/eth0.$vlan/accept_ra; echo 1 > /proc/sys/net/ipv6/conf/eth0.$vlan/disable_ipv6; ip link set eth0.$vlan up; }"
	"${host[@]}" "ip link show nic1.$vlan >/dev/null 2>&1 || { ip link add link nic1 name nic1.$vlan type vlan id $vlan; ip link set nic1.$vlan master vmbr1; ip link set nic1.$vlan up; }"
	sleep 15
	"${flint_ap[@]}" "ip -s link show eth0.$vlan | sed -n '1p;3,4p'"
}

cleanup() {
	"${host[@]}" "ip link del nic1.$vlan 2>/dev/null || true"
	"${flint_ap[@]}" "ip link del eth0.$vlan 2>/dev/null || true"
}

restore_router01() {
	"${host[@]}" "qm set 101 -net0 '$net0' -net1 '$net1' >/dev/null && echo router-01 links up"
}

verify() {
	log "== Flint 3"
	"${flint_gw[@]}" '
		echo "-- ifstatus"; for i in wan6 wan; do ifstatus $i | grep -E "\"(up|proto|l3_device)\"|\"address\"|\"mask\"|errors|code" | tr -s " \t\n" " "; echo; done
		echo "-- map rules"; grep -E "IPV4ADDR|PSID=|IPV6ADDR|PORTSETS" /tmp/map-wan.rules 2>&1 | cut -c1-200
		echo "-- addr"; ip -br addr | grep -E "map-wan|eth0|br-lan"
		echo "-- mape_nat"; nft list table ip mape_nat 2>&1 | grep -c "snat to"
		echo "-- v6 route"; ip -6 route | grep -E "br-lan|default" | head -4
		echo "-- ping4"; ping -4 -c 3 -W 2 8.8.8.8 | tail -2
		echo "-- ce address on wan device"; ip -6 addr show dev "$(ubus call network.interface.wan6 status | jsonfilter -e "@.l3_device")" | grep -c "/128"
		echo "-- ping6"; ping -6 -c 3 -W 2 2001:4860:4860::8888 | tail -2
		echo "-- services"; for s in dnsmasq odhcpd ndppd adguardhome; do echo -n "$s:"; pgrep -f "$s" >/dev/null && echo up || echo DOWN; done
		echo "-- listen"; netstat -lntu | grep -E ":(53|3053|3000|67) " | awk "{print \$1,\$4}" | sort -u | tr "\n" ";"; echo
		echo "-- kmwan/log"; logread | grep -iE "map|mapcalc|kmwan|ndppd|odhcp6c.*(fail|error)|adguard.*(fatal|error)" | tail -25
	' 2>&1 | tee -a "$out/trial.log" || true

	log "== LAN 端末（dev-02）"
	{
		echo "-- dns via $gw_ip"; host -W 3 example.com "$gw_ip" 2>&1 | tail -3
		echo "-- dns block"; host -W 3 doubleclick.net "$gw_ip" 2>&1 | tail -3
		echo "-- dns lan name"; host -W 3 netbox.apextox.dpdns.org "$gw_ip" 2>&1 | tail -3
		echo "-- ping v4/v6 by address"; ping -4 -c 2 -W 2 8.8.8.8 | tail -1; ping -6 -c 2 -W 2 2001:4860:4860::8888 | tail -1
		echo "-- pmtu 1432/1433"; ping -4 -c 2 -W 2 -M 'do' -s 1432 8.8.8.8 2>&1 | tail -1; ping -4 -c 2 -W 2 -M 'do' -s 1433 8.8.8.8 2>&1 | tail -1
		echo "-- external v4"; curl -4 -s -m 8 https://api.ipify.org; echo
		echo "-- external v6"; curl -6 -s -m 8 https://api64.ipify.org | cut -c1-19; echo
		echo "-- https v4/v6"; curl -4 -s -o /dev/null -m 10 -w "v4 %{http_code} %{time_total}s\n" https://www.google.com/; curl -6 -s -o /dev/null -m 10 -w "v6 %{http_code} %{time_total}s\n" https://www.google.com/
		echo "-- nichiban"; curl -4 -s -o /dev/null -m 20 -w "%{http_code} %{time_total}s\n" https://www.nichiban.co.jp/
		echo "-- 300 parallel connections"; seq 300 | xargs -P 150 -I{} curl -4 -s -o /dev/null -m 8 -w "%{http_code}\n" https://www.gstatic.com/generate_204 | sort | uniq -c
		echo "-- speed v4 (15s)"; curl -4 -s -o /dev/null -m 15 -w "%{speed_download} B/s (%{size_download} bytes)\n" http://ftp.riken.jp/Linux/ubuntu-releases/24.04/ubuntu-24.04.5-live-server-amd64.iso || true
		echo "-- speed v4 (15s)"; curl -4 -s -o /dev/null -m 15 -w "%{speed_download} B/s (%{size_download} bytes)\n" http://ftp.riken.jp/Linux/ubuntu-releases/24.04/ubuntu-24.04.5-live-server-amd64.iso || true
	} 2>&1 | tee -a "$out/trial.log" || true

	log "== ポートの分散（Flint 3 の conntrack）"
	"${flint_gw[@]}" '
		. /tmp/map-wan.rules 2>/dev/null
		conntrack -L -p tcp 2>/dev/null | sed -nE "s/.* dst=$RULE_1_IPV4ADDR sport=[0-9]+ dport=([0-9]+).*/\1/p" | awk "{b[int(\$1/4096)]++; n++} END{for(k in b) printf \"block %d: %d\n\", k, b[k]; printf \"total %d\n\", n}" | sort -t" " -k2 -n
		echo "-- cpu"; top -bn1 | sed -n "2p"
	' 2>&1 | tee -a "$out/trial.log" || true
}

run() {
	mkdir -p "$out"
	: > "$out/trial.log"
	log "trial start (minutes=$minutes)"
	"${flint_ap[@]}" "ip link show eth0.$vlan >/dev/null" || { log "prepare を先に実行する"; exit 1; }

	# 予約（NetBox 由来）を写す。試験中も固定アドレスの機器が同じ IP を受けられる。
	ssh "${ssh_opts[@]}" "root@$gw_ip" 'cat /etc/dnsmasq.d/netbox-reservations.conf' > "$out/netbox-reservations.conf"
	"${flint_ap[@]}" 'mkdir -p /etc/dnsmasq.d && cat > /etc/dnsmasq.d/netbox-reservations.conf' < "$out/netbox-reservations.conf"

	# 安全網: 14 分後に K11 が router-01 のリンクを上げ直す。
	"${host[@]}" "systemctl stop flint3-trial-restore.timer flint3-trial-restore.service 2>/dev/null; systemctl reset-failed flint3-trial-restore.service 2>/dev/null; systemd-run --unit flint3-trial-restore --on-active=14min /bin/sh -c \"/usr/sbin/qm set 101 -net0 '$net0' -net1 '$net1'; ip link del nic1.$vlan\"" 2>&1 | tee -a "$out/trial.log"

	log "router-01 を切り離す"
	"${host[@]}" "qm set 101 -net0 '$net0,link_down=1' -net1 '$net1,link_down=1' >/dev/null"

	log "Flint 3 をルーターにする"
	started=$(date +%s)
	"${flint_ap[@]}" "ip link del eth0.$vlan; WAN_DEVICE=eth0.$vlan /etc/shakecloud/apply-router" 2>&1 | tee -a "$out/trial.log" || true

	# 起動を待つ（MAP-E が上がるまで）。
	for _ in $(seq 1 30); do
		sleep 5
		"${flint_gw[@]}" 'ifstatus wan 2>/dev/null | grep -q "\"up\": true"' 2>/dev/null && break
	done
	log "wan up を確認、または待ち時間切れ"
	sleep 45

	verify
	# Flint 3 自身の巻き戻し（10 分）より前に、2回目の確認と復帰を終える。
	left=$(( started + minutes * 60 - 150 - $(date +%s) ))
	if [ "$left" -gt 0 ]; then sleep "$left"; fi
	log "== 終了前の再確認"
	verify

	log "Flint 3 を元へ戻す"
	"${flint_gw[@]}" '(sleep 1; /etc/shakecloud/rollback-router) >/dev/null 2>&1 </dev/null &' 2>&1 | tee -a "$out/trial.log" || true
	sleep 20
	restore_router01 2>&1 | tee -a "$out/trial.log"
	# Flint 3 が AP 構成で戻る前に VLAN の道を消す（残すとタグ付きのフレームが LAN へ流れる）。
	"${host[@]}" "ip link del nic1.$vlan 2>/dev/null; systemctl stop flint3-trial-restore.timer 2>/dev/null || true"
	for _ in $(seq 1 40); do
		sleep 5
		ping -c1 -W1 "$ap_ip" >/dev/null 2>&1 && break
	done
	sleep 15
	log "== 復帰の確認"
	{
		ping -c 2 -W 2 "$gw_ip" | tail -1
		curl -4 -s -m 10 https://api.ipify.org; echo
		"${flint_ap[@]}" 'ip -br addr show br-lan; uci get dhcp.lan.ignore; uci get network.wan.proto'
	} 2>&1 | tee -a "$out/trial.log" || true
	log "trial end"
}

# 巻き戻しの期限を延ばす。Flint 3 が先に戻り、その 90 秒後に K11 が router-01 を上げる。
heartbeat() {
	local seconds="${1:-300}"
	"${flint_gw[@]}" "/etc/shakecloud/apply-router extend $seconds"
	"${host[@]}" "systemctl stop flint3-trial-restore.timer 2>/dev/null; systemctl reset-failed flint3-trial-restore.service 2>/dev/null; systemd-run -q --unit flint3-trial-restore --on-active=$((seconds + 90)) /root/restore-router01.sh"
}

# 自動では戻さない切替。期限までに heartbeat が来なければ戻る。
switch() {
	mkdir -p "$out"
	: > "$out/trial.log"
	log "switch start"
	prepare | tee -a "$out/trial.log"
	ssh "${ssh_opts[@]}" "root@$gw_ip" 'cat /etc/dnsmasq.d/netbox-reservations.conf' > "$out/netbox-reservations.conf"
	"${flint_ap[@]}" 'mkdir -p /etc/dnsmasq.d && cat > /etc/dnsmasq.d/netbox-reservations.conf' < "$out/netbox-reservations.conf"
	"${host[@]}" "systemctl stop flint3-trial-restore.timer 2>/dev/null; systemctl reset-failed flint3-trial-restore.service 2>/dev/null; systemd-run -q --unit flint3-trial-restore --on-active=690 /root/restore-router01.sh"
	log "router-01 を切り離す"
	"${host[@]}" "qm set 101 -net0 '$net0,link_down=1' -net1 '$net1,link_down=1' >/dev/null"
	log "Flint 3 をルーターにする（最初の期限は 10 分）"
	"${flint_ap[@]}" "ip link del eth0.$vlan; ROLLBACK_AFTER=600 WAN_DEVICE=eth0.$vlan /etc/shakecloud/apply-router" 2>&1 | tee -a "$out/trial.log" || true
	# IPv4 が通るまで待つ（上流の記憶が切り替わるまで）。
	for i in $(seq 1 90); do
		sleep 5
		if curl -4 -s -m 4 -o /dev/null https://www.gstatic.com/generate_204; then
			log "IPv4 が通った（約 $((i * 5 + 5)) 秒後）"
			break
		fi
	done
	verify
	log "switch done"
}

rollback() {
	"${flint_gw[@]}" '(sleep 1; /etc/shakecloud/rollback-router) >/dev/null 2>&1 </dev/null &' || true
	sleep 20
	"${host[@]}" "/root/restore-router01.sh; systemctl stop flint3-trial-restore.timer 2>/dev/null || true"
}

case "${1:-}" in
	prepare) prepare ;;
	run) run ;;
	switch) switch ;;
	heartbeat) heartbeat "${2:-300}" ;;
	rollback) rollback ;;
	cleanup) cleanup ;;
	*) sed -n '2,8p' "$0"; exit 2 ;;
esac
