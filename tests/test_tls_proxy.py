import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from jinja2 import Environment, FileSystemLoader
import yaml

ROOT = Path(__file__).resolve().parents[1]
DNS = yaml.safe_load((ROOT / 'platform/terraform/dns.yaml').read_text())
TLS_PROXY = ROOT / 'platform/ansible/roles/tls_proxy'
# core-01 is created by 05-seed, not declared in hosts.yaml.
SEED_HOST = 'core-01'
# The cloud VM's inventory host name is its instance id; the display name
# (tags.Name) arrives as cloud_name and is what dns.yaml records by.
CLOUD_INSTANCE_ID = 'i-a06df9a2dfd1ce6db'
CLOUD_NAME = 'media-01'


def defaults(role):
    return yaml.safe_load((ROOT / f'platform/ansible/roles/{role}/defaults/main.yml').read_text())


def caddyfile(sites, **extra):
    # Ansible's templar enables trim_blocks; keep the same rendering here.
    environment = Environment(
        loader=FileSystemLoader(str(TLS_PROXY / 'templates')), trim_blocks=True)
    variables = dict(
        tls_proxy_sites=sites,
        tls_proxy_dns=DNS,
        tls_proxy_authentik_url=defaults('tls_proxy')['tls_proxy_authentik_url'],
    )
    variables.update(extra)
    return environment.get_template('Caddyfile.j2').render(**variables)


def sites_of(host):
    return [{'key': name, 'value': record} for name, record in DNS['records'].items()
            if record.get('host') == host and 'upstream' in record]


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
        # core-01（Caddy のホスト）だけに開けている。router（LuCI）も同じく
        # ルータ上で、80 はルータ自身の管理画面。
        for name, record in DNS['records'].items():
            if 'upstream' in record and name not in ('cups', 'adguard', 'router'):
                self.assertRegex(record['upstream'], r'^127\.0\.0\.1:\d+$', name)
            for route in record.get('path_routes', []):
                self.assertRegex(route['upstream'], r'^127\.0\.0\.1:\d+$',
                                 f'{name}{route["path"]}')
        self.assertEqual(DNS['records']['cups']['upstream'], '192.168.10.105:631')
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
        self.assertEqual(records['poke']['upstream'], f"127.0.0.1:{defaults('poke_translate')['poke_translate_port']}")
        self.assertEqual(records['khinsider']['upstream'], '127.0.0.1:5820')
        self.assertEqual(records['nextcloud-mcp']['upstream'], '127.0.0.1:5811')
        # 全曲レビューは navidrome の /review/ から music-tools の review へ中継する。
        music_tools = yaml.safe_load((ROOT / 'platform/ansible/music-tools.yml').read_text())[0]
        review_port = music_tools['vars']['music_tools_review_port']
        self.assertEqual(records['navidrome']['path_routes'][0]['path'], '/review')
        self.assertEqual(records['navidrome']['path_routes'][0]['upstream'],
                         f'127.0.0.1:{review_port}')
        # CUPS は 631 の IPP と同居するWeb UI。印刷クライアントは 631 を直接使う。
        self.assertEqual(records['cups']['upstream'], '192.168.10.105:631')
        # AdGuard の UI はルータ上。ルータ側のファイアウォールで core-01 だけに開ける。
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
        playbooks = {'cloud-01': ['cloud.yml'],
                     # Authentik lives next to NetBox on the core host.
                     SEED_HOST: ['netbox.yml', 'identity.yml'],
                     'apps-01': ['librespeed.yml', 'docs-site.yml', 'mail-view.yml', 'homarr.yml',
                                 'vaultwarden.yml', 'cups.yml', 'poke-translate.yml'],
                     CLOUD_NAME: ['media-tls.yml'],
                     'monitor-02': ['monitoring.yml']}
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
                         {'navidrome', 'metube', 'khinsider', 'cups', 'adguard',
                          'mail-view', 'backup', 'urbackup'})
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

        self.assertEqual(len(sites), 10)
        # navidrome は通常の認証に加え、/review/ の全曲レビューと
        # /review-static/ の生成HTMLにも forward_auth を付ける。
        self.assertEqual(rendered.count('forward_auth https://'), 7)
        for name in ('navidrome', 'metube', 'khinsider', 'backup', 'urbackup'):
            block = site_block(rendered, name)
            self.assertIn('forward_auth', block, name)
            self.assertIn('request_header -Remote-User', block, name)
            self.assertIn('request_header -X-Authentik-Username', block, name)
            self.assertIn('copy_headers X-Authentik-Username', block, name)
            self.assertIn('header_up Remote-User sso_{http.request.header.X-Authentik-Username}', block, name)
            self.assertIn('header_up -X-Authentik-Username', block, name)
        navidrome = site_block(rendered, 'navidrome')
        self.assertIn('@review_exact path /review', navidrome)
        self.assertIn('redir @review_exact /review/ 308', navidrome)
        self.assertIn('handle /review/*', navidrome)
        self.assertIn('reverse_proxy 127.0.0.1:5830', navidrome)
        # 前置きの除去は認証の後ろ。先に消すと SSO の戻り先が / になる。
        self.assertIn('uri strip_prefix /review', navidrome)
        self.assertIn('handle /review-static/*', navidrome)
        self.assertIn('uri strip_prefix /review-static', navidrome)
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


