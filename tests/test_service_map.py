"""The service map page is generated from dns.yaml; keep it current and linked."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs/assets/js/service-map-data.js'
SOURCE = ROOT / 'stacks/docs/service-map.yaml'


def load():
    text = DATA.read_text(encoding='utf-8')
    return json.loads(text[text.index('{'):].rstrip().rstrip(';'))


class ServiceMapTests(unittest.TestCase):
    def test_the_generated_data_is_current(self):
        result = subprocess.run([sys.executable, 'tools/render-service-map.py', '--check'],
                                cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_name_in_dns_is_on_the_map_with_its_url(self):
        dns = yaml.safe_load((ROOT / 'platform/terraform/dns.yaml').read_text(encoding='utf-8'))
        urls = {service.get('url') for vm in load()['vms'] for service in vm['services']}
        for name in dns['records']:
            if '*' in name:
                continue
            port = ':8006' if name == 'pve' else ''
            self.assertIn(f'https://{name}.{dns["zone"]}{port}/', urls)

    def test_every_linked_runbook_exists(self):
        source = yaml.safe_load(SOURCE.read_text(encoding='utf-8'))
        paths = [path for vm in source['vms'] for path in vm.get('docs', [])]
        paths += [path for vm in source['vms'] for service in vm.get('services', [])
                  for path in service.get('docs', [])]
        paths += [path for docs in source['record_docs'].values() for path in docs]
        for path in paths:
            self.assertTrue((ROOT / 'docs' / path).is_file(), path)

    def test_a_relayed_service_shows_its_route_through_the_edge(self):
        data = load()
        services = {service['name']: service for vm in data['vms'] for service in vm['services']}
        self.assertEqual(services['Kavita']['route'], [data['edge'], 'media-01'])
        self.assertEqual(services['Authentik']['route'], [data['edge']])
        self.assertEqual(services['AdGuard Home']['route'], [data['edge'], 'router-01'])

    def test_the_page_is_in_the_navigation_and_loads_its_scripts(self):
        mkdocs = (ROOT / 'mkdocs.yml').read_text(encoding='utf-8')
        for fragment in ('service-map.md', 'assets/js/service-map-data.js',
                         'assets/js/service-map.js', 'assets/css/service-map.css'):
            self.assertIn(fragment, mkdocs)
        self.assertIn('id="service-map"', (ROOT / 'docs/service-map.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
