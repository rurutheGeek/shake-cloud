"""Turn what the sources returned into the pictures and tables of the page.

Everything here is pure: it takes parsed data and returns plain dicts, so the
tests can feed it a small router config without any network.
"""
import ipaddress

from . import uci

ZONE_LABELS = {
    'lan': 'サーバー',
    'personal': '個人端末',
    'iot': 'ネット専用',
    'dmz': 'DMZ',
    'wan': 'インターネット',
    'tailscale': 'Tailscale',
    'guest': 'ゲスト',
}
# Flint 3（GL-BE9300）の内蔵スイッチ（switch1）のポート番号と前面の表記。
PORT_LABELS = {'7': 'LAN1', '6': 'LAN2', '5': 'LAN3', '4': 'LAN4'}
CPU_PORT = '3'
CPU_DEVICE = 'eth1'
ROUTER = 'Flint 3'


def split_dump(text):
    parts, name = {}, None
    for line in text.splitlines():
        if line.startswith('### '):
            name = line[4:].strip()
            parts[name] = []
        elif name:
            parts[name].append(line)
    return {key: '\n'.join(lines) for key, lines in parts.items()}


def label(zone):
    return ZONE_LABELS.get(zone, zone)


def subnet_of(interface):
    address, mask = interface.get('ipaddr'), interface.get('netmask', '255.255.255.0')
    if not address or interface.get('proto') != 'static':
        return None
    try:
        return str(ipaddress.ip_interface(f'{address}/{mask}').network)
    except ValueError:
        return None


def live(interface):
    return interface is not None and interface.get('disabled') != '1'