EDGE_ADDRESS = '192.168.10.200'
IDENTITY_ADDRESS = '192.168.10.204'
MEDIA_ADDRESS = '192.168.10.101'


class EdgeDeclarationTests(unittest.TestCase):
    """One host holds the public certificates and the Cloudflare token."""

    def test_the_edge_is_a_host_that_already_serves_names(self):
        edge = DNS['edge']
        served = {record['host'] for record in DNS['records'].values() if 'upstream' in record}
        self.assertEqual(edge['host'], SEED_HOST)
        self.assertIn(edge['host'], served)
        # A backend is a host with names of its own, and never the edge itself.
        for backend in edge['backends']:
            self.assertIn(backend, served - {edge['host']}, backend)
        self.assertEqual(len(edge['backends']), len(set(edge['backends'])))

    def test_the_edge_has_its_own_playbook_on_the_dynamic_inventory(self):
        play = yaml.safe_load((ROOT / 'platform/ansible/edge.yml').read_text())[0]
        self.assertEqual(play['hosts'], 'core')
        self.assertIn('tls_proxy', play['roles'])

    def test_dns_points_relayed_names_at_the_edge(self):
        main = (ROOT / 'platform/terraform/20-dns/main.tf').read_text()
        # Only names Caddy serves move; a record without an upstream (the
        # LocalSend receiver, Proxmox) keeps its own address.
        self.assertIn('can(record.upstream) && contains(local.edge.backends, try(record.host, ""))', main)
        self.assertIn('local.via_edge[name] ? local.known_hosts[local.edge.host]', main)

    def test_the_token_is_mounted_only_where_certificates_are_requested(self):
        base = yaml.safe_load((ROOT / 'stacks/tls-proxy/compose.yaml').read_text())
        overlay = yaml.safe_load((ROOT / 'stacks/tls-proxy/compose.token.yaml').read_text())
        self.assertNotIn('secrets', base)
        self.assertNotIn('secrets', base['services']['caddy'])
        self.assertEqual(overlay['services']['caddy']['secrets'], ['cloudflare_dns_api_token'])
        tasks = yaml.safe_load((TLS_PROXY / 'tasks/main.yml').read_text())
        by_name = {task['name']: task for task in tasks}
        environment = by_name['Write the storage location and the compose files in use']['ansible.builtin.copy']['content']
        self.assertIn("COMPOSE_FILE=compose.yaml{{ '' if tls_proxy_behind_edge else ':compose.token.yaml' }}", environment)
        for name in ('Read the Cloudflare DNS token', 'Install the Cloudflare DNS token'):
            self.assertEqual(by_name[name]['when'], 'not tls_proxy_behind_edge', name)
        removal = by_name['Remove the Cloudflare DNS token from a host behind the edge']
        self.assertEqual(removal['ansible.builtin.file']['state'], 'absent')
        self.assertEqual(removal['when'], 'tls_proxy_behind_edge')


