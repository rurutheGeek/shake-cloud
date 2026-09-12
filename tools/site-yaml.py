#!/usr/bin/env python3
"""Write platform/terraform/site.yaml from what the host actually reports.

The machine-specific values Terraform needs -- node name, storage IDs, bridge
-- exist only on the Proxmox host. Copying them by hand invites two failures:
a typo that surfaces as a confusing ACL error, and a guess that looks right
and is not. This reads the survey's own output and writes the file, or refuses
and names the candidates when the answer is genuinely ambiguous.

Two sources work. The API needs only a read-only token and no SSH, so it is
the one to reach for; the survey's output is there for a host the API cannot
be reached on.

    python3 tools/site-yaml.py --api            # reads PROXMOX_VE_* from the env
    python3 tools/site-yaml.py .survey/<host>.facts.json

site.yaml holds no secrets -- storage and bridge names are not credentials --
so unlike the rest of .survey/ it is committed.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'platform/terraform/site.yaml'

# Chosen by this repository rather than discovered: 00-bootstrap creates them.
CLOUD_IMAGES_STORE = 'cloud-images'
CLOUD_IMAGES_PATH = '/srv/cloud-images'

TEMPLATE = '''---
# 実機の事実。**このファイルが正本**で、Terraform の全モジュールが読む。
#
# **手で書かない。** tools/site-yaml.py が実機の読み取り結果から生成する。
#
#   ansible-playbook -i platform/ansible/pve.ini platform/ansible/survey-pve.yml
#   python3 tools/site-yaml.py .survey/<ホスト名>.facts.json
#
# 秘密値は含まない。ノード名・ストレージ名・bridge名・ゾーン名はいずれも
# 資格情報ではなく、資格情報は今まで通り SOPS 経由の環境変数で渡す。
#
# 整合は tests/test_platform_inventory.py が検査する。
node_name: {node_name}

storage:
  # 既存のストレージ。Proxmox のインストーラが作るのでコード管理しない。
  vm_disks: {vm_disks}
  # 管理者が cloud image を置く先。00-bootstrap の images.tf が使う。
  admin_images: {admin_images}
  # クラウドAPI専用。00-bootstrap が作る（proxmox_storage_directory）。
  # 利用者のイメージとインスタンスごとの seed ISO が入る。
  # 発見ではなくこのリポジトリが決めた名前。
  cloud_images: {cloud_images}
  cloud_images_path: {cloud_images_path}

network:
  bridge: {bridge}
  # この bridge が VLAN タグを通すか（実測）。VLAN 切替の前提で、
  # 10-platform が「vlan_id を設定したのに bridge が未対応」を plan で止める。
  bridge_vlan_aware: {bridge_vlan_aware}
  # 素の Linux bridge が入る既定ゾーン。SDN を使っていなければ localnetwork。
  sdn_zone: {sdn_zone}
  # ゲストが載るネットワーク。ホストの bridge のアドレスから導出した。
  prefix: {prefix}
  gateway: {gateway}
  dns_servers:
{dns_servers}
'''


class Ambiguous(Exception):
    """Raised when the host offers more than one plausible answer."""


def pick(candidates, what, hint):
    """Return the single candidate, or explain why the host cannot decide."""
    if not candidates:
        raise Ambiguous(f'no candidate for {what}. {hint}')
    if len(candidates) > 1:
        raise Ambiguous(f'{len(candidates)} candidates for {what}: '
                        f"{', '.join(sorted(candidates))}. {hint}")
    return candidates[0]


def node_name(nodes, override=None):
    if override:
        return override
    return pick([entry['node'] for entry in nodes],
                'node_name', 'Pass --node to choose one.')


def content_types(entry):
    raw = entry.get('content', '')
    return {part.strip() for part in raw.split(',') if part.strip()}


def storages(storage, wanted, what, hint, exclude=()):
    found = [entry['storage'] for entry in storage
             if wanted <= content_types(entry) and entry['storage'] not in exclude]
    return pick(found, what, hint)


def usable_bridges(bridges):
    """Keep only bridges that carry traffic off the host.

    A bridge with no port is internal: a VM attached to it cannot reach the
    LAN or be reached from it, so it is never the answer here.
    """
    return [bridge['name'] for bridge in bridges if bridge.get('ports')]


def bridges_from_interfaces(interfaces):
    """Parse /etc/network/interfaces into the same shape the API returns."""
    found = []
    entry = None
    for line in interfaces.splitlines() + ['iface END']:
        match = re.match(r'^iface\s+(\S+)', line)
        if match:
            if entry:
                found.append(entry)
            entry = ({'name': match.group(1), 'ports': None, 'vlan_aware': False,
                      'cidr': None, 'gateway': None}
                     if match.group(1).startswith('vmbr') else None)
            continue
        if not entry:
            continue
        for key, pattern in (('ports', r'^\s+bridge-ports\s+(\S.*)'),
                             ('cidr', r'^\s+address\s+(\S+)'),
                             ('gateway', r'^\s+gateway\s+(\S+)')):
            found_value = re.match(pattern, line)
            if found_value:
                entry[key] = found_value.group(1).strip()
        if re.match(r'^\s+bridge-vlan-aware\s+yes', line):
            entry['vlan_aware'] = True
    return found


def bridges_from_api(network):
    """Pick the bridges out of GET /nodes/<node>/network."""
    return [{'name': entry['iface'],
             'ports': entry.get('bridge_ports'),
             'vlan_aware': str(entry.get('bridge_vlan_aware', '0')) == '1',
             'cidr': entry.get('cidr'),
             'gateway': entry.get('gateway')}
            for entry in network if entry.get('type') == 'bridge']


def vlan_aware(bridges, name):
    """Whether the chosen bridge already passes VLAN tags through.

    Not written into site.yaml because nothing reads it yet; the VLAN phase
    will. Reported on stdout so the answer is on record before then.
    """
    for bridge in bridges:
        if bridge['name'] == name:
            return bool(bridge.get('vlan_aware'))
    return False


def prefix_of(bridges, name):
    """The network the guests sit on, from the bridge's own address.

    Proxmox reports the host's address (192.0.2.10/24); guests need the
    network (192.0.2.0/24), so the host part is masked off.
    """
    for bridge in bridges:
        if bridge['name'] == name and bridge.get('cidr'):
            return str(ipaddress.ip_interface(bridge['cidr']).network)
    raise Ambiguous(f'bridge {name} reports no address. Set network.prefix by hand.')


def gateway_of(bridges, name):
    for bridge in bridges:
        if bridge['name'] == name and bridge.get('gateway'):
            return bridge['gateway']
    raise Ambiguous(f'bridge {name} reports no gateway. Set network.gateway by hand.')


def sdn_zone(zones):
    """The zone that SDN.Use must be granted on.

    A plain Linux bridge is not in an SDN zone at all; Proxmox treats it as
    the implicit `localnetwork` zone for permission checks. So an empty zone
    list is the normal answer here, not a missing one.
    """
    names = [zone['zone'] for zone in zones]
    return names[0] if len(names) == 1 else 'localnetwork'


def build(nodes, storage, bridges, zones, node=None, dns=None):
    """Decide every value site.yaml holds, or raise Ambiguous naming the tie."""
    bridge = pick(usable_bridges(bridges), 'network.bridge',
                  'Edit site.yaml by hand and record why.')
    resolvers = [dns[key] for key in ('dns1', 'dns2', 'dns3')
                 if (dns or {}).get(key)] or [gateway_of(bridges, bridge)]
    return {
        'prefix': prefix_of(bridges, bridge),
        'gateway': gateway_of(bridges, bridge),
        'dns_servers': '\n'.join(f'    - {server}' for server in resolvers),
        'node_name': node_name(nodes, node),
        'vm_disks': storages(
            storage, {'images'}, 'storage.vm_disks',
            'Pick the one that should hold user VM disks and set it by hand.'),
        'admin_images': storages(
            storage, {'import'}, 'storage.admin_images',
            'This is where 00-bootstrap downloads official cloud images.',
            exclude=(CLOUD_IMAGES_STORE,)),
        'cloud_images': CLOUD_IMAGES_STORE,
        'cloud_images_path': CLOUD_IMAGES_PATH,
        'bridge': bridge,
        'bridge_vlan_aware': str(vlan_aware(bridges, bridge)).lower(),
        'sdn_zone': sdn_zone(zones),
    }


def from_survey(facts, node=None):
    return build(json.loads(facts['nodes_json']),
                 json.loads(facts['storage_json']),
                 bridges_from_interfaces(facts['interfaces_file']),
                 json.loads(facts.get('sdn_zones') or '[]'), node)


def from_api(data, node=None):
    return build(data['nodes'], data['storage'],
                 bridges_from_api(data['network']), data['sdn_zones'], node,
                 dns=data.get('dns'))


def read_api():
    """Fetch what site.yaml needs straight from the Proxmox API.

    A read-only token is enough, so this needs no SSH access to the host and
    no key on the machine running it.
    """
    import ssl
    import urllib.request

    endpoint = os.environ.get('PROXMOX_VE_ENDPOINT')
    token = os.environ.get('PROXMOX_VE_API_TOKEN')
    if not (endpoint and token):
        raise SystemExit('Set PROXMOX_VE_ENDPOINT and PROXMOX_VE_API_TOKEN')
    base = endpoint.rstrip('/') + '/api2/json'
    context = None
    if os.environ.get('PROXMOX_VE_INSECURE', '').lower() in ('1', 'true', 'yes'):
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    def get(path):
        request = urllib.request.Request(
            base + path, headers={'Authorization': f'PVEAPIToken={token}'})
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            return json.load(response)['data']

    nodes = get('/nodes')
    node = nodes[0]['node']
    return {'nodes': nodes, 'storage': get('/storage'),
            'network': get(f'/nodes/{node}/network'),
            'sdn_zones': get('/cluster/sdn/zones'),
            'dns': get(f'/nodes/{node}/dns')}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('facts', nargs='?',
                        help='.survey/<host>.facts.json from survey-pve.yml')
    parser.add_argument('--api', action='store_true',
                        help='read from the Proxmox API instead (needs PROXMOX_VE_*)')
    parser.add_argument('--node', help='node name, when the cluster has more than one')
    parser.add_argument('--print', action='store_true', help='write to stdout instead')
    args = parser.parse_args()

    if not (args.api or args.facts):
        raise SystemExit('Pass --api, or the path to a .facts.json file')
    try:
        if args.api:
            data = read_api()
            values = from_api(data, args.node)
            bridges = bridges_from_api(data['network'])
        else:
            facts = json.loads(Path(args.facts).read_text(encoding='utf-8'))
            values = from_survey(facts, args.node)
            bridges = bridges_from_interfaces(facts['interfaces_file'])
        content = TEMPLATE.format(**values)
    except Ambiguous as error:
        raise SystemExit(f'Cannot decide from the host: {error}')

    # Nothing reads this yet, but the VLAN phase needs it and the answer is
    # cheap to record now.
    print(f"note: bridge {values['bridge']} vlan_aware="
          f"{str(vlan_aware(bridges, values['bridge'])).lower()}")

    if args.print:
        print(content, end='')
        return 0
    if TARGET.exists() and TARGET.read_text(encoding='utf-8') == content:
        print('OK: site.yaml already matches the host')
        return 0
    TARGET.write_text(content, encoding='utf-8')
    print(f'CHANGED: wrote {TARGET.relative_to(ROOT)}')
    print(yaml.safe_dump(yaml.safe_load(content), allow_unicode=True, sort_keys=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
