#!/usr/bin/env python3
"""Render the data behind docs/service-map.md.

URLs, upstreams and the edge come from platform/terraform/dns.yaml; the VM list
and the links to the runbooks come from stacks/docs/service-map.yaml. The
result is a JavaScript file, so the page needs no fetch and works from file://.

    python3 tools/render-service-map.py          # write
    python3 tools/render-service-map.py --check  # fail if the file is stale
"""
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
DNS = ROOT / 'platform/terraform/dns.yaml'
SOURCE = ROOT / 'stacks/docs/service-map.yaml'
OUTPUT = ROOT / 'docs/assets/js/service-map-data.js'


def doc_links(paths):
    links = []
    for path in paths or []:
        text = (ROOT / 'docs' / path).read_text(encoding='utf-8')
        title = next((line[2:].strip() for line in text.splitlines() if line.startswith('# ')), path)
        # use_directory_urls: operations/edge.md is served at operations/edge/.
        url = path[:-len('index.md')] if path.endswith('index.md') else path[:-len('.md')] + '/'
        links.append({'title': title, 'path': url})
    return links


def render():
    dns = yaml.safe_load(DNS.read_text(encoding='utf-8'))
    source = yaml.safe_load(SOURCE.read_text(encoding='utf-8'))
    edge = dns['edge']
    vms = {}
    for vm in source['vms']:
        vms[vm['name']] = {
            'name': vm['name'], 'kind': vm['kind'], 'role': vm['role'], 'address': vm['address'],
            'docs': doc_links(vm.get('docs')),
            'services': [{'name': service['name'], 'description': service['description'],
                          'docs': doc_links(service.get('docs'))}
                         for service in vm.get('services', [])],
        }
    for name, record in dns['records'].items():
        host = source['record_vm_overrides'].get(name) or record.get('host') or source['record_vms'].get(name)
        if host not in vms:
            raise SystemExit(f'service-map: {name} is on {host!r}, which stacks/docs/service-map.yaml does not list')
        label, _, note = record['description'].partition('（')
        service = {
            'name': label, 'description': note.rstrip('）') if note else '',
            'docs': doc_links(source['record_docs'].get(name)),
        }
        if '*' not in name:
            port = ':8006' if name == 'pve' else ''
            service['url'] = f'https://{name}.{dns["zone"]}{port}/'
        if record.get('upstream'):
            service['upstream'] = record['upstream']
            service['sso'] = bool(record.get('auth'))
            relay = record.get('host')
            service['route'] = [edge['host']] + ([relay] if relay != edge['host'] else [])
            if host != relay:
                service['route'].append(host)
        vms[host]['services'].append(service)
    data = {'edge': edge['host'], 'vms': list(vms.values())}
    body = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True)
    return ('// tools/render-service-map.py が platform/terraform/dns.yaml と\n'
            '// stacks/docs/service-map.yaml から書く。直接直さない。\n'
            f'window.SERVICE_MAP = {body};\n')


def main():
    text = render()
    if '--check' in sys.argv[1:]:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding='utf-8') != text:
            raise SystemExit('service-map: docs/assets/js/service-map-data.js is stale; '
                             'run python3 tools/render-service-map.py')
        return
    OUTPUT.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    main()