class EdgeRenderingTests(unittest.TestCase):
    def test_without_backends_nothing_about_the_edge_is_rendered(self):
        # Until a host is moved, every host keeps requesting its own
        # certificates exactly as before.
        for host in ('cloud-01', CLOUD_NAME, 'monitor-02', SEED_HOST):
            rendered = caddyfile(sites_of(host))
            self.assertIn('dns cloudflare {file./run/secrets/cloudflare_dns_api_token}', rendered, host)
            for marker in ('tls internal', 'trusted_proxies', 'tls_trust_pool', 'X-Forwarded-For', '@outpost'):
                self.assertNotIn(marker, rendered, f'{host}: {marker}')

    def test_a_host_behind_the_edge_holds_no_token_and_keeps_its_own_auth(self):
        rendered = caddyfile(sites_of(CLOUD_NAME), tls_proxy_behind_edge=True,
                             tls_proxy_edge_address=EDGE_ADDRESS)
        self.assertNotIn('cloudflare', rendered)
        self.assertIn('(dns_challenge) {\n\ttls internal\n}', rendered)
        self.assertIn(f'trusted_proxies static {EDGE_ADDRESS}/32', rendered)
        self.assertIn('skip_install_trust', rendered)
        # Forward Auth and the header hygiene stay on the host that runs the app.
        navidrome = site_block(rendered, 'navidrome')
        self.assertIn('request_header -Remote-User', navidrome)
        # As many Forward Auth calls as the host makes when it is not behind the edge.
        self.assertEqual(rendered.count('forward_auth https://auth.apextox.dpdns.org'),
                         caddyfile(sites_of(CLOUD_NAME)).count('forward_auth https://'))
        self.assertGreater(rendered.count('forward_auth https://'), 0)
        # Every hop to an app passes the real client, not the edge.
        self.assertEqual(rendered.count('reverse_proxy 127.0.0.1:'),
                         rendered.count('header_up X-Forwarded-For {client_ip}'))

    def test_the_edge_relays_over_tls_and_checks_the_backends_own_ca(self):
        relayed = [{'key': name, 'value': record, 'address': MEDIA_ADDRESS}
                   for name, record in DNS['records'].items()
                   if record.get('host') == CLOUD_NAME and 'upstream' in record]
        rendered = caddyfile(sites_of(SEED_HOST), tls_proxy_passthrough_sites=relayed)
        self.assertIn('dns cloudflare', rendered)
        for site in relayed:
            block = site_block(rendered, site['key'])
            name = f"{site['key']}.{DNS['zone']}"
            self.assertIn('import dns_challenge', block, name)
            self.assertIn(f'reverse_proxy https://{MEDIA_ADDRESS} {{', block, name)
            # Caddy rewrites Host for an https upstream; the backend picks the
            # site by Host, so the original must be passed explicitly.
            self.assertIn('header_up Host {host}', block, name)
            self.assertIn(f'tls_server_name {name}', block, name)
            self.assertIn(f'tls_trust_pool file /etc/caddy/backend-ca/{CLOUD_NAME}.crt', block, name)
            # The edge only relays: authentication is the backend's job.
            self.assertNotIn('forward_auth', block, name)
            self.assertNotIn('127.0.0.1', block, name)
        # The edge's own sites are untouched.
        self.assertIn('reverse_proxy 127.0.0.1:', site_block(rendered, 'netbox'))
        self.assertNotIn('@outpost', rendered)

    def test_forward_auth_does_not_loop_once_identity_is_behind_the_edge(self):
        identity = {'host': 'identity', 'address': IDENTITY_ADDRESS, 'name': f"auth.{DNS['zone']}"}
        relayed = [{'key': name, 'value': record,
                    'address': IDENTITY_ADDRESS if record['host'] == 'identity' else MEDIA_ADDRESS}
                   for name, record in DNS['records'].items()
                   if record.get('host') in (CLOUD_NAME, 'identity') and 'upstream' in record]
        rendered = caddyfile(sites_of(SEED_HOST), tls_proxy_passthrough_sites=relayed,
                             tls_proxy_auth_backend=identity,
                             tls_proxy_authentik_url=f'https://{IDENTITY_ADDRESS}')
        # A backend asks auth.<zone>, which is now the edge, with the app's
        # Host. The edge must hand that to identity, not back to the app.
        navidrome = site_block(rendered, 'navidrome')
        self.assertIn('@outpost path /outpost.goauthentik.io/*', navidrome)
        outpost = navidrome[navidrome.index('handle @outpost'):navidrome.index('handle {')]
        self.assertIn(f'reverse_proxy https://{IDENTITY_ADDRESS}', outpost)
        self.assertIn('header_up Host {host}', outpost)
        self.assertIn('tls_trust_pool file /etc/caddy/backend-ca/identity.crt', outpost)
        # Sites without Forward Auth need no such route.
        self.assertNotIn('@outpost', site_block(rendered, 'nextcloud'))
        # The edge's own Forward Auth sites go to identity directly as well.
        adguard = site_block(rendered, 'adguard')
        self.assertIn(f'forward_auth https://{IDENTITY_ADDRESS} {{', adguard)
        self.assertIn(f"tls_server_name auth.{DNS['zone']}", adguard)
        self.assertNotIn('forward_auth https://auth.', rendered)


