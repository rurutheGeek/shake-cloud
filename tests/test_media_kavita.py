"""Guard the Kavita unit for media-01 (W04).

A wrong project name, a LAN-bound port, or a writable books mount would only
show up after deployment to the VM and its data disk, so these are source-text
and YAML assertions in the same spirit as test_media_vm.py. Nothing here
connects to media-01 or runs Docker.
"""
import ast
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / 'stacks/media/kavita'
COMPOSE = yaml.safe_load((UNIT / 'compose.yaml').read_text(encoding='utf-8'))
LOCK = yaml.safe_load((UNIT / 'compose.lock.yaml').read_text(encoding='utf-8'))
ROOT_LOCK = yaml.safe_load((ROOT / 'stacks/compose.lock.yaml').read_text(encoding='utf-8'))
PLAYBOOK = ROOT / 'platform/ansible/media-kavita.yml'
SSO_PLAYBOOK = ROOT / 'platform/ansible/media-kavita-sso.yml'
AUTHORITY = 'https://auth.apextox.dpdns.org/application/o/kavita/'
DEFAULT_ROLES = ['Pleb', 'Login', 'Download', 'Bookmark']


class ComposeTests(unittest.TestCase):
    def test_it_is_an_independent_project(self):
        self.assertEqual(COMPOSE['name'], 'media-kavita')

    def test_kavita_is_the_only_service(self):
        self.assertEqual(list(COMPOSE['services']), ['kavita'])

    def test_the_port_is_loopback_only(self):
        ports = COMPOSE['services']['kavita']['ports']
        self.assertEqual(ports, ['127.0.0.1:${KAVITA_PORT:-5000}:5000'])
        self.assertNotIn('0.0.0.0', ''.join(ports))

    def test_config_persists_on_the_data_disk(self):
        volumes = COMPOSE['services']['kavita']['volumes']
        self.assertIn('${STORAGE_ROOT:-/srv/media-stack/storage}/kavita:/kavita/config', volumes)

    def test_books_stay_read_only(self):
        volumes = COMPOSE['services']['kavita']['volumes']
        self.assertIn('${LIBRARY_ROOT:-/srv/media-stack/library}/books:/books:ro', volumes)
        self.assertFalse(any(volume.endswith(':/books') for volume in volumes))

    def test_timezone_is_set(self):
        environment = COMPOSE['services']['kavita']['environment']
        self.assertEqual(environment['TZ'], '${TZ:-Asia/Tokyo}')


class LockTests(unittest.TestCase):
    def test_every_service_is_pinned_to_a_digest(self):
        self.assertEqual(set(LOCK['services']), set(COMPOSE['services']))
        for name, service in LOCK['services'].items():
            self.assertRegex(service['image'], r'@sha256:[0-9a-f]{64}$', name)

    def test_kavita_reuses_the_reviewed_digest(self):
        self.assertEqual(LOCK['services']['kavita'], ROOT_LOCK['services']['kavita'])


