"""Guard the media-01 SSO wiring to the identity Authentik.

configure.py declares the Nextcloud/Kavita OIDC clients and the Navidrome,
MeTube and Picard Forward Auth providers on the identity VM; configure-oidc.py
runs on media-01 and hands the client secret to occ without putting it on a
command line; media-sso.yml carries the secret from identity to media-01. These
are source-text, YAML and in-memory assertions in the same spirit as
test_media_nextcloud.py. Nothing here connects to a host or runs Docker except
the ansible-playbook syntax check, which parses the file on localhost only.
"""
import ast
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

from support import load_module, syntax_check

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = ROOT / 'stacks/identity'
NEXTCLOUD = ROOT / 'stacks/media/nextcloud'
PLAYBOOK = ROOT / 'platform/ansible/media-sso.yml'

PORTAL = 'https://cloud.apextox.dpdns.org'
ZONE = 'apextox.dpdns.org'


configure = load_module(IDENTITY / 'configure.py', 'identity_configure')
nextcloud_oidc = load_module(NEXTCLOUD / 'configure-oidc.py', 'nextcloud_configure_oidc')
FLOWS = {configure.AUTHORIZATION_FLOW: 'auth', configure.INVALIDATION_FLOW: 'inval'}


class MediaDeclarationTests(unittest.TestCase):
    def test_the_zone_is_derived_from_the_portal_url(self):
        self.assertEqual(configure.media_zone(PORTAL), ZONE)
        self.assertEqual(configure.media_zone(PORTAL + '/'), ZONE)
        with self.assertRaises(ValueError):
            configure.media_zone('/auth/callback')

    def test_native_oidc_redirects_match_each_application(self):
        self.assertEqual(configure.media_redirect('nextcloud', ZONE),
                         'https://nextcloud.apextox.dpdns.org/apps/user_oidc/code')
        self.assertEqual(configure.media_redirect('kavita', ZONE),
                         'https://kavita.apextox.dpdns.org/signin-oidc')

    def test_media_oidc_providers_keep_stable_subjects_and_strict_redirects(self):
        for name in ('nextcloud', 'kavita'):
            body = configure.oidc_provider_body(
                name, configure.media_redirect(name, ZONE), FLOWS, ['mapping'],
                'signing-key', {'client_id': name, 'client_secret': 'secret'})
            self.assertEqual(body['sub_mode'], 'user_uuid', name)
            self.assertTrue(body['include_claims_in_id_token'], name)
            self.assertEqual(body['redirect_uris'],
                             [{'matching_mode': 'strict',
                               'url': configure.media_redirect(name, ZONE),
                               'redirect_uri_type': 'authorization'}], name)

    def test_the_outpost_update_unions_providers_and_keeps_other_config(self):
        current = {'providers': ['existing'],
                   'config': {'authentik_host': 'http://auth.localhost:9000',
                              'authentik_host_browser': 'http://auth.localhost:9000',
                              'object_creation': True}}
        body = configure.outpost_body(current, ['p1', 'p2'], ZONE)
        self.assertEqual(body['providers'], ['existing', 'p1', 'p2'])
        self.assertTrue(body['config']['object_creation'])
        self.assertEqual(body['config']['authentik_host'], f'https://auth.{ZONE}')
        self.assertEqual(body['config']['authentik_host_browser'], f'https://auth.{ZONE}')


class FakeMediaAPI:
    """In-memory Authentik objects for configure_media()."""

    def __init__(self, outposts=None):
        self.objects = {
            'providers/oauth2/': [],
            'providers/proxy/': [],
            'core/applications/': [],
            'policies/bindings/': [],
            'outposts/instances/': outposts if outposts is not None else [
                {'pk': 'outpost', 'name': 'authentik Embedded Outpost',
                 'providers': ['provider-existing'],
                 'config': {'authentik_host': 'http://auth.localhost:9000',
                            'authentik_host_browser': 'http://auth.localhost:9000'}}],
        }
        self.calls = []

    def rows(self, path):
        key = self.collection(path)
        found = self.objects.get(key, [])
        if key == 'policies/bindings/' and 'target=' in path:
            target = path.split('target=', 1)[1].split('&')[0]
            return [row for row in found if row.get('target') == target]
        return found

    def collection(self, path):
        key = path.split('?')[0]
        if key in self.objects:
            return key
        parent = key.rstrip('/').rsplit('/', 1)[0] + '/'
        return parent if parent in self.objects else key

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        key = self.collection(path)
        collection = self.objects[key]
        if method == 'POST':
            prefixes = {'providers/oauth2/': 'oidc-', 'providers/proxy/': 'proxy-',
                        'core/applications/': 'app-', 'policies/bindings/': 'bind-'}
            label = body.get('name') or body.get('slug') or str(len(collection))
            row = dict(body, pk=prefixes[key] + label)
            collection.append(row)
            return row
        if method == 'PATCH':
            identifier = path.rstrip('/').split('/')[-1]
            for row in collection:
                if row.get('pk') == identifier or row.get('slug') == identifier:
                    row.update(body)
                    return row
        return {'pk': 'obj'}


class MediaCredentialTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.original = configure.ROOT
        configure.ROOT = Path(self.directory.name)
        self.addCleanup(lambda: setattr(configure, 'ROOT', self.original))

    def test_it_creates_both_clients_private_and_reuses_them(self):
        first = configure.media_credentials()
        path = Path(self.directory.name) / 'secrets' / 'oidc-media.json'
        self.assertEqual(set(first), set(configure.MEDIA_OIDC_CLIENTS))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        for name, values in first.items():
            self.assertEqual(values['client_id'], name)
            self.assertTrue(values['client_secret'])
        self.assertEqual(configure.media_credentials(), first)

    def test_an_existing_secret_is_kept_when_a_client_is_added(self):
        path = Path(self.directory.name) / 'secrets' / 'oidc-media.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(
            {'nextcloud': {'client_id': 'nextcloud', 'client_secret': 'keep'}}))
        credentials = configure.media_credentials()
        self.assertEqual(credentials['nextcloud']['client_secret'], 'keep')
        self.assertIn('kavita', credentials)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class MediaReconcileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.original = configure.ROOT
        configure.ROOT = Path(self.directory.name)
        self.addCleanup(lambda: setattr(configure, 'ROOT', self.original))

    def run_configure(self, api):
        with contextlib.redirect_stdout(io.StringIO()):
            configure.configure_media(api, {'users': {'pk': 'group-users'}}, FLOWS,
                                      ['mapping'], 'signing-key', PORTAL)

    def test_it_declares_oidc_and_forward_auth_providers_and_applications(self):
        api = FakeMediaAPI()
        self.run_configure(api)
        oidc = {body['name'] for method, path, body in api.calls
                if method == 'POST' and path == 'providers/oauth2/'}
        self.assertEqual(oidc, set(configure.MEDIA_OIDC_CLIENTS))
        proxy = {body['name']: body for method, path, body in api.calls
                 if method == 'POST' and path == 'providers/proxy/'}
        self.assertEqual(set(proxy), set(configure.MEDIA_PROXY_PROVIDERS))
        for name, body in proxy.items():
            self.assertEqual(body['mode'], 'forward_single', name)
            self.assertEqual(body['external_host'], f'https://{name}.{ZONE}', name)
        applications = {body['slug'] for method, path, body in api.calls
                        if method == 'POST' and path == 'core/applications/'}
        self.assertEqual(applications, set(configure.MEDIA_APPLICATIONS))

    def test_it_adds_the_proxy_providers_without_removing_the_existing_ones(self):
        api = FakeMediaAPI()
        self.run_configure(api)
        patches = [body for method, path, body in api.calls
                   if method == 'PATCH' and path.startswith('outposts/instances/')]
        self.assertEqual(len(patches), 1)
        self.assertIn('provider-existing', patches[0]['providers'])
        for name in configure.MEDIA_PROXY_PROVIDERS:
            self.assertIn('proxy-' + name, patches[0]['providers'])
        self.assertEqual(patches[0]['config']['authentik_host'], f'https://auth.{ZONE}')
        self.assertEqual(patches[0]['config']['authentik_host_browser'],
                         f'https://auth.{ZONE}')

    def test_it_grants_the_users_group_and_never_admins(self):
        api = FakeMediaAPI()
        self.run_configure(api)
        bindings = [body for method, path, body in api.calls
                    if path == 'policies/bindings/']
        self.assertEqual(len(bindings), len(configure.MEDIA_APPLICATIONS))
        for body in bindings:
            self.assertEqual(body['group'], 'group-users')
            self.assertEqual(body['order'], 10)

    def test_a_second_run_reports_ok_and_adds_nothing(self):
        api = FakeMediaAPI()
        self.run_configure(api)
        calls = len(api.calls)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            configure.configure_media(api, {'users': {'pk': 'group-users'}}, FLOWS,
                                      ['mapping'], 'signing-key', PORTAL)
        self.assertEqual(len(api.calls), calls)
        self.assertNotIn('CHANGED:', output.getvalue())
        self.assertIn('OK:', output.getvalue())


