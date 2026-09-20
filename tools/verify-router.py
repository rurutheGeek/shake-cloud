#!/usr/bin/env python3
"""Verify the router-01 switch-over against N06's completion conditions.

Run this from a LAN client (dev-b) after the cut-over. It checks the things a
document cannot: that the external UDP ports really fall inside the MAP-E port
set, that the path MTU is the measured 1460, that IPv6 is relayed, and that the
router and host agree with the declared configuration.

    python3 tools/verify-router.py                       # LAN client only
    python3 tools/verify-router.py --pve root@192.168.10.126

Every check reads the canonical files (the UCI config in platform/openwrt, the
declaration in platform/terraform) instead of hardcoding the measured values a
second time. Exit status is non-zero if any check fails.
"""
import argparse
import ipaddress
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
UCI_NETWORK = ROOT / 'platform/openwrt/rootfs/etc/shakecloud/config/network'

PASS, FAIL, WARN = 'PASS', 'FAIL', 'WARN'


class Check:
    """One question and its answer."""

    def __init__(self, name, question, on_failure):
        self.name = name
        self.question = question
        self.on_failure = on_failure
        self.status = WARN
        self.detail = ''

    def record(self, status, detail=''):
        self.status = status
        self.detail = detail
        return status


def load_uci(path):
    """Parse the `wan` interface section of a UCI network file."""
    options = {}
    in_wan = False
    for line in path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if stripped.startswith('config interface'):
            in_wan = stripped.split(None, 2)[-1].strip("'\"") == 'wan'
        elif in_wan and stripped.startswith('option '):
            _, key, value = stripped.split(None, 2)
            options[key] = value.strip("'\"")
    for key in ('proto', 'maptype', 'peeraddr', 'ip6prefix', 'ip6prefixlen',
                'ipaddr', 'ip4prefixlen', 'ealen', 'psidlen', 'offset', 'mtu'):
        if key not in options:
            raise SystemExit(f'{path}: wan.{key} が無い')
    return options


def rule_ipv4_network(wan):
    return ipaddress.ip_network(f"{wan['ipaddr']}/{wan['ip4prefixlen']}", strict=False)


def rule_ipv6_network(wan):
    return ipaddress.ip_network(f"{wan['ip6prefix']}/{wan['ip6prefixlen']}", strict=False)


def psid_of(port, offset, psidlen):
    """The PSID embedded in an observed external port.

    Ports are `A | PSID | j`, with A `offset` bits wide, PSID `psidlen` bits
    wide and j filling the rest. With JPNE's offset=4/psidlen=8, the PSID is
    bits 4..11 (N06's "中央 8 ビット").
    """
    suffix_bits = 16 - offset - psidlen
    return (port >> suffix_bits) & ((1 << psidlen) - 1)


def port_in_set(port, psid, offset, psidlen):
    """Whether an external port belongs to the CE's assigned MAP-E set."""
    suffix_bits = 16 - offset - psidlen
    if suffix_bits < 0 or not 0 <= port <= 0xFFFF:
        return False
    a = port >> (16 - offset) if offset else 0
    if a == 0:
        return False  # A=0 covers the system ports and is not assigned
    return psid_of(port, offset, psidlen) == psid


def parse_portsets(text):
    """'1024-1039 2048-2063' -> [(1024, 1039), (2048, 2063)]."""
    ranges = []
    for entry in text.split():
        low, _, high = entry.partition('-')
        ranges.append((int(low), int(high)))
    return ranges


def parse_rule_data(text):
    """Parse the RULE_* assignments map.sh leaves in /tmp/map-wan.rules."""
    rule = {}
    for line in text.splitlines():
        match = re.match(r'^(RULE_[A-Z0-9_]+)=(.*)$', line.strip())
        if match:
            rule[match.group(1)] = match.group(2).strip("'\"")
    return rule


def psid_from_portsets(ranges, offset, psidlen):
    """The PSID every range in a computed port set shares."""
    suffix_bits = 16 - offset - psidlen
    return (ranges[0][0] >> suffix_bits) & ((1 << psidlen) - 1)


