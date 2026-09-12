"""Static and local safety checks for the Home Assistant Container unit."""

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import yaml


ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/home-assistant'
PLAYBOOK = ROOT / 'platform/ansible/home-assistant.yml'
IDENTITY = ROOT / 'stacks/identity/configure.py'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_manage():
    return load_module('home_assistant_manage', STACK / 'manage.py')


class ComposeTests(unittest.TestCase):
    def setUp(self):
        self.compose = yaml.safe_load((STACK / 'compose.yaml').read_text(encoding='utf-8'))

    def test_service_is_loopback_only_and_persists_config(self):
        service = self.compose['services']['homeassistant']
        self.assertEqual(service['ports'], ['127.0.0.1:${HOME_ASSISTANT_PORT:-8123}:8123'])
        self.assertIn('${STORAGE_ROOT:-/srv/services/home-assistant}/config:/config',
                      service['volumes'])

    def test_the_container_does_not_require_host_network_or_privileged_mode(self):
        service = self.compose['services']['homeassistant']
        self.assertNotIn('network_mode', service)
        self.assertNotIn('privileged', service)

    def test_healthcheck_is_local(self):
        test = self.compose['services']['homeassistant']['healthcheck']['test']
        self.assertIn('127.0.0.1', ' '.join(test))


class ManageTests(unittest.TestCase):
    def setUp(self):
        self.manage = load_manage()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patch = patch.object(self.manage, 'ROOT', self.root)
        self.patch.start()
        (self.root / '.env.example').write_text(
            'STORAGE_ROOT=/srv/services/home-assistant\nHOME_ASSISTANT_PORT=8123\nTZ=Asia/Tokyo\n',
            encoding='utf-8',
        )

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_init_rejects_state_inside_project(self):
        (self.root / '.env').write_text(f'STORAGE_ROOT={self.root / "state"}\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.manage.init()

    def test_init_creates_private_env_and_config(self):
        # The production guard rejects a state directory nested below the
        # project, so place the fixture beside the temporary project.
        state = self.root.parent / f'{self.root.name}-state'
        (self.root / '.env').write_text(f'STORAGE_ROOT={state}\n', encoding='utf-8')
        self.manage.init()
        self.assertEqual((self.root / '.env').stat().st_mode & 0o777, 0o600)
        self.assertTrue((state / 'config').is_dir())
        shutil.rmtree(state)

    def http_store(self, stable, pending=None):
        state = self.root.parent / f'{self.root.name}-state'
        (self.root / '.env').write_text(f'STORAGE_ROOT={state}\n', encoding='utf-8')
        path = state / 'config' / '.storage' / 'http'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            'version': 2,
            'minor_version': 2,
            'key': 'http',
            'data': {
                'stable': stable,
                'pending': pending,
                'yaml_migration_done': True,
            },
        }), encoding='utf-8')
        return path

    def test_ensure_http_proxy_promotes_the_setting_and_drops_the_trial(self):
        store = self.http_store(
            {'server_port': 8123, 'custom': 'keep'},
            {'server_port': 8123, 'use_x_forwarded_for': True},
        )
        self.assertTrue(self.manage.ensure_http_proxy('172.31.254.1'))
        data = json.loads(store.read_text(encoding='utf-8'))['data']
        self.assertEqual(data['stable']['use_x_forwarded_for'], True)
        self.assertEqual(data['stable']['trusted_proxies'], ['172.31.254.1'])
        self.assertEqual(data['stable']['custom'], 'keep')
        self.assertIsNone(data['pending'])
        shutil.rmtree(store.parents[2])

    def test_ensure_http_proxy_is_idempotent(self):
        store = self.http_store({
            'use_x_forwarded_for': True,
            'trusted_proxies': ['172.31.254.1'],
        })
        before = store.read_text(encoding='utf-8')
        self.assertFalse(self.manage.ensure_http_proxy('172.31.254.1'))
        self.assertEqual(store.read_text(encoding='utf-8'), before)
        shutil.rmtree(store.parents[2])

    def test_ensure_http_proxy_requires_a_started_store(self):
        missing = self.root.parent / f'{self.root.name}-missing'
        (self.root / '.env').write_text(f'STORAGE_ROOT={missing}\n', encoding='utf-8')
        with self.assertRaises(FileNotFoundError):
            self.manage.ensure_http_proxy('172.31.254.1')

    def test_lock_uses_repository_digest_and_writes_service_map(self):
        (self.root / '.env').write_text('STORAGE_ROOT=/tmp/ha-state\n', encoding='utf-8')
        (self.root / 'compose.yaml').write_text('services: {homeassistant: {image: ha:stable}}\n', encoding='utf-8')
        responses = [
            type('Result', (), {'stdout': ''})(),
            type('Result', (), {'stdout': json.dumps({'services': {'homeassistant': {'image': 'ha:stable'}}})})(),
        ]
        with patch.object(self.manage, 'compose', side_effect=responses), \
             patch('subprocess.check_output', return_value=json.dumps([{
                 'RepoDigests': ['ghcr.io/home-assistant/home-assistant@sha256:' + 'a' * 64],
             }]).encode()):
            self.manage.lock()
        lock = yaml.safe_load((self.root / 'compose.lock.yaml').read_text(encoding='utf-8'))
        self.assertRegex(lock['services']['homeassistant']['image'], r'@sha256:[0-9a-f]{64}$')