class NextcloudOidcScriptTests(unittest.TestCase):
    def setUp(self):
        self.text = (NEXTCLOUD / 'configure-oidc.py').read_text(encoding='utf-8')

    def test_the_secret_never_lands_on_the_command_line(self):
        self.assertIn('--clientsecret-env=', self.text)
        self.assertNotIn('--clientsecret=', self.text)
        self.assertIn("'-e', SECRET_ENV", self.text)

    def test_it_uses_the_loopback_proxy_and_appends_the_trusted_domain(self):
        self.assertIn("'trusted_proxies'", self.text)
        self.assertIn("'trusted_domains'", self.text)
        self.assertIn('127.0.0.1', self.text)
        self.assertIn("'nextcloud.'", self.text)

    def test_it_forces_https_in_generated_urls(self):
        # Caddy forwards http; without overwriteprotocol Nextcloud redirects
        # browsers to http:// and relies on Caddy to upgrade them.
        self.assertIn("'overwriteprotocol'", self.text)
        self.assertIn("--value=https", self.text)

    def test_it_uses_only_the_standard_library(self):
        modules = set()
        for node in ast.walk(ast.parse(self.text)):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add((node.module or '').split('.')[0])
        self.assertLessEqual(modules, set(sys.stdlib_module_names))
        self.assertIn('subprocess', modules)

    def test_zone_and_trusted_domain_helpers_are_idempotent(self):
        discovery = ('https://auth.apextox.dpdns.org/application/o/nextcloud/'
                     '.well-known/openid-configuration')
        self.assertEqual(nextcloud_oidc.media_zone(discovery), ZONE)
        self.assertEqual(nextcloud_oidc.media_zone(discovery, 'media.example.org'),
                         'media.example.org')
        config = {'trusted_domains': ['localhost', '127.0.0.1']}
        domain = 'nextcloud.' + ZONE
        self.assertEqual(nextcloud_oidc.next_trusted_domain_index(config, domain), 2)
        config['trusted_domains'].append(domain)
        self.assertIsNone(nextcloud_oidc.next_trusted_domain_index(config, domain))
        sparse = {'trusted_domains': {'1': domain}}
        self.assertIsNone(nextcloud_oidc.next_trusted_domain_index(sparse, domain))
        self.assertEqual(nextcloud_oidc.next_trusted_domain_index(sparse, 'other.example.org'), 2)


class MediaSsoPlaybookTests(unittest.TestCase):
    def setUp(self):
        self.text = PLAYBOOK.read_text(encoding='utf-8')
        self.play = yaml.safe_load(self.text)[0]

    def test_it_targets_the_media_group_as_root(self):
        self.assertEqual(self.play['hosts'], 'media')
        self.assertTrue(self.play['become'])

    def test_it_reads_the_credentials_from_identity_without_logging_them(self):
        tasks = [task for task in self.play['tasks'] if 'ansible.builtin.slurp' in task]
        self.assertEqual(len(tasks), 1)
        self.assertIn('oidc-media.json', tasks[0]['ansible.builtin.slurp']['src'])
        self.assertEqual(tasks[0]['delegate_to'],
                         '{{ media_sso_identity_host | default("identity") }}')
        self.assertTrue(tasks[0]['no_log'])

    def test_the_run_is_limited_to_the_media_instance(self):
        for fragment in ('--limit', 'inventory.netbox.yml', 'inventory.cloud.py',
                         'i-a06df9a2dfd1ce6db'):
            self.assertIn(fragment, self.text)

    def test_the_secret_is_only_passed_through_the_environment(self):
        tasks = [task for task in self.play['tasks'] if 'ansible.builtin.command' in task]
        self.assertEqual(len(tasks), 1)
        self.assertTrue(tasks[0]['no_log'])
        environment = tasks[0]['environment']
        self.assertIn('client_secret', environment['NEXTCLOUD_OIDC_CLIENT_SECRET'])
        self.assertIn('client_id', environment['NEXTCLOUD_OIDC_CLIENT_ID'])
        self.assertIn('application/o/nextcloud/.well-known/openid-configuration', self.text)
        discovery = environment['NEXTCLOUD_OIDC_DISCOVERY_URL']
        if discovery == '{{ media_sso_discovery_url }}':
            discovery = self.play['vars']['media_sso_discovery_url']
        self.assertIn('auth.{{ media_sso_zone }}', discovery)

    def test_it_installs_the_unit_script_before_running_it(self):
        copies = [task['ansible.builtin.copy'] for task in self.play['tasks']
                  if 'ansible.builtin.copy' in task]
        self.assertTrue(any(copy['src'].endswith('media/nextcloud/configure-oidc.py')
                            and copy['dest'].startswith('{{ project_dir }}/media/nextcloud/')
                            for copy in copies))


class SyntaxTests(unittest.TestCase):
    def test_the_playbook_parses(self):
        result = syntax_check(PLAYBOOK)
        self.assertEqual(result.returncode, 0,
                         f'{PLAYBOOK.name} did not parse:\n{result.stdout}\n{result.stderr}')


if __name__ == '__main__':
    unittest.main()
