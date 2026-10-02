#!/usr/bin/env python3
"""Keep NetBox and the OpenWrt router's DHCP in step.

NetBox is the source of truth for the physical devices (not only the ones on
the network: microcontrollers, microphones and unmanaged switches live in the
dcim without an interface or an address) and for reserved addresses in the
DHCP pool (static clients that must not collide with leases). The router's
dnsmasq is the source of truth for what is actually leased. This tool bridges
them:

    ensure    NetBox の dcim を platform/netbox/devices.yaml に合わせる（ネット接続の無い機器も含む）
    pull      NetBox の reserved IP を dnsmasq の予約（/etc/dnsmasq.d）へ反映
    push      ルータの DHCP リースを NetBox の IPAddress(status=dhcp) へ写す
    discover  LAN の ARP とリースを一覧し、未宣言の機器を提案する（読むだけ）

**静的な IP の端末は自動では登録されない**（リースを取らないため）。
`devices.yaml` に宣言して `ensure` → `pull` すると、予約として台帳に載り、
dnsmasq がその IP を他の端末へ配らなくなる。

NetBox の資格情報は環境変数で渡す（リポジトリの他のツールと同じ）:

    sops exec-env platform/sops/netbox.sops.yaml \
      'python3 tools/netbox-dhcp-sync.py pull'

`--dry-run` は書き込まずに差分だけを出す。MAC は NetBox 4.x の
interface.mac_address に持つ（Terraform Provider は読み取り専用なので API で扱う）。
"""
import argparse
from datetime import date
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
# リースの「不在」を信用してよいのは、ルータがこれだけ起動してから。
# /tmp は tmpfs でリースDBは再起動で空になり、端末が取り直すまで
# 「リースが消えた」ように見える。リース期間（12h）より短いと、
# 再起動のたびに台帳を消してしまう（2026-09-20 に実際に起きた）。
LEASE_TRUST_SECONDS = 12 * 3600
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

    def delete(self, path):
        response = self.session.delete(self.base + path, timeout=30)
        if response.status_code != 204:
            raise NetBoxError(f'NetBox DELETE {path} HTTP {response.status_code}: {response.text[:200]}')


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


def parse_neigh(text):
    """`ip neigh show dev br-lan` の行を {address, mac, state} にする。

    lladdr の無い行（FAILED など）と IPv6 は落とす。
    """
    entries = []
    for line in text.splitlines():
        fields = line.split()
        if 'lladdr' not in fields:
            continue
        if not re.match(r'^\d+\.\d+\.\d+\.\d+$', fields[0]):
            continue
        index = fields.index('lladdr')
        mac = fields[index + 1].lower()
        if not re.match(r'^[0-9a-f]{2}(:[0-9a-f]{2}){5}$', mac):
            continue
        state = fields[index + 2] if len(fields) > index + 2 else ''
        entries.append({'address': fields[0], 'mac': mac, 'state': state})
    return entries


def interface_specs(device):
    """devices.yaml の `interface` / `interfaces` を1つの並びにする。

    `interface` は口が1つのとき、`interfaces` は複数のとき（PC の eth0 + wlan0、
    Pi の有線 + Wi-Fi など）。両方は書かない。
    """
    specs = []
    if device.get('interface'):
        specs.append(device['interface'])
    specs.extend(device.get('interfaces', []))
    return specs


def declared_macs(spec):
    """devices.yaml で宣言済みの MAC（devices と clients の両方）。"""
    macs = set()
    for device in spec.get('devices', []):
        for interface in interface_specs(device):
            if interface.get('mac'):
                macs.add(normalize_mac(interface['mac']))
    for client in spec.get('clients', []):
        if client.get('mac'):
            macs.add(normalize_mac(client['mac']))
    return macs


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


def render_names(records):
    """reserved な機器の名前を dnsmasq の host-record 行にする。

    `dhcp-host` は実際にリースを配った端末にしか DNS 名を付けない。静的 IP の
    端末（Pi・AP・Proxmox など）は DHCP に来ないため名前が生えない。リースの
    有無と無関係に引けるよう、名前は `host-record` でも書く。MAC が無い機器
    （プリンタなど）にも名前を付けられる。
    """
    lines = []
    for record in sorted(records, key=lambda r: ipaddress.ip_interface(r['address']).ip):
        if not record.get('name'):
            continue
        address = str(ipaddress.ip_interface(record['address']).ip)
        name = record['name']
        if '.' not in name:
            name = f'{name}.lan'
        lines.append(f'host-record={name},{address}')
    return lines