def stun_observe(server, port, timeout=3.0):
    """Ask a STUN server which external address/port it sees."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.bind(('0.0.0.0', 0))
        magic = b'\x21\x12\xa4\x42'
        sock.sendto(struct.pack('>HH', 0x0001, 0) + magic + os.urandom(12),
                    (server, port))
        data, _ = sock.recvfrom(2048)
    finally:
        sock.close()

    offset, end = 20, 20 + struct.unpack('>H', data[2:4])[0]
    while offset < end:
        attr_type, attr_len = struct.unpack('>HH', data[offset:offset + 4])
        if attr_type in (0x0001, 0x0020):
            value = data[offset + 6:offset + 8]
            port_value = struct.unpack('>H', value)[0]
            if attr_type == 0x0020:
                port_value ^= 0x2112
            address = data[offset + 8:offset + 12]
            if attr_type == 0x0020:
                address = bytes(byte ^ mask for byte, mask
                                in zip(address, b'\x21\x12\xa4\x42'))
            return socket.inet_ntoa(address), port_value
        offset += 4 + attr_len + ((4 - attr_len % 4) % 4)
    raise ValueError('STUN 応答に外部アドレスが無い')


def ping_ok(target, size):
    command = ['ping', '-M', 'do', '-s', str(size), '-c', '1', '-W', '3', '-q', target]
    return subprocess.run(command, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0


def largest_payload(target, low=1200, high=1472):
    """Largest ICMP payload that crosses the path unfragmented (None if even low fails)."""
    if not ping_ok(target, low):
        return None
    if ping_ok(target, high):
        return high
    while low + 1 < high:
        middle = (low + high) // 2
        if ping_ok(target, middle):
            low = middle
        else:
            high = middle
    return low


def ssh_run(destination, key, command, timeout=20):
    path = os.path.expanduser(key)
    args = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new',
            '-o', f'ConnectTimeout={min(timeout, 10)}']
    if path and os.path.exists(path):
        args += ['-i', path]
    args += [destination, command]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, 'timed out'
    if result.returncode != 0:
        return None, (result.stderr or result.stdout).strip()[:200]
    return result.stdout, ''


def probe_gateway(check, args, wan):
    result = subprocess.run(['ip', '-4', 'route', 'show', 'default'],
                            capture_output=True, text=True)
    lines = [line for line in result.stdout.splitlines() if line.startswith('default')]
    if not lines:
        return check.record(FAIL, 'IPv4 の既定ルートが無い')
    match = re.search(r'default via (\S+)', lines[0])
    if not match:
        return check.record(FAIL, f'既定ルートを読めない: {lines[0]}')
    default = match.group(1)
    if default != args.router:
        return check.record(FAIL, f'既定ルートが {default} で、ルータ {args.router} ではない')

    if not ping_ok(args.router, 56):
        return check.record(FAIL, f'{args.router} に ping が通らない')

    result = subprocess.run(['ip', '-4', 'neigh', 'show', args.router],
                            capture_output=True, text=True)
    mac_match = re.search(r'([0-9a-f]{2}(?::[0-9a-f]{2}){5})', result.stdout)
    observed_mac = mac_match.group(1) if mac_match else 'unknown'

    expected_mac = args.lan_mac
    if not expected_mac and args.pve:
        output, error = ssh_run(args.pve, args.pve_key,
                                f"qm config {args.vm_id} | sed -n 's/^net1:.*virtio=\\([^,]*\\).*/\\1/p'")
        if output:
            expected_mac = output.strip().lower()
    if expected_mac and observed_mac.lower() != expected_mac.lower():
        return check.record(FAIL, f'{args.router} の MAC が {observed_mac} で、'
                                   f'ルータの LAN MAC {expected_mac} と違う'
                                   '（Aterm がまだ 192.168.10.1 を名乗っている疑い）')
    note = '' if expected_mac else '（LAN MAC の照合はスキップ。--lan-mac か --pve を指定）'
    return check.record(PASS, f'default via {args.router}, MAC {observed_mac}{note}')


def probe_map_ports(check, args, wan):
    server, _, port = args.stun_server.partition(':')
    port = int(port or 19302)
    observations, failures = [], []
    for _ in range(args.samples):
        try:
            observations.append(stun_observe(server, port))
        except Exception as error:  # noqa: BLE001 - a sample failure is data
            failures.append(str(error))
    if len(observations) < 3:
        return check.record(FAIL, f'STUN が {len(observations)}/{args.samples} 回しか'
                                  f'応答しない: {failures[:1]}')

    addresses = {address for address, _ in observations}
    ports = [observed for _, observed in observations]
    psids = {psid_of(p, int(wan['offset']), int(wan['psidlen'])) for p in ports}
    if len(psids) != 1:
        return check.record(FAIL, f'PSID が一致しない（{sorted(psids)}）。'
                                  'MAP-E ではなく DS-Lite 等を疑う')
    psid = psids.pop()
    outside = [p for p in ports
               if not port_in_set(p, psid, int(wan['offset']), int(wan['psidlen']))]
    if outside:
        return check.record(FAIL, f'割当外のポートを観測: {outside}'
                                  f'（PSID {psid}, A は 1..{2 ** int(wan["offset"]) - 1}）')

    network = rule_ipv4_network(wan)
    if not all(ipaddress.ip_address(address) in network for address in addresses):
        return check.record(FAIL, f'外部アドレス {sorted(addresses)} が Rule IPv4 '
                                  f'{network} の外')

    blocks = {p >> (16 - int(wan['offset'])) for p in ports}
    return check.record(PASS, f'外部 {sorted(addresses)} / PSID {psid} / '
                              f'{len(ports)} サンプルがすべて割当内'
                              f'（観測ブロック {sorted(blocks)}）')


def probe_pmtu(check, args, wan):
    expected = int(wan['mtu']) - 28  # ICMP 8 + IPv4 20
    largest = largest_payload(args.pmtu_target)
    if largest is None:
        return check.record(FAIL, f'{args.pmtu_target} へ ICMP が通らず PMTU を測れない')
    if largest != expected:
        return check.record(FAIL, f'フラグメントなしで通る最大ペイロードが {largest}。'
                                  f'MTU {wan["mtu"]} なら {expected} のはず')
    return check.record(PASS, f'最大ペイロード {largest} = MTU {wan["mtu"]}（ping -M do）')


def probe_ipv6(check, args, wan):
    result = subprocess.run(['ip', '-6', '-o', 'addr', 'show', 'scope', 'global'],
                            capture_output=True, text=True)
    addresses = [entry.split()[3].split('/')[0] for entry in result.stdout.splitlines()
                 if len(entry.split()) > 3 and ':' in entry.split()[3]]
    global_unicast = [ipaddress.ip_address(a) for a in addresses
                      if ipaddress.ip_address(a).is_global]
    rule = rule_ipv6_network(wan)
    in_rule = [a for a in global_unicast if a in rule]
    if not in_rule:
        return check.record(FAIL, f'Rule IPv6 {rule} 内の GUA が無い（取得: '
                                  f'{[str(a) for a in global_unicast] or "なし"}）')
    reachable = subprocess.run(
        ['ping', '-6', '-c', '2', '-W', '3', '-q', '2606:4700:4700::1111'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not reachable:
        return check.record(WARN, f'{in_rule[0]} は {rule} 内だが IPv6 へ出られない')
    return check.record(PASS, f'{in_rule[0]} が {rule} 内で、IPv6 へ到達できる')


def probe_router(check, args, wan, observed_psid=None):
    # --router is compared against the default route, so it stays a bare
    # address; the image only bakes the admin key in for root.
    destination = f'{args.router_user}@{args.router}' if args.router_user else args.router
    output, error = ssh_run(destination, args.router_key, (
        "cat /tmp/map-wan.rules 2>/dev/null; echo '==LINK=='; "
        "ip -d link show map-wan 2>&1; echo '==MTU=='; uci get network.wan.mtu"))
    if output is None:
        return check.record(FAIL, f'{destination} へ SSH できない: {error}')

    rules_text, _, rest = output.partition('==LINK==')
    link_text, _, mtu_text = rest.partition('==MTU==')
    rule = parse_rule_data(rules_text)
    if 'RULE_BMR' not in rule or 'RULE_1_PORTSETS' not in rule:
        return check.record(FAIL, 'map-wan.rules に BMR/ポートセットが無い'
                                  '（WAN リンクダウン、または NO_MATCHING_PD）')
    if 'map-wan' not in link_text or 'ipip6' not in link_text:
        return check.record(FAIL, f'map-wan の ipip6 トンネルが無い: {link_text.strip()[:120]}')
    if mtu_text.strip() != wan['mtu']:
        return check.record(FAIL, f'ルータの map MTU が {mtu_text.strip()}（宣言は {wan["mtu"]}）')

    ranges = parse_portsets(rule['RULE_1_PORTSETS'])
    router_psid = psid_from_portsets(ranges, int(wan['offset']), int(wan['psidlen']))
    if observed_psid is not None and observed_psid != router_psid:
        return check.record(FAIL, f'STUN の PSID {observed_psid} とルータの計算 '
                                  f'{router_psid} が違う')
    # `in` on a network needs an address object; a bare str raises AttributeError.
    if rule.get('RULE_1_IPV4ADDR') and (ipaddress.ip_address(rule['RULE_1_IPV4ADDR'])
                                        not in rule_ipv4_network(wan)):
        return check.record(FAIL, f'ルータの IPv4 {rule["RULE_1_IPV4ADDR"]} が '
                                  f'{rule_ipv4_network(wan)} の外')
    return check.record(PASS, f'IPv4 {rule.get("RULE_1_IPV4ADDR")} / PSID {router_psid} / '
                              f'{len(ranges)} ポートセット / MTU {mtu_text.strip()}')


def probe_host_links(check, args, wan):
    if not args.pve:
        return check.record(WARN, '--pve が無いのでホストのリンクを確認していない')
    output, error = ssh_run(args.pve, args.pve_key,
                            "for i in nic0 nic1; do echo \"== $i\"; "
                            "ethtool $i | grep -E 'Speed|Duplex|Link detected'; "
                            "done")
    if output is None:
        return check.record(FAIL, f'{args.pve} へ SSH できない: {error}')

    speeds = {}
    current = None
    for line in output.splitlines():
        if line.startswith('=='):
            current = line.split()[1]
            speeds[current] = {}
        elif current and ':' in line:
            key, _, value = line.partition(':')
            speeds[current][key.strip()] = value.strip()
    bad = [name for name, values in speeds.items()
           if not values.get('Speed', '').startswith('1000')
           or values.get('Link detected') != 'yes']
    if bad:
        return check.record(FAIL, f'1000Mbps リンクでない NIC: '
                                  f'{ {name: speeds[name] for name in bad} }')
    return check.record(PASS, f'nic0/nic1 とも {speeds["nic0"]["Speed"]} フルデュプレクス')


CHECKS = [
    ('gateway', probe_gateway,
     '既定ルートが router-01 で、192.168.10.1 がルータの LAN MAC か？',
     'Aterm がまだゲートウェイを名乗っているか、ルータへ到達できない。'),
    ('map_ports', probe_map_ports,
     '外部ポートが MAP-E の割当（240 ポート）に収まっているか？',
     'MAP-E が成立していない。DS-Lite 等の取り違え、または NAT の不整合。'),
    ('pmtu', probe_pmtu,
     'フラグメントなしで通る最大ペイロードが MTU 1460（1432）か？',
     'MTU/MSS clamp が合っていない。大きなパケットが通らない。'),
    ('ipv6', probe_ipv6,
     'LAN 端末が Rule IPv6 内の GUA で外部へ出られるか？',
     'odhcpd relay が動いていない。ndppd への切替を検討する。'),
    ('router', probe_router,
     'ルータの map-wan と mapcalc の計算が STUN の観測と一致するか？',
     'WAN が未接続、または map/relay の設定が一致していない。'),
    ('host_links', probe_host_links,
     'ホストの nic0/nic1 が 1000Mbps でリンクしているか？',
     'ケーブル不良が再発している。切替を止めて配線を確認する。'),
]


def run(args):
    wan = load_uci(UCI_NETWORK)
    results = []
    observed_psid = None
    for name, function, question, on_failure in CHECKS:
        if args.only and name not in args.only:
            continue
        check = Check(name, question, on_failure)
        try:
            if name == 'router':
                function(check, args, wan, observed_psid)
            else:
                function(check, args, wan)
            if name == 'map_ports' and check.status == PASS:
                match = re.search(r'PSID (\d+)', check.detail)
                observed_psid = int(match.group(1)) if match else None
        except Exception as error:  # a check must never mask the others
            check.record(FAIL, f'{type(error).__name__}: {error}')
        results.append(check)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--router', default='192.168.10.1',
                        help='router-01 のアドレス（SSH と ping）。空文字で router チェックを省く')
    parser.add_argument('--router-user', default='root',
                        help='router-01 の SSH ユーザ。イメージに焼く管理者鍵は root 用')
    parser.add_argument('--router-key', default='~/.ssh/id_ed25519_pve')
    parser.add_argument('--pve', default='',
                        help='Proxmox ホスト（例: root@192.168.10.126）。リンク速度も見る')
    parser.add_argument('--pve-key', default='~/.ssh/id_ed25519_pve')
    parser.add_argument('--vm-id', type=int, default=101)
    parser.add_argument('--lan-mac', default='',
                        help='router-01 の LAN MAC。--pve があれば qm config から取る')
    parser.add_argument('--stun-server', default='stun.l.google.com:19302')
    parser.add_argument('--samples', type=int, default=6)
    parser.add_argument('--pmtu-target', default='8.8.8.8')
    parser.add_argument('--only', action='append', help='run only the named check')
    args = parser.parse_args()

    results = run(args)
    failures = [check for check in results if check.status == FAIL]
    for check in results:
        print(f'{check.status}: {check.name} -- {check.question}')
        print(f'      {check.detail}')
        if check.status == FAIL:
            print(f'      consequence: {check.on_failure}')
    passed = sum(1 for check in results if check.status == PASS)
    warned = sum(1 for check in results if check.status == WARN)
    print(f'--- {passed} PASS / {len(failures)} FAIL / {warned} WARN')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
