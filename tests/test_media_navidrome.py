"""Guard the Navidrome unit for media-01 (W05).

A wrong project name, a LAN-bound port, or a writable music mount would only
show up after deployment to the VM and its data disk, so these are source-text
and YAML assertions in the same spirit as test_media_vm.py. Nothing here
connects to media-01 or runs Docker.
"""
import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / 'stacks/media/navidrome'
COMPOSE = yaml.safe_load((UNIT / 'compose.yaml').read_text(encoding='utf-8'))
LOCK = yaml.safe_load((UNIT / 'compose.lock.yaml').read_text(encoding='utf-8'))
ROOT_LOCK = yaml.safe_load((ROOT / 'stacks/compose.lock.yaml').read_text(encoding='utf-8'))
PLAYBOOK = ROOT / 'platform/ansible/media-navidrome.yml'


class ComposeTests(unittest.TestCase):
    def test_it_is_an_independent_project(self):
        self.assertEqual(COMPOSE['name'], 'media-navidrome')

    def test_navidrome_is_the_only_service(self):
        self.assertEqual(list(COMPOSE['services']), ['navidrome'])

    def test_it_runs_as_the_library_user(self):
        service = COMPOSE['services']['navidrome']
        self.assertEqual(service['user'], '${MEDIA_UID:-33}:${MEDIA_GID:-33}')

    def test_the_port_is_loopback_only(self):
        ports = COMPOSE['services']['navidrome']['ports']
        self.assertEqual(ports, ['127.0.0.1:${NAVIDROME_PORT:-4533}:4533'])
        self.assertNotIn('0.0.0.0', ''.join(ports))

    def test_data_persists_on_the_data_disk(self):
        volumes = COMPOSE['services']['navidrome']['volumes']
        self.assertIn('${STORAGE_ROOT:-/srv/media-stack/storage}/navidrome:/data', volumes)

    def test_music_stays_read_only(self):
        volumes = COMPOSE['services']['navidrome']['volumes']
        self.assertIn('${LIBRARY_ROOT:-/srv/media-stack/library}/music:/music:ro', volumes)
        self.assertFalse(any(volume.endswith(':/music') for volume in volumes))

    def test_the_container_layout_and_language_are_fixed(self):
        environment = COMPOSE['services']['navidrome']['environment']
        self.assertEqual(environment['ND_MUSICFOLDER'], '/music')
        self.assertEqual(environment['ND_DATAFOLDER'], '/data')
        self.assertEqual(environment['ND_SCANSCHEDULE'], '@every 1h')
        self.assertEqual(environment['ND_DEFAULTLANGUAGE'], 'ja')
        self.assertEqual(environment['TZ'], '${TZ:-Asia/Tokyo}')

    def test_the_healthcheck_uses_the_ping_endpoint(self):
        healthcheck = COMPOSE['services']['navidrome']['healthcheck']
        self.assertIn('http://127.0.0.1:4533/ping', healthcheck['test'])


class ForwardAuthTests(unittest.TestCase):
    def test_the_proxy_user_header_is_trusted(self):
        environment = COMPOSE['services']['navidrome']['environment']
        self.assertEqual(environment['ND_EXTAUTH_USERHEADER'], 'Remote-User')

    def test_only_loopback_and_the_docker_bridge_are_trusted(self):
        environment = COMPOSE['services']['navidrome']['environment']
        self.assertEqual(environment['ND_EXTAUTH_TRUSTEDSOURCES'],
                         '127.0.0.1/32,172.16.0.0/12')

    def test_forward_auth_keeps_the_public_port_on_loopback(self):
        ports = COMPOSE['services']['navidrome']['ports']
        self.assertEqual(ports, ['127.0.0.1:${NAVIDROME_PORT:-4533}:4533'])
        self.assertNotIn('0.0.0.0', ''.join(ports))


class LockTests(unittest.TestCase):
    def test_every_service_is_pinned_to_a_digest(self):
        self.assertEqual(set(LOCK['services']), set(COMPOSE['services']))
        for name, service in LOCK['services'].items():
            self.assertRegex(service['image'], r'@sha256:[0-9a-f]{64}$', name)

    def test_navidrome_reuses_the_reviewed_digest(self):
        self.assertEqual(LOCK['services']['navidrome'], ROOT_LOCK['services']['navidrome'])


def load_manage():
    spec = importlib.util.spec_from_file_location('navidrome_manage', UNIT / 'manage.py')
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

    def test_directories_follow_the_configured_library_user(self):
        self.assertIn("config.get('MEDIA_UID', 33)", self.text)
        self.assertIn("config.get('MEDIA_GID', 33)", self.text)
        self.assertIn('os.chown(path, uid, gid)', self.text)