def render_clients(clients):
    """名前だけ付けるクライアント。IP は動的のまま、DNS 名だけ登録する。"""
    return [f"dhcp-host={normalize_mac(client['mac'])},{client['name']}"
            for client in sorted(clients, key=lambda c: c['name'])]


def declared_clients(spec):
    """名前だけ付ける DHCP クライアント（固定IPを持たない機器）。

    `clients` の宣言に加え、devices のうち address を持たず MAC を持つ口も
    含める（Wi-Fi 家電など。MAC が分かったら interface に書くだけで名前が付く）。
    同じ MAC は1つに畳む（dnsmasq は重複した dhcp-host で起動に失敗する）。
    """
    names = {}
    for client in spec.get('clients', []):
        names[normalize_mac(client['mac'])] = client['name']
    for device in spec.get('devices', []):
        if device.get('address') or device.get('dhcp') is False:
            continue
        for interface in interface_specs(device):
            mac = interface.get('mac')
            if mac:
                names.setdefault(normalize_mac(mac), device.get('dns_name', device['name']))
    return [{'mac': mac, 'name': name} for mac, name in names.items()]


def client_names(spec):
    return {normalize_mac(client['mac']): client['name']
            for client in declared_clients(spec)}


def lease_name(lease, names):
    """台帳に書く名前。クライアントが送った名前を優先し、無ければ宣言を使う。"""
    return lease['hostname'] or names.get(lease['mac'], '')


def render_file(records, clients=()):
    header = [
        '# NetBox が生成する dnsmasq の予約。**手で編集しない。**',
        '# 正本は NetBox の reserved な IPAddress（宣言は platform/netbox/devices.yaml）。',
        '# 生成: tools/netbox-dhcp-sync.py pull',
    ]
    names = render_names(records)
    if names:
        names = ['# 静的 IP の端末はリースを取らないため、DNS 名は host-record で別に書く。'] + names
    return '\n'.join(header + render_hosts(records) + names + render_clients(clients)) + '\n'


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


def reference_id(value):
    """参照フィールド（NetBox は {'id': ..} で返す）から id を取り出す。"""
    return value.get('id') if isinstance(value, dict) else value


def choice_value(value):
    """選択フィールド（NetBox は {'value': ..} で返す）から値を取り出す。"""
    return value.get('value') if isinstance(value, dict) else value


# ケーブルの端点。YAML のキー → NetBox の object_type → API の置き場。
CABLE_ENDPOINTS = (
    ('interface', 'dcim.interface', '/dcim/interfaces/'),
    ('power_port', 'dcim.powerport', '/dcim/power-ports/'),
    ('power_outlet', 'dcim.poweroutlet', '/dcim/power-outlets/'),
)


def custom_field_values(device, names):
    """devices.yaml の項目を NetBox の custom_fields へ書ける形にする。

    names は spec の `custom_fields` に宣言した名前。日付は API が受け取る
    ISO 文字列にする（YAML は date として読むため）。
    """
    values = {}
    for field in names:
        if field in device:
            value = device[field]
            if isinstance(value, date):
                value = value.isoformat()
            values[field] = value
    return values


def endpoint_name(end):
    """ケーブル端点の口の名前（interface / power_port / power_outlet）。"""
    for kind, _, _ in CABLE_ENDPOINTS:
        if end.get(kind):
            return end[kind]
    return '?'


def device_payload(device, device_types, roles, site, custom_field_names=()):
    """devices.yaml の1件を NetBox の Device へ書ける形にする。

    serial・asset_tag・comments・custom_fields は宣言があるときだけ入れる。
    書いていない項目を空にして、画面で入れた値を消さないため。
    """
    payload = {
        'name': device['name'],
        'device_type': device_types[device['device_type']]['id'],
        'role': roles[device['role']]['id'],
        'site': site['id'],
        'status': device.get('status', 'active'),
        'description': device.get('description', ''),
    }
    for field in ('serial', 'asset_tag'):
        if field in device:
            payload[field] = device[field]
    if 'comments' in device:
        # YAML の `|` は末尾に改行を入れるが、NetBox は落として保存する。
        # そのまま送ると毎回「差分あり」になるので、ここで揃える。
        payload['comments'] = device['comments'].strip()
    custom = custom_field_values(device, custom_field_names)
    if custom:
        payload['custom_fields'] = custom
    return payload