def router(dump):
    """The Flint 3 config: segments, switch ports, SSIDs and firewall."""
    parts = split_dump(dump)
    configs = uci.parse(parts.get('uci', ''))
    network = configs.get('network', {})
    firewall = configs.get('firewall', {})
    wireless = configs.get('wireless', {})
    dhcp = configs.get('dhcp', {})
    interfaces = {name: section for name, section in network.items() if section.get('.type') == 'interface'}

    links = {}
    for line in parts.get('links', '').splitlines():
        fields = line.split(None, 1)
        if len(fields) == 2:
            links[fields[0]] = fields[1]

    zones = []
    for zone in uci.of_type(firewall, 'zone'):
        name = zone.get('name')
        networks = [n for n in uci.as_list(zone.get('network')) if live(interfaces.get(n))]
        if not networks and name != 'tailscale':
            continue
        zones.append({
            'name': name,
            'label': label(name),
            'networks': networks,
            'subnets': [s for s in (subnet_of(interfaces[n]) for n in networks) if s],
            'input': zone.get('input', 'ACCEPT'),
            'forward': zone.get('forward', 'ACCEPT'),
            'output': zone.get('output', 'ACCEPT'),
            'ssids': [],
            'ports': [],
            'dhcp': None,
        })
    by_network = {n: z for z in zones for n in z['networks']}
    by_name = {z['name']: z for z in zones}

    for iface in uci.of_type(wireless, 'wifi-iface'):
        zone = by_network.get(iface.get('network'))
        if zone is None or iface.get('disabled') == '1' or iface.get('mode', 'ap') != 'ap':
            continue
        band = {'wifi0': '2.4GHz', 'wifi1': '5GHz', 'wifi2': '6GHz'}.get(iface.get('device'), iface.get('device', ''))
        if iface['.name'].startswith('wlanmld'):
            band = f'MLO {band}'
        ssid = next((s for s in zone['ssids'] if s['ssid'] == iface.get('ssid')), None)
        if ssid is None:
            ssid = {'ssid': iface.get('ssid', ''), 'bands': [], 'isolate': iface.get('isolate') == '1'}
            zone['ssids'].append(ssid)
        ssid['bands'].append(band)

    bridges = {d.get('name'): uci.as_list(d.get('ports')) for d in uci.of_type(network, 'device')}
    vlans = []
    for vlan in uci.of_type(network, 'switch_vlan'):
        tag = vlan.get('vlan')
        device = f'{CPU_DEVICE}.{tag}'
        holders = [name for name, ports in bridges.items() if device in ports] + [device]
        net = next((n for n, i in interfaces.items() if i.get('device') in holders and live(i)), None)
        zone = by_network.get(net)
        ports = []
        for port in uci.as_list(vlan.get('ports')):
            number, tagged = port.rstrip('t'), port.endswith('t')
            if number == CPU_PORT:
                continue
            ports.append({'port': PORT_LABELS.get(number, number), 'tagged': tagged,
                          'link': links.get(number, '')})
            if zone is not None:
                zone['ports'].append(f'{PORT_LABELS.get(number, number)}{"（タグ付き）" if tagged else ""}')
        vlans.append({'vlan': tag, 'network': net, 'zone': zone['label'] if zone else '—', 'ports': ports})

    for pool in uci.of_type(dhcp, 'dhcp'):
        zone = by_network.get(pool.get('interface'))
        iface = interfaces.get(pool.get('interface'))
        if zone is None or pool.get('ignore') == '1' or not iface or not iface.get('ipaddr'):
            continue
        base = iface['ipaddr'].rsplit('.', 1)[0]
        start = int(pool.get('start', '100'))
        limit = int(pool.get('limit', '150'))
        zone['dhcp'] = f'{base}.{start}〜{base}.{start + limit - 1}'

    forwardings = [{'src': f.get('src'), 'dest': f.get('dest')}
                   for f in uci.of_type(firewall, 'forwarding') if f.get('enabled') != '0']
    rules = []
    for rule in uci.of_type(firewall, 'rule'):
        if rule.get('enabled') == '0':
            continue
        rules.append({
            'name': rule.get('name', rule['.name']),
            'src': rule.get('src') or '',
            'dest': rule.get('dest') or '',
            'proto': ' '.join(uci.as_list(rule.get('proto'))) or 'all',
            'dest_port': ' '.join(uci.as_list(rule.get('dest_port'))),
            'src_ip': ' '.join(uci.as_list(rule.get('src_ip'))),
            'dest_ip': ' '.join(uci.as_list(rule.get('dest_ip'))),
            'src_mac': ' '.join(uci.as_list(rule.get('src_mac'))),
            'family': rule.get('family', ''),
            'target': rule.get('target', 'DROP'),
        })
    redirects = [{
        'name': r.get('name', r['.name']), 'src': r.get('src', ''),
        'proto': ' '.join(uci.as_list(r.get('proto'))), 'src_dport': r.get('src_dport', ''),
        'dest_ip': r.get('dest_ip', ''), 'dest_port': r.get('dest_port', ''),
    } for r in uci.of_type(firewall, 'redirect') if r.get('enabled') != '0']

    leases = []
    for line in parts.get('leases', '').splitlines():
        fields = line.split()
        if len(fields) >= 4:
            leases.append({'mac': fields[1], 'address': fields[2], 'name': '' if fields[3] == '*' else fields[3]})

    return {
        'zones': zones, 'by_name': by_name, 'vlans': vlans, 'forwardings': forwardings,
        'rules': rules, 'redirects': redirects, 'leases': leases, 'wan_link': links.get('eth0', ''),
    }


def describe_rule(rule):
    parts = []
    if rule['src_ip']:
        parts.append(f'送信元 {rule["src_ip"]}')
    if rule['src_mac']:
        parts.append(f'MAC {rule["src_mac"]}')
    if rule['dest_ip']:
        parts.append(f'宛先 {rule["dest_ip"]}')
    if rule['proto'] != 'all' or rule['dest_port']:
        port = f':{rule["dest_port"]}' if rule['dest_port'] else ''
        parts.append(f'{rule["proto"]}{port}')
    return '、'.join(parts) or 'すべて'


def matrix(state):
    """Zone × zone: what the router lets through, plus the router itself."""
    zones = state['zones']
    names = [z['name'] for z in zones]
    allowed = {(f['src'], f['dest']) for f in state['forwardings']}
    rows = []
    for src in zones:
        cells = []
        for dest_name in names + ['__router__']:
            if dest_name == src['name']:
                cells.append({'kind': 'self', 'text': '—', 'rules': []})
                continue
            if dest_name == '__router__':
                matching = [r for r in state['rules'] if r['src'] == src['name'] and not r['dest']]
                accept = src['input'] == 'ACCEPT'
            else:
                matching = [r for r in state['rules'] if r['src'] == src['name'] and r['dest'] in (dest_name, '*')]
                accept = (src['name'], dest_name) in allowed
            accepts = [r for r in matching if r['target'] == 'ACCEPT']
            denies = [r for r in matching if r['target'] != 'ACCEPT']
            if accept:
                kind, text = 'allow', 'すべて許可'
                if denies:
                    kind, text = 'partial', 'ほぼ許可'
            elif accepts:
                kind, text = 'partial', '一部だけ'
            else:
                kind, text = 'deny', '拒否'
            cells.append({'kind': kind, 'text': text,
                          'rules': [{'name': r['name'], 'target': r['target'], 'what': describe_rule(r)}
                                    for r in matching]})
        rows.append({'zone': src, 'cells': cells})
    return {'columns': [label(n) for n in names] + [ROUTER + ' 自身'], 'rows': rows}