class IntegrationInstallTests(unittest.TestCase):
    def setUp(self):
        self.manage = load_manage()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patch = patch.object(self.manage, 'ROOT', self.root)
        self.patch.start()
        self.state = self.root.parent / f'{self.root.name}-state'
        (self.root / '.env').write_text(f'STORAGE_ROOT={self.state}\n', encoding='utf-8')

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    @staticmethod
    def zip_bytes(files):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as bundle:
            for name, content in files.items():
                bundle.writestr(name, content)
        return buffer.getvalue()

    @staticmethod
    def tar_bytes(files):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as bundle:
            for name in files:
                data = b'{}'
                info = tarfile.TarInfo(name)
                info.size = len(data)
                bundle.addfile(info, io.BytesIO(data))
        return buffer.getvalue()

    def install(self, payload, name='auth_oidc', member='', sha256=None):
        digest = sha256 or hashlib.sha256(payload).hexdigest()
        response = type('Response', (), {
            '__enter__': lambda self: self,
            '__exit__': lambda *args: False,
            'read': lambda self: payload,
        })()
        with patch.object(self.manage.urllib.request, 'urlopen', return_value=response):
            return self.manage.install_integration(
                name, 'https://example.invalid/archive', digest, member)

    def test_installs_a_zip_and_repeats_as_a_no_op(self):
        payload = self.zip_bytes({
            'manifest.json': '{"domain": "auth_oidc"}', '__init__.py': ''})
        self.assertTrue(self.install(payload))
        target = self.state / 'config' / 'custom_components' / 'auth_oidc'
        self.assertTrue((target / 'manifest.json').is_file())
        self.assertFalse(self.install(payload))

    def test_rejects_a_digest_mismatch_without_replacing_the_target(self):
        payload = self.zip_bytes({'manifest.json': '{}'})
        with self.assertRaises(RuntimeError):
            self.install(payload, sha256='0' * 64)
        self.assertFalse((self.state / 'config' / 'custom_components' / 'auth_oidc').exists())

    def test_tar_member_selects_the_integration_directory(self):
        payload = self.tar_bytes([
            'eufy_security-8.2.4/README.md',
            'eufy_security-8.2.4/custom_components/eufy_security/manifest.json',
        ])
        self.assertTrue(self.install(
            payload, name='eufy_security',
            member='eufy_security-8.2.4/custom_components/eufy_security'))
        target = self.state / 'config' / 'custom_components' / 'eufy_security'
        self.assertTrue((target / 'manifest.json').is_file())
        self.assertFalse((target / 'README.md').exists())


class FakeIdentityAPI:
    def __init__(self):
        self.calls = []
        self.bound = []

    def rows(self, path):
        if path.startswith('policies/bindings/'):
            return [{'group': group} for group in self.bound]
        return []

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path == 'providers/oauth2/':
            return {'pk': 'provider-ha', **body}
        if path == 'core/applications/':
            return {'pk': 'app-ha', **body}
        if path == 'policies/bindings/':
            self.bound.append(body['group'])
        return {}


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.identity = load_module('identity_configure', IDENTITY)

    def test_home_assistant_is_a_public_client_with_a_strict_callback(self):
        self.assertEqual(self.identity.HOME_ASSISTANT, 'home-assistant')
        self.assertEqual(
            self.identity.home_assistant_redirect('apextox.dpdns.org'),
            'https://ha.apextox.dpdns.org/auth/oidc/callback')
        flows = {
            'default-provider-authorization-implicit-consent': 'auth',
            'default-provider-invalidation-flow': 'invalidation',
        }
        body = self.identity.public_oidc_provider_body(
            'home-assistant', 'https://ha.apextox.dpdns.org/auth/oidc/callback',
            flows, ['mapping'], 'signing-key')
        self.assertEqual(body['client_type'], 'public')
        self.assertNotIn('client_secret', body)
        self.assertEqual(body['sub_mode'], 'user_uuid')
        self.assertTrue(body['include_claims_in_id_token'])
        self.assertEqual(body['redirect_uris'][0]['matching_mode'], 'strict')
        self.assertEqual(body['redirect_uris'][0]['redirect_uri_type'], 'authorization')

    def test_home_assistant_is_open_to_users_and_admins(self):
        api = FakeIdentityAPI()
        groups = {'users': {'pk': 'group-users'}, 'admins': {'pk': 'group-admins'}}
        flows = {
            'default-provider-authorization-implicit-consent': 'auth',
            'default-provider-invalidation-flow': 'invalidation',
        }
        with contextlib.redirect_stdout(io.StringIO()):
            self.identity.configure_home_assistant(
                api, groups, flows, ['mapping'], 'signing-key',
                'https://cloud.apextox.dpdns.org')
        self.assertEqual(set(api.bound), {'group-users', 'group-admins'})
        provider = next(body for method, path, body in api.calls
                        if path == 'providers/oauth2/')
        self.assertEqual(provider['client_type'], 'public')


class AnsibleTests(unittest.TestCase):
    def test_playbook_uses_independent_project_and_storage(self):
        play = yaml.safe_load(PLAYBOOK.read_text(encoding='utf-8'))[0]
        self.assertEqual(play['hosts'], 'netbox_bootstrap')
        text = PLAYBOOK.read_text(encoding='utf-8')
        self.assertIn('home_assistant_project_dir', text)
        self.assertIn('home_assistant_storage_root', text)
        self.assertIn('manage.py', text)
        self.assertIn('ensure-http-proxy', text)
        self.assertIn('home_assistant_trusted_proxy', text)
        self.assertIn('install-integration', text)
        self.assertIn('auth_oidc', text)
        self.assertIn('eufy_security', text)
        self.assertIn('auth_oidc', text)
        self.assertIn('home_assistant_oidc_discovery', text)


if __name__ == '__main__':
    unittest.main()
