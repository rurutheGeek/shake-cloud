#!/usr/bin/env python3
"""Render docs/network-map.md from the address plan and the NetBox ledger.

Segments come from platform/terraform/network.yaml; machines and their addresses
come from NetBox, which the cloud API and
tools/netbox-dhcp-sync.py keep current. Run it after the ledger changes:

    sops exec-env platform/sops/netbox.sops.yaml \
      'python3 tools/render-network-map.py'

The page is a Mermaid diagram, so nothing is drawn by hand.
"""
import datetime
import ipaddress
import os
from pathlib import Path
import re
import sys

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
NETWORK = ROOT / 'platform/terraform/network.yaml'
OUTPUT = ROOT / 'docs/network-map.md'

LABELS = {
    'server': 'サーバー',
    'management': '管理（予約）',
    'dmz': 'DMZ',
    'personal': '個人端末',
    'iot': 'ネット専用',
}
ROUTER = 'flint3'


def node_id(name):
    return 'n_' + re.sub(r'[^0-9A-Za-z]', '_', name)


def segment_of(address, segments):
    ip = ipaddress.ip_interface(address).ip
    for name, segment in segments.items():
        if ip in ipaddress.ip_network(segment['prefix']):
            return name
    return None


def machines(addresses):
    """(name, address, kind, label) for every addressed device and VM."""
    seen = {}
    for entry in addresses:
        obj = entry.get('assigned_object') or {}
        if entry.get('assigned_object_type') == 'virtualization.vminterface':
            name, kind = (obj.get('virtual_machine') or {}).get('name'), 'vm'
        elif entry.get('assigned_object_type') == 'dcim.interface':
            name, kind = (obj.get('device') or {}).get('name'), 'device'
        else:
            name, kind = entry.get('dns_name') or entry['address'], 'other'
        if not name or name in seen:
            continue
        # クラウドVMの台帳名はインスタンスID。DNS 名（Name タグ）で見せる。
        label = entry.get('dns_name') or name
        seen[name] = (name, entry['address'], kind, label)
    return sorted(seen.values(), key=lambda m: ipaddress.ip_interface(m[1]).ip)


def render(segments, addressed, status):
    lines = ['```mermaid', 'flowchart TB']
    lines.append('  internet(["インターネット"])')
    lines.append(f'  {node_id(ROUTER)}{{{{"Flint 3<br>192.168.10.1"}}}}')
    lines.append(f'  internet --- {node_id(ROUTER)}')
    for name, segment in segments.items():
        label = LABELS.get(name, name)
        title = f'{label} VLAN {segment["vlan_id"]}<br>{segment["prefix"]}'
        lines.append(f'  subgraph seg_{name}["{title}"]')
        members = [m for m in addressed if segment_of(m[1], {name: segment}) and m[0] != ROUTER]
        if not members:
            lines.append(f'    empty_{name}["（まだ無い）"]')
        for host, address, kind, shown in members:
            ip = str(ipaddress.ip_interface(address).ip)
            stopped = status.get(host) not in (None, 'active')
            text = f'{shown}<br>{ip}' + ('<br>停止中' if stopped else '')
            shape = f'("{text}")' if kind == 'vm' else f'["{text}"]'
            lines.append(f'    {node_id(host)}{shape}')
        lines.append('  end')
        if not segment.get('reserved'):
            lines.append(f'  {node_id(ROUTER)} --- seg_{name}')
    for name in segments:
        if segments[name].get('reserved') or name == 'dmz':
            lines.append(f'  style seg_{name} stroke-dasharray: 5 5')
    lines.append('```')
    return '\n'.join(lines)


def page(diagram):
    today = datetime.date.today().isoformat()
    return f'''---
title: ネットワーク図
updated: {today}
section: 入口
audience: 全員
tags:
  - hub
  - network
---

# ネットワーク図

> **更新日** {today} ・ **区分** 入口 ・ **読む人** 全員

<!-- tools/render-network-map.py が network.yaml と NetBox から作る。手で編集しない。 -->

{diagram}

| 形 | 意味 |
| --- | --- |
| 四角 | 物理の機器 |
| 角丸 | VM |
| 点線の枠 | 未作成・予約 |

区画間の通信は [VLAN 分離](operations/vlan.md)、Flint 3 の設定は [Flint 3](operations/flint3.md)。
'''


def fetch(session, url, path):
    items, next_url = [], f'{url}{path}'
    while next_url:
        data = session.get(next_url, timeout=30).json()
        items += data['results']
        next_url = data.get('next')
    return items


def main():
    url = os.environ.get('NETBOX_SERVER_URL', '').rstrip('/')
    token = os.environ.get('NETBOX_API_TOKEN', '')
    if not url or not token:
        raise SystemExit('NETBOX_SERVER_URL と NETBOX_API_TOKEN を渡してください（sops exec-env）')
    session = requests.Session()
    session.headers['Authorization'] = f'Token {token}'
    session.headers['Accept'] = 'application/json'

    segments = yaml.safe_load(NETWORK.read_text(encoding='utf-8'))['segments']
    addressed = machines(fetch(session, url, '/api/ipam/ip-addresses/?limit=500'))
    status = {item['name']: item['status']['value']
              for path in ('/api/virtualization/virtual-machines/?limit=500', '/api/dcim/devices/?limit=500')
              for item in fetch(session, url, path)}

    OUTPUT.write_text(page(render(segments, addressed, status)), encoding='utf-8')
    print(f'wrote {OUTPUT.relative_to(ROOT)}: {len(addressed)} machines')
    return 0


if __name__ == '__main__':
    sys.exit(main())