def device_updates(existing, desired):
    """既存 Device と宣言の差を PATCH できる形で返す。"""
    updates = {}
    for field in ('device_type', 'role', 'site'):
        if reference_id(existing.get(field)) != desired[field]:
            updates[field] = desired[field]
    if choice_value(existing.get('status')) != desired['status']:
        updates['status'] = desired['status']
    if (existing.get('description') or '') != desired['description']:
        updates['description'] = desired['description']
    for field in ('serial', 'asset_tag', 'comments'):
        if field in desired and (existing.get(field) or '') != (desired[field] or ''):
            updates[field] = desired[field]
    existing_custom = existing.get('custom_fields') or {}
    custom_updates = {}
    for field, value in (desired.get('custom_fields') or {}).items():
        if (existing_custom.get(field) or '') != (value or ''):
            custom_updates[field] = value
    if custom_updates:
        updates['custom_fields'] = custom_updates
    return updates


def device_type_updates(existing, desired):
    """既存 DeviceType と宣言の差を PATCH できる形で返す。"""
    updates = {}
    if reference_id(existing.get('manufacturer')) != desired['manufacturer']:
        updates['manufacturer'] = desired['manufacturer']
    for field in ('model', 'part_number', 'comments'):
        if field in desired and (existing.get(field) or '') != desired[field]:
            updates[field] = desired[field]
    return updates


def cable_updates(existing, desired):
    """既存 Cable と宣言の差を PATCH できる形で返す。"""
    updates = {}
    for field in ('a_terminations', 'b_terminations'):
        current = [end.get('object_id') for end in existing.get(field) or []]
        wanted = [end['object_id'] for end in desired[field]]
        if current != wanted:
            updates[field] = desired[field]
    if choice_value(existing.get('status')) != desired['status']:
        updates['status'] = desired['status']
    if (existing.get('description') or '') != desired['description']:
        updates['description'] = desired['description']
    if 'type' in desired and choice_value(existing.get('type')) != desired['type']:
        updates['type'] = desired['type']
    if 'length' in desired:
        current = existing.get('length')
        if current is None or float(current) != float(desired['length']) or \
                choice_value(existing.get('length_unit')) != desired['length_unit']:
            updates['length'] = desired['length']
            updates['length_unit'] = desired['length_unit']
    return updates


def ensure_custom_fields(api, spec, dry_run=False):
    """devices.yaml の custom_fields（Device 用）を NetBox に用意する。

    器を作るだけ。既にある物は触らない（型を変えると既存データに影響する）。
    """
    actions = []
    for field in spec.get('custom_fields', []):
        if api.one('/extras/custom-fields/', name=field['name']):
            continue
        if dry_run:
            actions.append(f"create custom_field {field['name']}")
            continue
        api.post('/extras/custom-fields/', {
            'name': field['name'],
            'label': field.get('label', field['name']),
            'type': field['type'],
            'object_types': field.get('object_types', ['dcim.device']),
        })
        actions.append(f"create custom_field {field['name']}")
    return actions


def ensure_cables(api, spec, dry_run=False):
    """devices.yaml の cables を NetBox の接続図（Cables）へ合わせる。

    両端は devices で宣言した口（interface / power_port / power_outlet）。
    `label`（既定は端点から作る）で突き合わせる。
    """
    actions = []
    for cable in spec.get('cables', []):
        ends = []
        for end in (cable['a'], cable['b']):
            kind = next((k for k, _, _ in CABLE_ENDPOINTS if end.get(k)), None)
            if not kind:
                raise NetBoxError(
                    f"cable {end.get('device')}: interface / power_port / "
                    "power_outlet のどれかを書く")
            _, object_type, path = next(e for e in CABLE_ENDPOINTS if e[0] == kind)
            device = api.one('/dcim/devices/', name=end['device'])
            if not device:
                raise NetBoxError(
                    f"cable {end['device']}/{end[kind]}: 機器が NetBox に無い")
            port = api.one(path, device_id=device['id'], name=end[kind])
            if not port and not dry_run:
                raise NetBoxError(
                    f"cable {end['device']}/{end[kind]}: 口が NetBox に無い"
                    f"（devices の {kind}s に宣言する）")
            ends.append({'object_type': object_type,
                         'object_id': port['id'] if port else None})
        label = cable.get('label') or (
            f"{cable['a']['device']}/{endpoint_name(cable['a'])} - "
            f"{cable['b']['device']}/{endpoint_name(cable['b'])}")
        desired = {
            'a_terminations': [ends[0]],
            'b_terminations': [ends[1]],
            'status': cable.get('status', 'connected'),
            'label': label,
            'description': cable.get('description', ''),
        }
        if cable.get('type'):
            desired['type'] = cable['type']
        if cable.get('length_m'):
            desired['length'] = cable['length_m']
            desired['length_unit'] = 'm'
        existing = api.one('/dcim/cables/', label=label)
        if not existing:
            if dry_run:
                actions.append(f"create cable {label}")
            else:
                api.post('/dcim/cables/', desired)
                actions.append(f"create cable {label}")
            continue
        updates = cable_updates(existing, desired)
        if updates:
            if dry_run:
                actions.append(f"update cable {label} "
                               f"({', '.join(sorted(updates))})")
            else:
                api.patch(f"/dcim/cables/{existing['id']}/", updates)
                actions.append(f"update cable {label} "
                               f"({', '.join(sorted(updates))})")
    return actions


