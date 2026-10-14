"""Read the live configuration. Nothing here writes anything anywhere.

Each reader returns (data, error). A source that cannot be read leaves its part
of the page empty with the reason, instead of failing the whole page.
"""
import concurrent.futures
import json
import os
import subprocess

import requests

TIMEOUT = 15


def env(name, default=''):
    return os.environ.get(name, default)


def secret(name):
    path = os.path.join(env('NETMAP_SECRETS', '/run/secrets'), name)
    try:
        with open(path, encoding='utf-8') as handle:
            return handle.read().strip()
    except OSError:
        return ''


def flint():
    """The router's config through a key that may only run netmap-dump."""
    key = os.path.join(env('NETMAP_SECRETS', '/run/secrets'), 'flint_ssh_key')
    result = subprocess.run(
        ['ssh', '-i', key, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
         '-o', 'StrictHostKeyChecking=yes', '-o', f'UserKnownHostsFile={key}.known_hosts',
         f'root@{env("FLINT_HOST", "192.168.10.1")}'],
        capture_output=True, text=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-300:] or f'ssh exited {result.returncode}')
    return result.stdout


def pve():
    base = env('PVE_URL', 'https://192.168.10.10:8006').rstrip('/') + '/api2/json'
    node = env('PVE_NODE', 'apextox')
    session = requests.Session()
    session.verify = False
    session.headers['Authorization'] = f'PVEAPIToken={env("PVE_TOKEN_ID")}={secret("pve_token")}'

    def get(path):
        response = session.get(base + path, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()['data']

    bridges = [{'host': 'apextox', 'name': i['iface'], 'vlan_aware': bool(int(i.get('bridge_vlan_aware') or 0)),
                'ports': i.get('bridge_ports', '')}
               for i in get(f'/nodes/{node}/network') if i.get('type') == 'bridge']
    vms = []
    for vm in sorted(get(f'/nodes/{node}/qemu'), key=lambda v: int(v['vmid'])):
        vmid = vm['vmid']
        config = get(f'/nodes/{node}/qemu/{vmid}/config')
        net = dict(part.split('=', 1) for part in config.get('net0', '').split(',') if '=' in part)
        options = get(f'/nodes/{node}/qemu/{vmid}/firewall/options')
        rules = get(f'/nodes/{node}/qemu/{vmid}/firewall/rules')
        vms.append({
            'vmid': vmid, 'name': vm.get('name', str(vmid)), 'running': vm.get('status') == 'running',
            'bridge': net.get('bridge', ''), 'tag': net.get('tag', ''),
            'firewall': net.get('firewall') == '1' and bool(options.get('enable')),
            'policy_in': options.get('policy_in', 'DROP'), 'policy_out': options.get('policy_out', 'ACCEPT'),
            'rules': [{
                'type': r.get('type'), 'action': r.get('action'), 'proto': r.get('proto', ''),
                'dport': r.get('dport', ''), 'source': r.get('source', ''), 'dest': r.get('dest', ''),
                'comment': r.get('comment', ''), 'enable': bool(r.get('enable')),
            } for r in rules],
        })
    host_rules = get(f'/nodes/{node}/firewall/rules')
    cluster = get('/cluster/firewall/options')
    return {'bridges': bridges, 'vms': vms, 'host_rules': host_rules, 'cluster': cluster}


def netbox():
    base = env('NETBOX_URL').rstrip('/') + '/api'
    token = secret('netbox_token')
    scheme = 'Bearer' if token.startswith('nbt_') else 'Token'
    session = requests.Session()
    session.headers.update({'Authorization': f'{scheme} {token}', 'Accept': 'application/json'})

    def get(path):
        response = session.get(base + path, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()['results']

    cables = []
    for cable in get('/dcim/cables/?limit=1000'):
        if cable.get('type') == 'power' or not cable['a_terminations'] or not cable['b_terminations']:
            continue
        ends = []
        for side in (cable['a_terminations'][0], cable['b_terminations'][0]):
            obj = side['object']
            ends.append({'device': (obj.get('device') or {}).get('name', ''), 'interface': obj.get('name', '')})
        if ends[0]['device'] and ends[1]['device']:
            cables.append({'a': ends[0], 'b': ends[1], 'label': cable.get('label') or cable.get('description', '')})
    hosts = []
    for address in get('/ipam/ip-addresses/?limit=1000&family=4'):
        obj = address.get('assigned_object') or {}
        owner = (obj.get('virtual_machine') or obj.get('device') or {}).get('name')
        if owner:
            hosts.append({'address': address['address'].split('/')[0],
                          'name': address.get('dns_name') or owner,
                          'kind': 'vm' if obj.get('virtual_machine') else 'device'})
    return {'cables': cables, 'hosts': hosts}


def tailscale():
    session = requests.Session()
    session.headers['Authorization'] = f'Bearer {secret("tailscale_token")}'
    base = 'https://api.tailscale.com/api/v2'

    def get(path, **headers):
        response = session.get(base + path, timeout=TIMEOUT, headers=headers)
        response.raise_for_status()
        return response.json()

    devices = get('/tailnet/-/devices?fields=all')['devices']
    policy = get('/tailnet/-/acl', Accept='application/json')
    return {
        'devices': [{
            'name': d.get('hostname', ''), 'address': (d.get('addresses') or [''])[0],
            'tags': d.get('tags') or [], 'user': '' if d.get('tags') else d.get('user', ''),
            'os': d.get('os', ''), 'routes': d.get('enabledRoutes') or [],
            'last_seen': d.get('lastSeen', ''),
        } for d in devices],
        'acls': policy.get('acls', []),
        'grants': policy.get('grants', []),
        'auto_routes': (policy.get('autoApprovers') or {}).get('routes', {}),
    }


READERS = {'flint': flint, 'pve': pve, 'netbox': netbox, 'tailscale': tailscale}


def read_all():
    results, errors = {}, {}
    with concurrent.futures.ThreadPoolExecutor(len(READERS)) as pool:
        futures = {name: pool.submit(reader) for name, reader in READERS.items()}
        for name, future in futures.items():
            try:
                results[name] = future.result(timeout=TIMEOUT + 5)
            except Exception as error:  # noqa: BLE001 — one broken source must not hide the others
                errors[name] = f'{type(error).__name__}: {error}'[:300]
    return results, errors


def dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=2)
