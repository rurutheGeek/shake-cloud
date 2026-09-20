#!/usr/bin/env python3
"""Keep NetBox and the OpenWrt router's DHCP in step.

NetBox is the source of truth for the infrastructure band (static devices:
AP, printer, Pis, the Proxmox host). The router's dnsmasq is the source of
truth for what is actually leased. This tool bridges the two:

    ensure  NetBox の dcim を platform/netbox/devices.yaml に合わせる
    pull    NetBox の reserved IP を dnsmasq の予約（/etc/dnsmasq.d）へ反映
    push    ルータの DHCP リースを NetBox の IPAddress(status=dhcp) へ写す

NetBox の資格情報は環境変数で渡す（リポジトリの他のツールと同じ）:

    sops exec-env platform/sops/netbox.sops.yaml \
      'python3 tools/netbox-dhcp-sync.py pull'

`--dry-run` は書き込まずに差分だけを出す。MAC は NetBox 4.x の
interface.mac_address に持つ（Terraform Provider は読み取り専用なので API で扱う）。
"""
import argparse
import ipaddress
from pathlib import Path
import os
import re
import subprocess
import sys

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
NETWORK = ROOT / 'platform/terraform/network.yaml'
DEVICES = ROOT / 'platform/netbox/devices.yaml'
RESERVATIONS_FILE = '/etc/dnsmasq.d/netbox-reservations.conf'
LEASES_FILE = '/tmp/dhcp.leases'
DEFAULT_KEY = '~/.ssh/id_ed25519_pve'


class NetBoxError(SystemExit):
    pass


class NetBox:
    def __init__(self, url, token):
        self.base = url.rstrip('/') + '/api'
        self.session = requests.Session()
        self.session.headers['Authorization'] = f'Token {token}'
        self.session.verify = False

    def get(self, path, **params):
        response = self.session.get(self.base + path, params=params, timeout=30)
        if response.status_code != 200:
            raise NetBoxError(f'NetBox GET {path} HTTP {response.status_code}: {response.text[:200]}')
        return response.json()

    def one(self, path, **params):
        """Return the single result, or None. Refuses an ambiguous answer."""
        params.setdefault('limit', 2)
        results = self.get(path, **params)['results']
        if len(results) > 1:
            raise NetBoxError(f'NetBox GET {path} {params} が複数返した')
        return results[0] if results else None

    def post(self, path, payload):
        response = self.session.post(self.base + path, json=payload, timeout=30)
        if response.status_code not in (200, 201):
            raise NetBoxError(f'NetBox POST {path} HTTP {response.status_code}: {response.text[:200]}')
        return response.json()

    def patch(self, path, payload):
        response = self.session.patch(self.base + path, json=payload, timeout=30)
        if response.status_code != 200:
            raise NetBoxError(f'NetBox PATCH {path} HTTP {response.status_code}: {response.text[:200]}')
        return response.json()


def load_yaml(path):
    return yaml.safe_load(path.read_text(encoding='utf-8'))


def range_of(section):
    """The span from range_start to range_end (inclusive) as a list of addresses."""
    first = ipaddress.ip_interface(section['range_start']).ip
    last = ipaddress.ip_interface(section['range_end']).ip
    return first, last


def in_range(address, section):
    first, last = range_of(section)
    value = ipaddress.ip_interface(address).ip
    return first <= value <= last


def parse_leases(text):
    """dnsmasq のリース行を (mac, ip, hostname) にする。

    行は `<expiry> <mac> <ip> <hostname> <clientid>`。hostname は `*` のことがある。
    """
    leases = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        mac, address, hostname = fields[1], fields[2], fields[3]
        if not re.match(r'^[0-9a-f]{2}(:[0-9a-f]{2}){5}$', mac.lower()):
            continue
        leases.append({'mac': mac.lower(), 'address': address,
                       'hostname': '' if hostname == '*' else hostname})
    return leases


def normalize_mac(mac):
    return mac.strip().lower().replace('-', ':')


def render_hosts(records):
    """reserved な機器を dnsmasq の dhcp-host 行にする。

    records は {mac, address, name} の辞書。address は CIDR 付きでもよい。
    MAC の無い機器（プリンタなど）は予約できないので落とす。
    """
    lines = []
    for record in sorted(records, key=lambda r: ipaddress.ip_interface(r['address']).ip):
        if not record.get('mac'):
            continue
        address = str(ipaddress.ip_interface(record['address']).ip)
        lines.append(f"dhcp-host={normalize_mac(record['mac'])},{address},{record['name']}")
    return lines


def render_file(records):
    header = [
        '# NetBox が生成する dnsmasq の予約。**手で編集しない。**',
        '# 正本は NetBox の reserved な IPAddress（宣言は platform/netbox/devices.yaml）。',
        '# 生成: tools/netbox-dhcp-sync.py pull',
    ]
    return '\n'.join(header + render_hosts(records)) + '\n'