def ensure_devices(api, spec, dry_run=False):
    """NetBox の dcim を devices.yaml に合わせる（足りない物は作り、違えば直す）。

    ネット接続の無い機器（USB のマイコン・マイク、アンマネージドスイッチ）は
    interface と address を省いて宣言できる。その場合は dcim にだけ載る。
    """
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

    actions.extend(ensure_custom_fields(api, spec, dry_run))
    custom_field_names = [field['name'] for field in spec.get('custom_fields', [])]

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
        payload = {
            'manufacturer': manufacturers[entry['manufacturer']]['id'],
            'model': entry['model'], 'slug': entry['slug'],
        }
        if entry.get('part_number'):
            payload['part_number'] = entry['part_number']
        if entry.get('comments'):
            payload['comments'] = entry['comments'].strip()
        if not found:
            if dry_run:
                actions.append(f"create device_type {entry['slug']}")
                found = {'id': None, 'dry': True}
            else:
                found = api.post('/dcim/device-types/', payload)
                actions.append(f"create device_type {entry['slug']}")
        else:
            updates = device_type_updates(found, payload)
            if updates:
                if not dry_run:
                    api.patch(f"/dcim/device-types/{found['id']}/", updates)
                actions.append(f"update device_type {entry['slug']} "
                               f"({', '.join(sorted(updates))})")
        device_types[entry['model']] = found

    for device in spec['devices']:
        desired = device_payload(device, device_types, roles, site, custom_field_names)
        found = api.one('/dcim/devices/', name=device['name'])
        if not found:
            if dry_run:
                actions.append(f"create device {device['name']}")
                continue
            found = api.post('/dcim/devices/', desired)
            actions.append(f"create device {device['name']}")
        else:
            updates = device_updates(found, desired)
            if updates:
                if not dry_run:
                    found = api.patch(f"/dcim/devices/{found['id']}/", updates)
                actions.append(f"update device {device['name']} "
                               f"({', '.join(sorted(updates))})")

        interfaces = {}
        for spec_interface in interface_specs(device):
            interface = api.one('/dcim/interfaces/', device_id=found['id'],
                                name=spec_interface['name'])
            if not interface:
                if dry_run:
                    actions.append(
                        f"create interface {device['name']}/{spec_interface['name']}")
                    interfaces[spec_interface['name']] = None
                    continue
                interface = api.post('/dcim/interfaces/', {
                    'device': found['id'],
                    'name': spec_interface['name'],
                    'type': spec_interface['type'],
                })
                actions.append(
                    f"create interface {device['name']}/{spec_interface['name']}")
            updates = {}
            if choice_value(interface.get('type')) != spec_interface['type']:
                updates['type'] = spec_interface['type']
            mac = spec_interface.get('mac')
            if mac and normalize_mac(interface.get('mac_address') or '') != normalize_mac(mac):
                updates['mac_address'] = normalize_mac(mac)
            if updates:
                if dry_run:
                    actions.append(
                        f"update interface {device['name']}/{spec_interface['name']}")
                else:
                    api.patch(f"/dcim/interfaces/{interface['id']}/", updates)
                    actions.append(
                        f"update interface {device['name']}/{spec_interface['name']}")
            interfaces[spec_interface['name']] = interface

        for label, path, key in (
                ('power port', '/dcim/power-ports/', 'power_ports'),
                ('power outlet', '/dcim/power-outlets/', 'power_outlets')):
            for name in device.get(key, []):
                if api.one(path, device_id=found['id'], name=name):
                    continue
                if dry_run:
                    actions.append(f"create {label} {device['name']}/{name}")
                else:
                    api.post(path, {'device': found['id'], 'name': name})
                    actions.append(f"create {label} {device['name']}/{name}")

        address = device.get('address')
        if not address:
            continue
        # IP を割り当てる口。既定は最初に宣言した口（address_interface で指名できる）。
        wanted = device.get('address_interface')
        if wanted and wanted not in interfaces:
            raise NetBoxError(f"{device['name']}: address_interface {wanted} が宣言に無い")
        interface = interfaces.get(wanted) if wanted else next(iter(interfaces.values()), None)
        if interface is None and interfaces:
            continue  # dry-run で口がまだ無い。IP の差分は次回に出す。
        existing = api.one('/ipam/ip-addresses/', address=address)
        payload = {
            'address': address,
            'status': 'reserved',
            'dns_name': device.get('dns_name', device['name']),
            'description': f"{device['name']} ({device['role']})",
        }
        if interface:
            payload['assigned_object_type'] = 'dcim.interface'
            payload['assigned_object_id'] = interface['id']
        if not existing:
            if dry_run:
                actions.append(f"create ip {address} ({device['name']})")
            else:
                api.post('/ipam/ip-addresses/', payload)
                actions.append(f"create ip {address} ({device['name']})")
            continue
        updates = {}
        if choice_value(existing.get('status')) != 'reserved':
            updates['status'] = 'reserved'
        if existing.get('dns_name') != payload['dns_name']:
            updates['dns_name'] = payload['dns_name']
        if existing.get('description') != payload['description']:
            updates['description'] = payload['description']
        if interface:
            if existing.get('assigned_object_id') != interface['id']:
                updates['assigned_object_type'] = 'dcim.interface'
                updates['assigned_object_id'] = interface['id']
        elif existing.get('assigned_object_id'):
            # interface を宣言から外した場合。NetBox 側の割り当ても外す。
            updates['assigned_object_type'] = None
            updates['assigned_object_id'] = None
        if updates:
            if dry_run:
                actions.append(f"update ip {address} ({device['name']})")
            else:
                api.patch(f"/ipam/ip-addresses/{existing['id']}/", updates)
                actions.append(f"update ip {address} ({device['name']})")

    actions.extend(ensure_cables(api, spec, dry_run))
    return actions


