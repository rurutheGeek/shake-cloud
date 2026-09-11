import json
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
DNS = yaml.safe_load((ROOT / 'platform/terraform/dns.yaml').read_text())
# services-01 is created by 05-seed, not declared in hosts.yaml.
SEED_HOST = 'services-01'


def defaults(role):
    return yaml.safe_load((ROOT / f'platform/ansible/roles/{role}/defaults/main.yml').read_text())


class DnsDeclarationTests(unittest.TestCase):
    def test_every_record_has_exactly_one_address_source(self):
        hosts = set(yaml.safe_load((ROOT / 'platform/terraform/hosts.yaml').read_text())['hosts']) | {SEED_HOST}
        for name, record in DNS['records'].items():
            self.assertEqual(('host' in record) + ('address' in record), 1, name)
            if 'host' in record:
                self.assertIn(record['host'], hosts, name)

    def test_upstreams_stay_on_loopback(self):
        # The service ports are closed to the LAN; only Caddy on the same host
        # may reach them, so the only way in is HTTPS.
        for name, record in DNS['records'].items():
            if 'upstream' in record:
                self.assertRegex(record['upstream'], r'^127\.0\.0\.1:\d+$', name)

    def test_upstream_ports_match_the_services(self):
        records = DNS['records']
        identity_ports = yaml.safe_load((ROOT / 'stacks/identity/compose.yaml').read_text())['services']['server']['ports']
        self.assertTrue(any(port.endswith(':9000:9000') for port in identity_ports))
        self.assertEqual(records['auth']['upstream'], '127.0.0.1:9000')
        self.assertEqual(records['cloud']['upstream'], f"127.0.0.1:{defaults('cloud_api')['cloud_api_port']}")
        self.assertEqual(records['netbox']['upstream'], f"127.0.0.1:{defaults('netbox')['netbox_port']}")
        self.assertEqual(records['docs']['upstream'], f"127.0.0.1:{defaults('docs_site')['docs_site_port']}")

    def test_comments_fit_cloudflare_free_plan(self):
        # Cloudflare's free plan rejects record comments over 100 characters.
        for name, record in DNS['records'].items():
            self.assertLessEqual(len(f"{record['description']} / platform/terraform/20-dns"), 100, name)


class TlsProxyTests(unittest.TestCase):
    def test_base_images_are_pinned(self):
        lines = [line for line in (ROOT / 'stacks/tls-proxy/Dockerfile').read_text().splitlines() if line.startswith('FROM ')]
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertIn('@sha256:', line)
        self.assertRegex((ROOT / 'stacks/tls-proxy/Dockerfile').read_text(), r'caddy-dns/cloudflare@v\d+\.\d+\.\d+')

    def test_the_dns_token_never_reaches_the_ansible_log(self):
        tasks = yaml.safe_load((ROOT / 'platform/ansible/roles/tls_proxy/tasks/main.yml').read_text())
        touching = [task for task in tasks if 'tls_proxy_token' in json.dumps(task)]
        self.assertEqual(len(touching), 2)
        for task in touching:
            self.assertTrue(task.get('no_log'), task['name'])

    def test_services_behind_the_proxy_do_not_listen_on_the_lan(self):
        self.assertEqual(defaults('identity')['identity_bind_address'], '127.0.0.1')
        self.assertEqual(defaults('cloud_api')['cloud_api_bind_address'], '127.0.0.1')

    def test_every_host_with_upstreams_deploys_the_proxy(self):
        playbooks = {'identity': ['identity.yml'], 'cloud-01': ['cloud.yml'], SEED_HOST: ['netbox.yml', 'docs-site.yml']}
        served = {record['host'] for record in DNS['records'].values() if 'upstream' in record}
        self.assertEqual(served, set(playbooks))
        for host, files in playbooks.items():
            for name in files:
                roles = yaml.safe_load((ROOT / 'platform/ansible' / name).read_text())[0]['roles']
                self.assertIn('tls_proxy', roles, name)

    def test_the_cloud_api_trusts_only_local_proxies(self):
        environment = yaml.safe_load((ROOT / 'cloud/compose.yaml').read_text())['services']['api']['environment']
        for prefix in environment['SHAKECLOUD_TRUSTED_PROXIES'].split(','):
            self.assertRegex(prefix, r'^(127\.0\.0\.1/32|172\.16\.0\.0/12)$')


if __name__ == '__main__':
    unittest.main()