def ssh_run(destination, key, command, timeout=30, input_text=None):
    path = os.path.expanduser(key)
    args = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new',
            '-o', f'ConnectTimeout={min(timeout, 10)}']
    if path and os.path.exists(path):
        args += ['-i', path]
    args += [destination, command]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                                input=input_text)
    except subprocess.TimeoutExpired:
        return None, 'timed out'
    if result.returncode != 0:
        return None, (result.stderr or result.stdout).strip()[:200]
    return result.stdout, ''


def ensure_devices(api, spec, dry_run=False):
    """NetBox の dcim を devices.yaml に合わせる（足りない物だけ作る）。"""
    actions = []

    def find_or_create(path, lookup, payload, label):
        found = api.one(path, **lookup)
        if found:
            return found
        if dry_run:
            actions.append(f'create {label}')
            return {'id': None, 'dry': True}
        created = api.post(path, payload)
        actions.append(f'create {label}')
        return created

    site = api.one('/dcim/sites/', name=spec['site'])
    if not site:
        raise NetBoxError(f"NetBox に site {spec['site']} が無い")

    roles = {}
    for role in spec.get('roles', []):
        found = find_or_create('/dcim/device-roles/',
                               {'slug': role['slug']},
                               {'name': role['name'], 'slug': role['slug'],
                                'color': role['color_hex']},
                               f"role {role['slug']}")
        roles[role['name']] = found

    manufacturers = {}
    for maker in spec.get('manufacturers', []):
        found = find_or_create('/dcim/manufacturers/',
                               {'slug': maker['slug']},
                               {'name': maker['name'], 'slug': maker['slug']},
                               f"manufacturer {maker['slug']}")
        manufacturers[maker['name']] = found

    device_types = {}
    for entry in spec.get('device_types', []):
        found = api.one('/dcim/device-types/', slug=entry['slug'])
        if not found:
            if dry_run:
                actions.append(f"create device_type {entry['slug']}")
                found = {'id': None, 'dry': True}
            else:
                found = api.post('/dcim/device-types/', {
                    'manufacturer': manufacturers[entry['manufacturer']]['id'],
                    'model': entry['model'], 'slug': entry['slug']})
                actions.append(f"create device_type {entry['slug']}")
        device_types[entry['model']] = found

    for device in spec['devices']:
        found = api.one('/dcim/devices/', name=device['name'])
        if not found:
            if dry_run:
                actions.append(f"create device {device['name']}")
                continue
            found = api.post('/dcim/devices/', {
                'name': device['name'],
                'device_type': device_types[device['device_type']]['id'],
                'role': roles[device['role']]['id'],
                'site': site['id'],
                'status': 'active',
                'description': device.get('description', ''),
            })
            actions.append(f"create device {device['name']}")

        interface = api.one('/dcim/interfaces/', device_id=found['id'],
                            name=device['interface']['name'])
        if not interface:
            if dry_run:
                actions.append(f"create interface {device['name']}/{device['interface']['name']}")
                continue
            interface = api.post('/dcim/interfaces/', {
                'device': found['id'],
                'name': device['interface']['name'],
                'type': device['interface']['type'],
            })
            actions.append(f"create interface {device['name']}/{device['interface']['name']}")

        mac = device['interface'].get('mac')
        if mac and normalize_mac(interface.get('mac_address') or '') != normalize_mac(mac):
            if dry_run:
                actions.append(f"set mac {device['name']} -> {mac}")
            else:
                api.patch(f"/dcim/interfaces/{interface['id']}/",
                          {'mac_address': normalize_mac(mac)})
                actions.append(f"set mac {device['name']} -> {mac}")

        address = device.get('address')
        if not address:
            continue
        existing = api.one('/ipam/ip-addresses/', address=address)
        payload = {
            'address': address,
            'status': 'reserved',
            'dns_name': device.get('dns_name', device['name']),
            'description': f"{device['name']} ({device['role']})",
            'assigned_object_type': 'dcim.interface',
            'assigned_object_id': interface['id'],
        }
        if not existing:
            if dry_run:
                actions.append(f"create ip {address} ({device['name']})")
            else:
                api.post('/ipam/ip-addresses/', payload)
                actions.append(f"create ip {address} ({device['name']})")
        elif existing.get('status', {}).get('value') != 'reserved' or \
                existing.get('dns_name') != payload['dns_name']:
            if dry_run:
                actions.append(f"update ip {address} ({device['name']})")
            else:
                api.patch(f"/ipam/ip-addresses/{existing['id']}/",
                          {'status': 'reserved', 'dns_name': payload['dns_name'],
                           'description': payload['description'],
                           'assigned_object_type': 'dcim.interface',
                           'assigned_object_id': interface['id']})
                actions.append(f"update ip {address} ({device['name']})")

    return actions