class BackupTests(unittest.TestCase):
    """Run the cold backup with Docker and tar mocked out."""

    def setUp(self):
        self.manage = load_manage()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.root_patch = patch.object(self.manage, 'ROOT', self.root)
        self.root_patch.start()
        self.state = self.root / 'storage' / 'navidrome'
        self.state.mkdir(parents=True)
        self.library = self.root / 'library' / 'music'
        self.library.mkdir(parents=True)
        (self.root / '.env').write_text(
            f'STORAGE_ROOT={self.root / "storage"}\nLIBRARY_ROOT={self.root / "library"}\n')
        for name in ('compose.yaml', 'compose.lock.yaml', '.env.example', 'manage.py'):
            (self.root / name).write_text('x')

    def tearDown(self):
        self.root_patch.stop()
        self.tmp.cleanup()

    def test_backup_stops_services_and_excludes_the_music_library(self):
        calls = []
        tars = []

        def compose(*args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(stdout='navidrome\n' if args[0] == 'ps' else '')

        with patch.object(self.manage.os, 'geteuid', return_value=0), \
             patch.object(self.manage, 'compose', side_effect=compose), \
             patch.object(self.manage, 'run', side_effect=lambda args: tars.append(args)):
            self.manage.backup(self.root / 'backups')
        self.assertEqual(calls[0][0], ('ps', '--services', '--status', 'running'))
        self.assertTrue(calls[0][1].get('capture_output'))
        self.assertIn(('stop', '--timeout', '120'), [args for args, _ in calls])
        self.assertEqual(calls[-1][0], ('start', 'navidrome'))
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
        self.assertIn('music library is not included', manifest['notes'])
        self.assertFalse(list((self.root / 'backups').glob('*.incomplete')))

    def test_backup_failure_restarts_original_services(self):
        def compose(*args, **kwargs):
            return SimpleNamespace(stdout='navidrome\n' if args[0] == 'ps' else '')

        with patch.object(self.manage.os, 'geteuid', return_value=0), \
             patch.object(self.manage, 'compose', side_effect=compose) as cp, \
             patch.object(self.manage, 'run',
                          side_effect=subprocess.CalledProcessError(2, 'tar')):
            with self.assertRaises(subprocess.CalledProcessError):
                self.manage.backup(self.root / 'backups')
        self.assertEqual(cp.call_args_list[-1].args, ('start', 'navidrome'))
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
        self.assertTrue(any(copy['dest'].startswith('{{ project_dir }}/media/navidrome/')
                            for copy in copies))

    def test_it_generates_a_private_env_from_group_vars(self):
        copies = [task['ansible.builtin.copy'] for task in self.play['tasks']
                  if 'ansible.builtin.copy' in task]
        env = [copy for copy in copies if copy['dest'].endswith('/.env')]
        self.assertEqual(len(env), 1)
        self.assertEqual(env[0]['mode'], '0600')
        self.assertIn('{{ storage_root }}', env[0]['content'])
        self.assertIn('{{ library_root }}', env[0]['content'])
        self.assertIn('MEDIA_UID', env[0]['content'])

    def test_it_starts_the_unit_with_manage_py(self):
        commands = [task['ansible.builtin.command']['argv'] for task in self.play['tasks']
                    if 'ansible.builtin.command' in task]
        self.assertTrue(any(argv[-1] == 'up' and argv[-2].endswith('manage.py')
                            for argv in commands))


class SecretTests(unittest.TestCase):
    def test_no_credential_is_committed_in_the_unit(self):
        for name in ('compose.yaml', 'compose.lock.yaml', '.env.example', 'manage.py'):
            text = (UNIT / name).read_text(encoding='utf-8')
            self.assertNotIn('PRIVATE KEY', text, name)
            self.assertNotIn('AKIA', text, name)
            self.assertNotRegex(text, r'(?im)^(PASSWORD|TOKEN|SECRET|API_KEY)=', name)

    def test_the_readme_documents_the_auth_proxy_and_the_work_item(self):
        readme = (UNIT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('../../../docs/development/W05-navidrome.md', readme)
        self.assertIn('認証プロキシ', readme)
        self.assertIn('読み取り専用', readme)
        self.assertIn('stacks/compose.lock.yaml', readme)

    def test_the_readme_documents_forward_auth(self):
        readme = (UNIT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('ND_EXTAUTH_USERHEADER', readme)
        self.assertIn('ND_EXTAUTH_TRUSTEDSOURCES', readme)
        self.assertIn('Remote-User', readme)
        self.assertIn('127.0.0.1/32', readme)


if __name__ == '__main__':
    unittest.main()