def reserved_records(api, sections):
    """NetBox の reserved IP（機器帯と DHCP プール内）を {mac, address, name} にする。

    DHCP プール内の reserved は、静的 IP の端末を他の端末へ配らないための予約。
    """
    records = []
    for entry in api.get('/ipam/ip-addresses/', status='reserved', limit=200)['results']:
        if not any(in_range(entry['address'], section) for section in sections):
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
    records = reserved_records(api, [network['infrastructure'], network['dhcp']])
    clients = declared_clients(load_yaml(DEVICES))
    desired = render_file(records, clients)
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
    print(f'pull: {len(render_hosts(records))} 件の予約・{len(render_names(records))} 件の DNS 名・'
          f'{len(render_clients(clients))} 件のリース名を反映'
          + (f"（MAC 未登録で DHCP 予約をスキップ: {', '.join(missing)}）" if missing else ''))
    return 0


def deletes_are_trustworthy(leases, uptime):
    """リースの不在を「機器が去った」とみなしてよいか。

    再起動直後はリースDB（/tmp、tmpfs）が空か部分的で、まだ取り直して
    いない端末が「リース無し」に見える。1件も無いときと、起動がリース
    期間に満たないときは削除しない。
    """
    return bool(leases) and uptime >= LEASE_TRUST_SECONDS