def reserved_records(api, infrastructure):
    """NetBox の reserved IP（機器帯）を {mac, address, name} にする。"""
    records = []
    for entry in api.get('/ipam/ip-addresses/', status='reserved', limit=200)['results']:
        if not in_range(entry['address'], infrastructure):
            continue
        mac = ''
        if entry.get('assigned_object_type') == 'dcim.interface':
            interface = api.get(f"/dcim/interfaces/{entry['assigned_object_id']}/")
            mac = interface.get('mac_address') or ''
        records.append({'mac': mac, 'address': entry['address'],
                        'name': entry.get('dns_name') or ''})
    return records


def pull(api, args):
    network = load_yaml(NETWORK)
    records = reserved_records(api, network['infrastructure'])
    desired = render_file(records)
    current, error = ssh_run(args.router, args.key,
                             f'cat {RESERVATIONS_FILE} 2>/dev/null || true')
    if current is None:
        raise SystemExit(f'{args.router} へ SSH できない: {error}')
    if current == desired:
        print('pull: 予約は既に一致（変更なし）')
        return 0
    if args.dry_run:
        print('pull: 差分あり（--dry-run のため書き込まない）')
        print(desired)
        return 0
    output, error = ssh_run(args.router, args.key,
                            f'cat > {RESERVATIONS_FILE} && /etc/init.d/dnsmasq restart'
                            ' && sleep 2 && pidof dnsmasq >/dev/null',
                            timeout=60, input_text=desired)
    if output is None:
        raise SystemExit(f'書き込みに失敗（dnsmasq が起動しない可能性）: {error}')
    missing = [r['name'] for r in records if not r['mac']]
    print(f'pull: {len(render_hosts(records))} 件の予約を反映'
          + (f"（MAC 未登録でスキップ: {', '.join(missing)}）" if missing else ''))
    return 0


def push(api, args):
    network = load_yaml(NETWORK)
    dhcp = network['dhcp']
    text, error = ssh_run(args.router, args.key, f'cat {LEASES_FILE}')
    if text is None:
        raise SystemExit(f'{args.router} へ SSH できない: {error}')
    leases = parse_leases(text)
    actions = []

    for lease in leases:
        if not in_range(lease['address'], dhcp):
            continue
        existing = api.one('/ipam/ip-addresses/', address=f"{lease['address']}/24")
        description = f"DHCP lease {lease['mac']}" + (f" ({lease['hostname']})"
                                                       if lease['hostname'] else '')
        if existing:
            if existing.get('status', {}).get('value') == 'reserved':
                continue  # 固定機器。リースで上書きしない
            if existing.get('description') == description and \
                    existing.get('dns_name') == lease['hostname']:
                continue
            actions.append(f"update {lease['address']} ({lease['hostname'] or lease['mac']})")
            if not args.dry_run:
                api.patch(f"/ipam/ip-addresses/{existing['id']}/",
                          {'status': 'dhcp', 'dns_name': lease['hostname'],
                           'description': description})
        else:
            actions.append(f"create {lease['address']} ({lease['hostname'] or lease['mac']})")
            if not args.dry_run:
                api.post('/ipam/ip-addresses/', {
                    'address': f"{lease['address']}/24", 'status': 'dhcp',
                    'dns_name': lease['hostname'], 'description': description})

    live = {lease['address'] for lease in leases}
    for entry in api.get('/ipam/ip-addresses/', status='dhcp', limit=200)['results']:
        if not in_range(entry['address'], dhcp):
            continue
        address = str(ipaddress.ip_interface(entry['address']).ip)
        if address in live:
            continue
        actions.append(f"expire {address}")
        if not args.dry_run:
            api.patch(f"/ipam/ip-addresses/{entry['id']}/",
                      {'status': 'deprecated',
                       'description': (entry.get('description') or '') + ' (lease expired)'})

    if args.dry_run:
        print('push: 差分（--dry-run のため書き込まない）')
    print('\n'.join(actions) if actions else 'push: 台帳は既に一致（変更なし）')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['ensure', 'pull', 'push'])
    parser.add_argument('--router', default='root@192.168.10.1')
    parser.add_argument('--key', default=DEFAULT_KEY)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    url = os.environ.get('NETBOX_SERVER_URL')
    token = os.environ.get('NETBOX_API_TOKEN')
    if not (url and token):
        raise SystemExit('NETBOX_SERVER_URL と NETBOX_API_TOKEN を設定する'
                         '（sops exec-env platform/sops/netbox.sops.yaml ...）')
    api = NetBox(url, token)

    if args.command == 'ensure':
        actions = ensure_devices(api, load_yaml(DEVICES), dry_run=args.dry_run)
        print('\n'.join(actions) if actions else 'ensure: NetBox は既に一致（変更なし）')
        return 0
    if args.command == 'pull':
        return pull(api, args)
    return push(api, args)


if __name__ == '__main__':
    sys.exit(main())