def load_manage():
    spec = importlib.util.spec_from_file_location('kavita_manage', UNIT / 'manage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ManageTests(unittest.TestCase):
    def setUp(self):
        self.text = (UNIT / 'manage.py').read_text(encoding='utf-8')

    def test_the_required_actions_are_available(self):
        self.assertIn("choices=['init', 'lock', 'up', 'status', 'down', 'backup']", self.text)

    def test_backup_has_a_default_destination_outside_the_unit(self):
        self.assertIn("default=str(ROOT / 'backups')", self.text)

    def test_backup_requires_root_and_marks_incomplete_runs(self):
        section = self.text.split('def backup', 1)[1].split('def main', 1)[0]
        self.assertIn('os.geteuid() != 0', section)
        self.assertIn('PermissionError', section)
        self.assertIn('.incomplete', section)
        self.assertIn("target.rename(complete)", section)
        self.assertIn("'-C', str(storage), '.'", section)
        self.assertNotIn('LIBRARY_ROOT', section)

    def test_it_uses_only_the_standard_library(self):
        modules = set()
        for node in ast.walk(ast.parse(self.text)):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add((node.module or '').split('.')[0])
        self.assertLessEqual(modules, set(sys.stdlib_module_names))
        self.assertIn('subprocess', modules)

    def test_the_private_env_is_created_from_the_example(self):
        self.assertIn(".env.example", self.text)
        self.assertIn("chmod(0o600)", self.text)

    def test_directories_are_given_to_the_container_user(self):
        self.assertIn('CONTAINER_UID = 33', self.text)
        self.assertIn('os.chown(path, CONTAINER_UID, CONTAINER_GID)', self.text)


class BackupTests(unittest.TestCase):
    """Run the cold backup with Docker and tar mocked out."""

    def setUp(self):
        self.manage = load_manage()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.root_patch = patch.object(self.manage, 'ROOT', self.root)
        self.root_patch.start()
        self.state = self.root / 'storage' / 'kavita'
        self.state.mkdir(parents=True)
        self.library = self.root / 'library' / 'books'
        self.library.mkdir(parents=True)
        (self.root / '.env').write_text(
            f'STORAGE_ROOT={self.root / "storage"}\nLIBRARY_ROOT={self.root / "library"}\n')
        for name in ('compose.yaml', 'compose.lock.yaml', '.env.example', 'manage.py'):
            (self.root / name).write_text('x')

    def tearDown(self):
        self.root_patch.stop()
        self.tmp.cleanup()

    def test_backup_stops_services_and_excludes_the_book_library(self):
        calls = []
        tars = []

        def compose(*args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(stdout='kavita\n' if args[0] == 'ps' else '')

        with patch.object(self.manage.os, 'geteuid', return_value=0), \
             patch.object(self.manage, 'compose', side_effect=compose), \
             patch.object(self.manage, 'run', side_effect=lambda args: tars.append(args)):
            self.manage.backup(self.root / 'backups')
        self.assertEqual(calls[0][0], ('ps', '--services', '--status', 'running'))
        self.assertTrue(calls[0][1].get('capture_output'))
        self.assertIn(('stop', '--timeout', '120'), [args for args, _ in calls])
        self.assertEqual(calls[-1][0], ('start', 'kavita'))
        self.assertEqual(tars[0][:1], ['tar'])
        self.assertIn('-C', tars[0])
        self.assertEqual(tars[0][tars[0].index('-C') + 1], str(self.state))
        self.assertFalse(any(str(self.library) in str(arg) for args in tars for arg in args))
        self.assertIn('compose.lock.yaml', tars[1])
        self.assertIn('manage.py', tars[1])
        runs = [path for path in (self.root / 'backups').iterdir()
                if not path.name.endswith('.incomplete')]
        self.assertEqual(len(runs), 1)
        manifest = json.loads((runs[0] / 'manifest.json').read_text())
        self.assertEqual(manifest['storage_root'], str(self.state))
        self.assertEqual(manifest['format'], 1)
        self.assertIn('books library is not included', manifest['notes'])
        self.assertFalse(list((self.root / 'backups').glob('*.incomplete')))

    def test_backup_failure_restarts_original_services(self):
        def compose(*args, **kwargs):
            return SimpleNamespace(stdout='kavita\n' if args[0] == 'ps' else '')

        with patch.object(self.manage.os, 'geteuid', return_value=0), \
             patch.object(self.manage, 'compose', side_effect=compose) as cp, \
             patch.object(self.manage, 'run',
                          side_effect=subprocess.CalledProcessError(2, 'tar')):
            with self.assertRaises(subprocess.CalledProcessError):
                self.manage.backup(self.root / 'backups')
        self.assertEqual(cp.call_args_list[-1].args, ('start', 'kavita'))
        self.assertEqual(len(list((self.root / 'backups').glob('*.incomplete'))), 1)

    def test_backup_requires_root(self):
        with patch.object(self.manage.os, 'geteuid', return_value=1000):
            with self.assertRaises(PermissionError):
                self.manage.backup(self.root / 'backups')

    def test_backup_refuses_a_destination_inside_the_state(self):
        with patch.object(self.manage.os, 'geteuid', return_value=0):
            with self.assertRaises(ValueError):
                self.manage.backup(self.state / 'backups')


class AnsibleTests(unittest.TestCase):
    def setUp(self):
        self.play = yaml.safe_load(PLAYBOOK.read_text(encoding='utf-8'))[0]

    def test_it_targets_the_media_group_as_root(self):
        self.assertEqual(self.play['hosts'], 'media')
        self.assertTrue(self.play['become'])

    def test_it_deploys_the_unit_under_the_project_directory(self):
        copies = [task['ansible.builtin.copy'] for task in self.play['tasks']
                  if 'ansible.builtin.copy' in task]
        self.assertTrue(any(copy['dest'].startswith('{{ project_dir }}/media/kavita/')
                            for copy in copies))

    def test_it_generates_a_private_env_from_group_vars(self):
        copies = [task['ansible.builtin.copy'] for task in self.play['tasks']
                  if 'ansible.builtin.copy' in task]
        env = [copy for copy in copies if copy['dest'].endswith('/.env')]
        self.assertEqual(len(env), 1)
        self.assertEqual(env[0]['mode'], '0600')
        self.assertIn('{{ storage_root }}', env[0]['content'])
        self.assertIn('{{ library_root }}', env[0]['content'])

    def test_it_starts_the_unit_with_manage_py(self):
        commands = [task['ansible.builtin.command']['argv'] for task in self.play['tasks']
                    if 'ansible.builtin.command' in task]
        self.assertTrue(any(argv[-1] == 'up' and argv[-2].endswith('manage.py')
                            for argv in commands))

    def test_it_copies_the_bootstrap_script(self):
        tasks = [task for task in self.play['tasks'] if 'ansible.builtin.copy' in task]
        self.assertTrue(any('bootstrap.py' in str(task.get('loop', '')) for task in tasks))

    def test_it_runs_bootstrap_after_the_unit_is_up_and_counts_only_changes(self):
        tasks = [task for task in self.play['tasks'] if 'ansible.builtin.command' in task]
        up = next(task for task in tasks
                  if task['ansible.builtin.command']['argv'][-1] == 'up')
        bootstrap = next(task for task in tasks
                         if task['ansible.builtin.command']['argv'][-1].endswith('bootstrap.py'))
        self.assertLess(tasks.index(up), tasks.index(bootstrap))
        self.assertEqual(bootstrap['changed_when'], "'CHANGED:' in kavita_bootstrap.stdout")


class SsoAnsibleTests(unittest.TestCase):
    def setUp(self):
        self.play = yaml.safe_load(SSO_PLAYBOOK.read_text(encoding='utf-8'))[0]

    def test_it_targets_the_media_group_as_root(self):
        self.assertEqual(self.play['hosts'], 'media')
        self.assertTrue(self.play['become'])

    def test_it_slurps_the_identity_credentials_without_logging_them(self):
        tasks = [task for task in self.play['tasks'] if 'ansible.builtin.slurp' in task]
        self.assertEqual(len(tasks), 1)
        slurp = tasks[0]['ansible.builtin.slurp']
        self.assertEqual(slurp['src'], '/opt/identity-stack/secrets/oidc-media.json')
        self.assertIn('default("identity")', tasks[0]['delegate_to'])
        self.assertTrue(tasks[0]['no_log'])

    def test_it_runs_configure_oidc_with_the_client_environment(self):
        tasks = [task for task in self.play['tasks'] if 'ansible.builtin.command' in task]
        self.assertEqual(len(tasks), 1)
        command = tasks[0]['ansible.builtin.command']
        self.assertTrue(command['argv'][-1].endswith('configure-oidc.py'))
        environment = tasks[0]['environment']
        self.assertIn('KAVITA_OIDC_CLIENT_ID', environment)
        self.assertIn('KAVITA_OIDC_CLIENT_SECRET', environment)
        self.assertEqual(tasks[0]['changed_when'],
                         "'CHANGED:' in media_sso_kavita_oidc.stdout")
        self.assertTrue(tasks[0]['no_log'])

    def test_it_documents_the_inventories_and_the_limit(self):
        text = SSO_PLAYBOOK.read_text(encoding='utf-8')
        self.assertIn('inventory.cloud.py', text)
        self.assertIn('inventory.netbox.yml', text)
        self.assertIn('--limit', text)


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = {} if payload is None else payload
        self.ok = status_code < 400

    def json(self):
        return self.payload

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f'HTTP {self.status_code}')


class FakeKavita:
    """In-memory Kavita API for bootstrap.py and configure-oidc.py."""

    def __init__(self, administrator=False, libraries=None, settings=None):
        self.administrator = administrator
        self.libraries = list(libraries or [])
        self.settings = dict(settings or {'enableFolderWatching': False})
        self.requests = []
        self.registered = None
        self.created_library = None
        self.posted_settings = None
        self.headers = {}

    def get(self, url, timeout=None, **kwargs):
        self.requests.append(('GET', url))
        if url.endswith('/api/Settings'):
            return FakeResponse(200, dict(self.settings))
        if url.endswith('/api/Library/libraries'):
            return FakeResponse(200, [dict(library) for library in self.libraries])
        raise AssertionError(url)

    def post(self, url, json=None, timeout=None, **kwargs):
        self.requests.append(('POST', url))
        if url.endswith('/api/Account/login'):
            if not self.administrator:
                return FakeResponse(401, {})
            return FakeResponse(200, {'token': 'test-token'})
        if url.endswith('/api/Account/register'):
            self.registered = dict(json)
            self.administrator = True
            return FakeResponse(200, {'token': 'test-token'})
        if url.endswith('/api/Settings'):
            self.settings = dict(json)
            self.posted_settings = dict(json)
            return FakeResponse(200, {})
        if url.endswith('/api/Library/create'):
            self.created_library = dict(json)
            self.libraries.append({'id': len(self.libraries) + 1,
                                   'name': json['name'], 'folders': json['folders']})
            return FakeResponse(200, {'id': 1})
        raise AssertionError(url)


def load_script(name, module_name):
    spec = importlib.util.spec_from_file_location(module_name, UNIT / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.module = load_script('bootstrap.py', 'kavita_bootstrap')
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.root_patch = patch.object(self.module, 'ROOT', self.root)
        self.root_patch.start()
        (self.root / '.env').write_text('KAVITA_PORT=5000\n')
        self.server = FakeKavita()

    def tearDown(self):
        self.root_patch.stop()
        self.tmp.cleanup()

    def run_bootstrap(self):
        output = io.StringIO()
        with patch.object(self.module.requests, 'Session', return_value=self.server), \
             contextlib.redirect_stdout(output):
            self.module.main()
        return output.getvalue()

    def test_the_script_exists(self):
        self.assertTrue((UNIT / 'bootstrap.py').exists())

    def test_it_registers_the_administrator_and_creates_the_books_library(self):
        output = self.run_bootstrap()
        self.assertIn('CHANGED:', output)
        self.assertTrue(all(url.startswith('http://127.0.0.1:5000/api/')
                            for _, url in self.server.requests))
        accounts_path = self.root / 'secrets' / 'accounts.json'
        self.assertEqual(stat.S_IMODE((self.root / 'secrets').stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(accounts_path.stat().st_mode), 0o600)
        accounts = json.loads(accounts_path.read_text())
        self.assertEqual(accounts['username'], 'admin')
        self.assertTrue(accounts['password'].startswith('Aa1!'))
        self.assertNotIn(accounts['password'], output)
        self.assertEqual(self.server.registered['email'], 'admin@localhost.localdomain')
        self.assertEqual(self.server.created_library['name'], 'Books')
        self.assertEqual(self.server.created_library['folders'], ['/books'])
        self.assertTrue(self.server.created_library['folderWatching'])
        self.assertTrue(self.server.settings['enableFolderWatching'])

    def test_it_is_idempotent_and_keeps_the_generated_password(self):
        self.run_bootstrap()
        accounts_path = self.root / 'secrets' / 'accounts.json'
        password = json.loads(accounts_path.read_text())['password']
        output = self.run_bootstrap()
        self.assertIn('OK:', output)
        self.assertEqual(json.loads(accounts_path.read_text())['password'], password)
        self.assertEqual(sum(1 for method, url in self.server.requests
                             if method == 'POST' and url.endswith('/api/Library/create')), 1)
        self.assertEqual(sum(1 for method, url in self.server.requests
                             if method == 'POST' and url.endswith('/api/Settings')), 1)
        self.assertEqual(sum(1 for method, url in self.server.requests
                             if method == 'POST' and url.endswith('/api/Account/register')), 1)


class ConfigureOidcTests(unittest.TestCase):
    def setUp(self):
        self.module = load_script('configure-oidc.py', 'kavita_configure_oidc')
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.root_patch = patch.object(self.module, 'ROOT', self.root)
        self.root_patch.start()
        (self.root / '.env').write_text('KAVITA_PORT=5000\n')
        (self.root / 'secrets').mkdir(mode=0o700)
        (self.root / 'secrets' / 'accounts.json').write_text(json.dumps(
            {'username': 'admin', 'password': 'Aa1!local-admin'}))
        self.server = FakeKavita(administrator=True, libraries=[{'id': 7, 'name': 'Books'}],
                                 settings={'enableFolderWatching': True, 'oidcConfig': {}})
        self.compose_calls = []

    def tearDown(self):
        self.root_patch.stop()
        self.tmp.cleanup()

    def run_configure(self):
        output = io.StringIO()
        environment = {'KAVITA_OIDC_CLIENT_ID': 'kavita-client',
                       'KAVITA_OIDC_CLIENT_SECRET': 's3cret-value'}
        with patch.dict(os.environ, environment), \
             patch.object(self.module.requests, 'Session', return_value=self.server), \
             patch.object(self.module, 'compose',
                          side_effect=lambda *args: self.compose_calls.append(args)), \
             contextlib.redirect_stdout(output):
            self.module.main()
        return output.getvalue()

    def test_the_script_exists(self):
        self.assertTrue((UNIT / 'configure-oidc.py').exists())

    def test_it_writes_the_provider_settings_and_restarts_once(self):
        output = self.run_configure()
        self.assertIn('CHANGED:', output)
        self.assertNotIn('s3cret-value', output)
        config = self.server.posted_settings['oidcConfig']
        self.assertEqual(config['authority'], AUTHORITY)
        self.assertEqual(config['clientId'], 'kavita-client')
        self.assertEqual(config['secret'], 's3cret-value')
        self.assertIs(config['provisionAccounts'], True)
        self.assertIs(config['requireVerifiedEmail'], True)
        self.assertIs(config['syncUserSettings'], False)
        self.assertEqual(config['defaultRoles'], DEFAULT_ROLES)
        self.assertEqual(config['defaultLibraries'], [7])
        self.assertIs(config['defaultIncludeUnknowns'], True)
        self.assertEqual(self.compose_calls, [('restart', 'kavita')])

    def test_it_is_idempotent_and_does_not_restart_again(self):
        self.run_configure()
        output = self.run_configure()
        self.assertIn('OK:', output)
        self.assertEqual(self.compose_calls, [('restart', 'kavita')])
        self.assertEqual(sum(1 for method, url in self.server.requests
                             if method == 'POST' and url.endswith('/api/Settings')), 1)

    def test_it_refuses_to_run_without_credentials(self):
        with patch.dict(os.environ, {'KAVITA_OIDC_CLIENT_ID': '',
                                     'KAVITA_OIDC_CLIENT_SECRET': ''}):
            with self.assertRaises(RuntimeError):
                self.module.main()

    def test_the_authority_roles_and_restart_are_fixed_in_source(self):
        text = (UNIT / 'configure-oidc.py').read_text(encoding='utf-8')
        self.assertIn(f"AUTHORITY = '{AUTHORITY}'", text)
        self.assertIn(f"DEFAULT_ROLES = {DEFAULT_ROLES!r}", text)
        self.assertIn("compose('restart', 'kavita')", text)

    def test_the_secret_is_only_read_from_the_environment_and_never_printed(self):
        text = (UNIT / 'configure-oidc.py').read_text(encoding='utf-8')
        self.assertIn('KAVITA_OIDC_CLIENT_ID', text)
        self.assertIn('KAVITA_OIDC_CLIENT_SECRET', text)
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == 'print':
                self.assertNotIn('secret', ast.dump(node))


class SecretTests(unittest.TestCase):
    def test_no_credential_is_committed_in_the_unit(self):
        for name in ('compose.yaml', 'compose.lock.yaml', '.env.example', 'manage.py',
                     'bootstrap.py', 'configure-oidc.py'):
            text = (UNIT / name).read_text(encoding='utf-8')
            self.assertNotIn('PRIVATE KEY', text, name)
            self.assertNotIn('AKIA', text, name)
            self.assertNotRegex(text, r'(?im)^(PASSWORD|TOKEN|SECRET|API_KEY)=', name)

    def test_the_readme_links_the_work_item_and_the_source(self):
        readme = (UNIT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('../../../docs/development/W04-kavita.md', readme)
        self.assertIn('stacks/compose.lock.yaml', readme)

    def test_the_readme_documents_the_bootstrap_and_oidc_dependencies(self):
        readme = (UNIT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('bootstrap.py', readme)
        self.assertIn('configure-oidc.py', readme)
        self.assertIn('python3-requests', readme)
        self.assertIn('KAVITA_OIDC_CLIENT_SECRET', readme)


if __name__ == '__main__':
    unittest.main()