def mermaid_id(text):
    return 'n_' + ''.join(c if c.isalnum() else '_' for c in text)


def segment_diagram(state):
    """Zones as boxes and what passes between them as arrows."""
    lines = ['flowchart LR']
    for zone in state['zones']:
        detail = '<br>'.join(zone['subnets'] + [s['ssid'] for s in zone['ssids']])
        text = f'{zone["label"]}' + (f'<br><small>{detail}</small>' if detail else '')
        lines.append(f'  {mermaid_id(zone["name"])}["{text}"]')
    names = {z['name'] for z in state['zones']}
    allowed = {(f['src'], f['dest']) for f in state['forwardings']}
    for src, dest in sorted(allowed):
        if src in names and dest in names:
            lines.append(f'  {mermaid_id(src)} ==>|すべて| {mermaid_id(dest)}')
    partial = {}
    for rule in state['rules']:
        if rule['target'] == 'ACCEPT' and rule['dest'] in names and rule['src'] in names \
                and (rule['src'], rule['dest']) not in allowed:
            partial.setdefault((rule['src'], rule['dest']), []).append(rule)
    for (src, dest), matched in sorted(partial.items()):
        lines.append(f'  {mermaid_id(src)} -.->|一部 {len(matched)}件| {mermaid_id(dest)}')
    return '\n'.join(lines)


def physical_diagram(state, cables, bridges, vms):
    """ONU → Flint 3 ports → what is plugged in → K11's bridges → VMs."""
    lines = ['flowchart LR', '  onu["ONU"]', f'  flint{{{{"{ROUTER}"}}}}', '  onu ---|WAN| flint']
    port_vlans = {}
    for vlan in state['vlans']:
        for port in vlan['ports']:
            port_vlans.setdefault(port['port'], []).append(
                f'{vlan["zone"]}{"（タグ）" if port["tagged"] else ""}')
    flint_ports = {}
    for cable in cables:
        for near, far in ((cable['a'], cable['b']), (cable['b'], cable['a'])):
            if near['device'] == 'flint3' and near['interface'].upper().startswith('LAN'):
                flint_ports[near['interface'].upper()] = far
    for port in ['LAN1', 'LAN2', 'LAN3', 'LAN4']:
        far = flint_ports.get(port)
        if not far:
            continue
        vlan = '・'.join(port_vlans.get(port, [])) or '—'
        lines.append(f'  {mermaid_id(far["device"])}["{far["device"]}"]')
        lines.append(f'  flint ---|"{port}<br>{vlan}"| {mermaid_id(far["device"])}')
    for cable in cables:
        a, b = cable['a'], cable['b']
        if 'flint3' in (a['device'], b['device']) or a['device'] == 'onu-1' or b['device'] == 'onu-1':
            continue
        lines.append(f'  {mermaid_id(a["device"])}["{a["device"]}"] --- {mermaid_id(b["device"])}["{b["device"]}"]')
    for bridge in bridges:
        bid = mermaid_id('bridge_' + bridge['name'])
        aware = 'VLAN対応' if bridge['vlan_aware'] else 'VLAN非対応'
        lines.append(f'  {bid}["{bridge["name"]}<br><small>{aware}</small>"]')
        lines.append(f'  {mermaid_id(bridge["host"])} --- {bid}')
        attached = [vm for vm in vms if vm['bridge'] == bridge['name']]
        for vm in attached:
            tag = f'VLAN {vm["tag"]}' if vm['tag'] else 'タグなし'
            stopped = '' if vm['running'] else '<br><small>停止中</small>'
            lines.append(f'  {mermaid_id("vm_" + vm["name"])}("{vm["name"]}{stopped}")')
            lines.append(f'  {bid} ---|{tag}| {mermaid_id("vm_" + vm["name"])}')
    return '\n'.join(lines)
