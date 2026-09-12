"""Safety checks for the isolated game1 RomM stack."""

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/romm'


def load_manage():
    spec = importlib.util.spec_from_file_location('romm_manage', STACK / 'manage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ComposeTests(unittest.TestCase):
    def setUp(self):
        self.compose = yaml.safe_load((STACK / 'compose.yaml').read_text(encoding='utf-8'))

    def test_romm_has_a_private_listener_and_read_only_rom_library(self):
        romm = self.compose['services']['romm']
        self.assertEqual(romm['ports'], ['127.0.0.1:${ROMM_PORT:-8086}:8080'])
        self.assertIn('${ROM_LIBRARY_ROOT:-/srv/game1/games}:/romm/library:ro', romm['volumes'])

    def test_database_is_private_and_has_a_healthcheck(self):
        database = self.compose['services']['romm-db']
        self.assertNotIn('ports', database)
        self.assertIn('healthcheck', database)
        self.assertIn('ROMM_DB_PASSWORD', database['environment']['MARIADB_PASSWORD'])

    def test_application_state_does_not_share_the_library_mount(self):
        volumes = self.compose['services']['romm']['volumes']
        self.assertTrue(any('/romm/resources' in volume for volume in volumes))
        self.assertTrue(any('/romm/assets' in volume for volume in volumes))
        self.assertNotIn('network_mode', self.compose['services']['romm'])


class ManageTests(unittest.TestCase):
    def setUp(self):
        self.manage = load_manage()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patch = patch.object(self.manage, 'ROOT', self.root)
        self.patch.start()
        (self.root / '.env.example').write_text(
            'STORAGE_ROOT=/srv/game1/romm\nROM_LIBRARY_ROOT=/srv/game1/games\n',
            encoding='utf-8')

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_init_rejects_state_inside_project(self):
        (self.root / '.env').write_text(f'STORAGE_ROOT={self.root / "state"}\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.manage.init()

    def test_library_path_rejects_a_project_subdirectory(self):
        (self.root / '.env').write_text(
            f'STORAGE_ROOT=/tmp/romm-state\nROM_LIBRARY_ROOT={self.root / "library"}\n',
            encoding='utf-8')
        with self.assertRaises(ValueError):
            self.manage.library_path()

    def test_init_creates_private_secrets_and_state(self):
        state = self.root.parent / f'{self.root.name}-state'
        (self.root / '.env').write_text(f'STORAGE_ROOT={state}\n', encoding='utf-8')
        self.manage.init()
        self.assertEqual((self.root / '.env').stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / 'secrets/db_password').stat().st_mode & 0o777, 0o400)
        self.assertTrue((state / 'mysql').is_dir())
        shutil.rmtree(state)

    def test_lock_preserves_repository_digests(self):
        (self.root / '.env').write_text('STORAGE_ROOT=/tmp/romm-state\n', encoding='utf-8')
        (self.root / 'compose.yaml').write_text(
            'services: {romm: {image: rommapp/romm:5.1.0}}\n', encoding='utf-8')
        responses = [
            type('Result', (), {'stdout': ''})(),
            type('Result', (), {'stdout': json.dumps({'services': {'romm': {'image': 'rommapp/romm:5.1.0'}}})})(),
        ]
        with patch.object(self.manage, 'compose', side_effect=responses), \
             patch('subprocess.check_output', return_value=json.dumps([{
                 'RepoDigests': ['rommapp/romm@sha256:' + 'c' * 64],
             }]).encode()):
            self.manage.lock()
        lock = yaml.safe_load((self.root / 'compose.lock.yaml').read_text(encoding='utf-8'))
        self.assertRegex(lock['services']['romm']['image'], r'@sha256:[0-9a-f]{64}$')


if __name__ == '__main__':
    unittest.main()
