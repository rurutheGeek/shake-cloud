import json
from pathlib import Path
import re
import unittest

from jinja2 import Environment, FileSystemLoader
import yaml

ROOT = Path(__file__).resolve().parents[1]
DNS = yaml.safe_load((ROOT / 'platform/terraform/dns.yaml').read_text())
TLS_PROXY = ROOT / 'platform/ansible/roles/tls_proxy'
# services-01 is created by 05-seed, not declared in hosts.yaml.
SEED_HOST = 'services-01'
# The cloud VM's inventory host name is its instance id; the display name
# (tags.Name) arrives as cloud_name and is what dns.yaml records by.
CLOUD_INSTANCE_ID = 'i-a06df9a2dfd1ce6db'
CLOUD_NAME = 'media-01'


def defaults(role):
    return yaml.safe_load((ROOT / f'platform/ansible/roles/{role}/defaults/main.yml').read_text())


def caddyfile(sites):
    # Ansible's templar enables trim_blocks; keep the same rendering here.
    environment = Environment(
        loader=FileSystemLoader(str(TLS_PROXY / 'templates')), trim_blocks=True)
    return environment.get_template('Caddyfile.j2').render(
        tls_proxy_sites=sites,
        tls_proxy_dns=DNS,
        tls_proxy_authentik_url=defaults('tls_proxy')['tls_proxy_authentik_url'],
    )


def site_block(rendered, name):
    marker = f'{name}.{DNS["zone"]} {{'
    start = rendered.index(marker)
    next_header = re.search(r'^[^\s{}][^\s{}]* \{$', rendered[start + len(marker):], re.M)
    end = len(rendered) if next_header is None else start + len(marker) + next_header.start()
    return rendered[start:end]