class EdgeRoleTests(unittest.TestCase):
    """Run the role's own decision tasks through Ansible, against no host."""

    @unittest.skipUnless(shutil.which('ansible-playbook') or (Path(sys.executable).parent / 'ansible-playbook').exists(),
                         'ansible-playbook is not installed')
    def test_the_role_works_out_each_hosts_place(self):
        ansible = shutil.which('ansible-playbook') or str(Path(sys.executable).parent / 'ansible-playbook')
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / 'ca').mkdir()
            (work / 'out').mkdir()
            dns = json.loads(json.dumps(DNS))
            dns['edge']['backends'] = ['monitor-02', CLOUD_NAME]
            for backend in dns['edge']['backends']:
                (work / 'ca' / f'{backend}.crt').write_text('test\n')
            (work / 'vars.json').write_text(json.dumps({
                'tls_proxy_dns': dns, 'tls_proxy_backend_ca_dir': str(work / 'ca'), 'out': str(work / 'out')}))
            (work / 'inventory.ini').write_text(
                f'{SEED_HOST} ansible_host={EDGE_ADDRESS}\n'
                'cloud-01 ansible_host=192.168.10.205\n'
                f'{CLOUD_INSTANCE_ID} ansible_host={MEDIA_ADDRESS} cloud_name={CLOUD_NAME}\n'
                'i-2193bd70bacdd1602 ansible_host=192.168.10.102 cloud_name=monitor-02\n')
            (work / 'play.yml').write_text(
                '- hosts: all\n'
                '  gather_facts: false\n'
                '  connection: local\n'
                '  tasks:\n'
                '    - ansible.builtin.include_role:\n'
                '        name: tls_proxy\n'
                '        tasks_from: facts\n'
                '        public: true\n'
                '    - ansible.builtin.template:\n'
                f"        src: {TLS_PROXY / 'templates/Caddyfile.j2'}\n"
                "        dest: '{{ out }}/{{ tls_proxy_ledger_name }}.Caddyfile'\n"
                "        mode: '0644'\n")
            result = subprocess.run(
                [ansible, '-i', str(work / 'inventory.ini'), '-e', f"@{work / 'vars.json'}", str(work / 'play.yml')],
                cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr[-2000:])
            rendered = {path.stem: path.read_text() for path in (work / 'out').iterdir()}

        self.assertEqual(set(rendered), {SEED_HOST, 'cloud-01', CLOUD_NAME, 'monitor-02'})
        # Only the edge and the host that has not been moved hold the token.
        holders = {host for host, text in rendered.items() if 'dns cloudflare' in text}
        self.assertEqual(holders, {SEED_HOST, 'cloud-01'})
        for host in (CLOUD_NAME, 'monitor-02'):
            self.assertIn(f'trusted_proxies static {EDGE_ADDRESS}/32', rendered[host], host)
        edge = rendered[SEED_HOST]
        relayed = [name for name, record in DNS['records'].items()
                   if record.get('host') in dns['edge']['backends'] and 'upstream' in record]
        self.assertEqual(edge.count('へ中継）'), len(relayed))
        # The cloud VM is found by its display name, and relayed to its address.
        self.assertIn(f'reverse_proxy https://{MEDIA_ADDRESS} {{', site_block(edge, 'nextcloud'))
        # Authentik is on the edge host itself, so auth is one of its own sites.
        self.assertIn('reverse_proxy 127.0.0.1:9000', site_block(edge, 'auth'))
        self.assertNotIn('cloud.', ''.join(line for line in edge.splitlines() if 'へ中継）' in line))


if __name__ == '__main__':
    unittest.main()