def push(api, args):
    network = load_yaml(NETWORK)
    dhcp = network['dhcp']
    names = client_names(load_yaml(DEVICES))
    text, error = ssh_run(args.router, args.key,
                          f'cat {LEASES_FILE}; echo ---; cat /proc/uptime')
    if text is None:
        raise SystemExit(f'{args.router} へ SSH できない: {error}')
    leases_text, _, uptime_text = text.partition('---')
    leases = parse_leases(leases_text)
    try:
        uptime = float(uptime_text.split()[0])
    except (IndexError, ValueError):
        uptime = 0.0
    actions = []

    for lease in leases:
        if not in_range(lease['address'], dhcp):
            continue
        display_name = lease_name(lease, names)
        # NetBox は dns_name を小文字で保存する。毎回の差分にしないよう揃える。
        dns_name = display_name.lower()
        existing = api.one('/ipam/ip-addresses/', address=f"{lease['address']}/24")
        description = f"DHCP lease {lease['mac']}" + (f" ({display_name})"
                                                       if display_name else '')
        if existing:
            if existing.get('status', {}).get('value') == 'reserved':
                continue  # 固定機器。リースで上書きしない
            if existing.get('description') == description and \
                    existing.get('dns_name') == dns_name:
                continue
            actions.append(f"update {lease['address']} ({display_name or lease['mac']})")
            if not args.dry_run:
                api.patch(f"/ipam/ip-addresses/{existing['id']}/",
                          {'status': 'dhcp', 'dns_name': dns_name,
                           'description': description})
        else:
            actions.append(f"create {lease['address']} ({display_name or lease['mac']})")
            if not args.dry_run:
                api.post('/ipam/ip-addresses/', {
                    'address': f"{lease['address']}/24", 'status': 'dhcp',
                    'dns_name': dns_name, 'description': description})

    live = {lease['address'] for lease in leases}
    if not deletes_are_trustworthy(leases, uptime):
        actions.append(f'push: 削除は見送り（起動 {int(uptime)} 秒・リース {len(leases)} 件）')
    else:
        for entry in api.get('/ipam/ip-addresses/', status='dhcp', limit=200)['results']:
            if not in_range(entry['address'], dhcp):
                continue
            address = str(ipaddress.ip_interface(entry['address']).ip)
            if address in live:
                continue
            # リースが消えたアドレスは残さない。機器が別の住所へ移っただけなのに
            # 「廃止」が並ぶと、機器自体が廃止されたように見えるため。
            actions.append(f"delete {address} (lease gone)")
            if not args.dry_run:
                api.delete(f"/ipam/ip-addresses/{entry['id']}/")

    if args.dry_run:
        print('push: 差分（--dry-run のため書き込まない）')
    print('\n'.join(actions) if actions else 'push: 台帳は既に一致（変更なし）')
    return 0


def discover(api, args):
    """LAN に居る機器を ARP とリースから一覧し、未宣言の候補を出す（読むだけ）。

    静的な IP の端末は DHCP のリースを取らないので `push` では台帳に載らない。
    ここで見つけて `devices.yaml` へ宣言する。
    """
    network = load_yaml(NETWORK)
    known = declared_macs(load_yaml(DEVICES))
    text, error = ssh_run(args.router, args.key,
                          f'cat {LEASES_FILE} 2>/dev/null; echo ---; ip neigh show dev br-lan')
    if text is None:
        raise SystemExit(f'{args.router} へ SSH できない: {error}')
    leases_text, _, neigh_text = text.partition('---')
    names = {lease['mac']: lease['hostname'] for lease in parse_leases(leases_text)}
    rows = []
    for entry in parse_neigh(neigh_text):
        if not (in_range(entry['address'], network['infrastructure']) or
                in_range(entry['address'], network['dhcp'])):
            continue
        record = api.one('/ipam/ip-addresses/', address=f"{entry['address']}/24")
        status = (record or {}).get('status', {}).get('value', 'なし')
        rows.append((entry['address'], entry['mac'], names.get(entry['mac'], ''),
                     entry['mac'] in known, status))
    for address, mac, name, is_known, status in sorted(
            rows, key=lambda row: ipaddress.ip_address(row[0])):
        print(f"{address:16} {mac}  {(name or '-'):24} "
              f"{'宣言済' if is_known else '未宣言':6} NetBox: {status}")
    undeclared = [row for row in rows if not row[3] and row[4] == 'なし']
    if undeclared:
        print('\n# NetBox に無い機器（devices.yaml に足す候補。MAC は ARP、名前は DHCP で名乗った物）')
        for address, mac, name, _, _ in undeclared:
            label = name or 'unknown'
            print(f'  - name: {label}')
            print('    device_type: Client Device')
            print('    role: Client')
            print(f"    interface: {{name: eth0, type: 1000base-t, mac: '{mac}'}}")
            print(f'    address: {address}/24')
            print(f'    dns_name: {label}')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['ensure', 'pull', 'push', 'discover'])
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
    if args.command == 'discover':
        return discover(api, args)
    return push(api, args)


if __name__ == '__main__':
    sys.exit(main())