class DnsDeclarationTests(unittest.TestCase):
    def test_every_record_has_exactly_one_address_source(self):
        hosts = set(yaml.safe_load((ROOT / 'platform/terraform/hosts.yaml').read_text())['hosts']) | {SEED_HOST}
        for name, record in DNS['records'].items():
            self.assertTrue('host' in record or 'address' in record, name)
            if 'address' not in record:
                # Only a record without a literal address may point at the
                # ledger; a cloud VM that is not in the ledger carries both
                # host (the name the proxy serves) and a literal address.
                self.assertIn(record['host'], hosts, name)

    def test_upstreams_stay_on_loopback(self):
        # The service ports are closed to the LAN; only Caddy on the same host
        # may reach them, so the only way in is HTTPS.
        # CUPS is the exception: its 631 is the print relay that LAN and VPN
        # clients dial directly, and CUPS rejects a non-localhost Host on
        # loopback connections, so Caddy dials the LAN address and keeps Host.
        # AdGuard の UI はルータ上にあり、ルータのファイアウォールが :3000 を
        # services-01（Caddy のホスト）だけに開けている。router（LuCI）も同じく
        # ルータ上で、80 はルータ自身の管理画面。
        for name, record in DNS['records'].items():
            if 'upstream' in record and name not in ('cups', 'adguard', 'router'):
                self.assertRegex(record['upstream'], r'^127\.0\.0\.1:\d+$', name)
        self.assertEqual(DNS['records']['cups']['upstream'], '192.168.10.200:631')
        self.assertEqual(DNS['records']['adguard']['upstream'], '192.168.10.1:3000')
        self.assertEqual(DNS['records']['router']['upstream'], '192.168.10.1:80')

    def test_upstream_ports_match_the_services(self):
        records = DNS['records']
        identity_ports = yaml.safe_load((ROOT / 'stacks/identity/compose.yaml').read_text())['services']['server']['ports']
        self.assertTrue(any(port.endswith(':9000:9000') for port in identity_ports))
        self.assertEqual(records['auth']['upstream'], '127.0.0.1:9000')
        self.assertEqual(records['cloud']['upstream'], f"127.0.0.1:{defaults('cloud_api')['cloud_api_port']}")
        self.assertEqual(records['netbox']['upstream'], f"127.0.0.1:{defaults('netbox')['netbox_port']}")
        self.assertEqual(records['docs']['upstream'], f"127.0.0.1:{defaults('docs_site')['docs_site_port']}")
        self.assertEqual(records['vault']['upstream'], f"127.0.0.1:{defaults('vaultwarden')['vaultwarden_port']}")
        self.assertEqual(records['speed']['upstream'], f"127.0.0.1:{defaults('librespeed')['librespeed_port']}")
        self.assertEqual(records['mail-view']['upstream'], f"127.0.0.1:{defaults('mail_view')['mail_view_port']}")
        self.assertEqual(records['khinsider']['upstream'], '127.0.0.1:5820')
        self.assertEqual(records['nextcloud-mcp']['upstream'], '127.0.0.1:5811')
        # CUPS は 631 の IPP と同居するWeb UI。印刷クライアントは 631 を直接使う。
        self.assertEqual(records['cups']['upstream'], '192.168.10.200:631')
        # AdGuard の UI はルータ上。ルータ側のファイアウォールで services-01 だけに開ける。
        self.assertEqual(records['adguard']['upstream'], '192.168.10.1:3000')
        # ルータの LuCI もルータ上。認証は LuCI 自身（SSO を付けない）。
        self.assertEqual(records['router']['upstream'], '192.168.10.1:80')

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
        playbooks = {'identity': ['identity.yml'], 'cloud-01': ['cloud.yml'],
                     SEED_HOST: ['netbox.yml', 'docs-site.yml', 'vaultwarden.yml', 'cups.yml',
                                 'librespeed.yml', 'mail-view.yml'],
                     CLOUD_NAME: ['media-tls.yml'],
                     'monitor-01': ['monitoring.yml']}
        served = {record['host'] for record in DNS['records'].values() if 'upstream' in record}
        self.assertEqual(served, set(playbooks))
        for host, files in playbooks.items():
            for name in files:
                roles = yaml.safe_load((ROOT / 'platform/ansible' / name).read_text())[0]['roles']
                names = [role.get('role') if isinstance(role, dict) else role for role in roles]
                self.assertIn('tls_proxy', names, name)

    def test_forward_auth_is_declared_for_the_browser_tools_only(self):
        records = DNS['records']
        behind_auth = {name for name, record in records.items() if record.get('auth')}
        self.assertEqual(behind_auth,
                         {'navidrome', 'metube', 'khinsider', 'cups', 'adguard', 'mail-view'})
        # ルータは復旧経路。identity が止まっていても開けるよう SSO を付けない。
        self.assertNotIn('auth', records['router'])
        for name in ('nextcloud', 'kavita', 'nextcloud-mcp'):
            self.assertNotIn('auth', records[name], name)

    def test_blocked_paths_are_answered_before_forward_auth(self):
        # Caddy 経由だと CUPS から見た接続元は 127.0.0.1 になる。管理画面を
        # localhost 限定のまま保つため、入口の respond で閉じる。
        cups = [{'key': 'cups', 'value': DNS['records']['cups']}]
        block = site_block(caddyfile(cups), 'cups')
        # route が内側を書いた順に評価させる（forward_auth が先に走るのを防ぐ）。
        self.assertIn('route {', block)
        self.assertIn('@blocked path /admin /admin/*', block)
        self.assertIn('respond @blocked 403', block)
        self.assertLess(block.index('respond @blocked 403'), block.index('forward_auth https://'))

        media = [{'key': 'navidrome', 'value': DNS['records']['navidrome']}]
        self.assertNotIn('@blocked', site_block(caddyfile(media), 'navidrome'))

    def test_the_caddyfile_learns_the_forward_auth_endpoint(self):
        template = (TLS_PROXY / 'templates/Caddyfile.j2').read_text()
        self.assertIn('forward_auth {{ tls_proxy_authentik_url }}', template)
        self.assertEqual(defaults('tls_proxy')['tls_proxy_authentik_url'],
                         'https://auth.apextox.dpdns.org')
        # The Authentik outpost picks the application by the request Host, so
        # Caddy must pass the original name through to the auth upstream.
        self.assertIn('header_up Host {http.request.host}', template)

    def test_only_identity_gets_the_forward_auth_catchall(self):
        # The Authentik outpost picks the application by the request Host, and
        # Caddy answers unmatched hosts with an empty 200. identity therefore
        # needs a catch-all that forwards the original Host to Authentik.
        template = (TLS_PROXY / 'templates/Caddyfile.j2').read_text()
        self.assertIn('tls_proxy_catchall_upstream', template)
        identity = yaml.safe_load((ROOT / 'platform/ansible/identity.yml').read_text())
        roles = identity[0]['roles']
        tls = next(role for role in roles
                   if (role.get('role') if isinstance(role, dict) else role) == 'tls_proxy')
        self.assertEqual(tls['tls_proxy_catchall_upstream'], '127.0.0.1:9000')

    def test_the_rendered_caddyfile_guards_only_the_auth_sites(self):
        names = [CLOUD_INSTANCE_ID, CLOUD_NAME]
        sites = [{'key': name, 'value': record} for name, record in DNS['records'].items()
                 if record.get('host') in names and 'upstream' in record]
        rendered = caddyfile(sites)

        self.assertEqual(len(sites), 8)
        # navidrome は通常の認証に加え、/review/ の静的ページにも forward_auth を付ける。
        self.assertEqual(rendered.count('forward_auth https://'), 4)
        for name in ('navidrome', 'metube', 'khinsider'):
            block = site_block(rendered, name)
            self.assertIn('forward_auth', block, name)
            self.assertIn('request_header -Remote-User', block, name)
            self.assertIn('request_header -X-Authentik-Username', block, name)
            self.assertIn('copy_headers X-Authentik-Username', block, name)
            self.assertIn('header_up Remote-User sso_{http.request.header.X-Authentik-Username}', block, name)
            self.assertIn('header_up -X-Authentik-Username', block, name)
        navidrome = site_block(rendered, 'navidrome')
        self.assertIn('handle_path /review/*', navidrome)
        self.assertIn('root * /data/review', navidrome)
        self.assertIn('file_server', navidrome)
        for name in ('nextcloud', 'kavita', 'freshrss', 'nextcloud-mcp'):
            self.assertNotIn('forward_auth', site_block(rendered, name), name)
            self.assertNotIn('request_header', site_block(rendered, name), name)

    def test_the_rendered_caddyfile_keeps_the_plain_sites_unchanged(self):
        sites = [{'key': 'cloud', 'value': DNS['records']['cloud']}]
        rendered = caddyfile(sites)
        self.assertIn('\treverse_proxy 127.0.0.1:8080\n', rendered)
        self.assertNotIn('forward_auth', rendered)

    def test_the_cloud_api_trusts_only_local_proxies(self):
        environment = yaml.safe_load((ROOT / 'cloud/compose.yaml').read_text())['services']['api']['environment']
        for prefix in environment['SHAKECLOUD_TRUSTED_PROXIES'].split(','):
            self.assertRegex(prefix, r'^(127\.0\.0\.1/32|172\.16\.0\.0/12)$')


if __name__ == '__main__':
    unittest.main()
