"""Static and local safety checks for the eufy-security-ws unit."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/eufy-security-ws'
PLAYBOOK = ROOT / 'platform/ansible/eufy-security-ws.yml'


def load_manage():
    spec = importlib.util.spec_from_file_location('eufy_ws_manage', STACK / 'manage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ComposeTests(unittest.TestCase):
    def setUp(self):
        self.compose = yaml.safe_load((STACK / 'compose.yaml').read_text(encoding='utf-8'))

    def test_service_joins_the_home_assistant_network_without_publishing_ports(self):
        service = self.compose['services']['eufy-security-ws']
        self.assertNotIn('ports', service)
        self.assertEqual(service['networks'], ['homeassistant'])
        self.assertEqual(self.compose['networks']['homeassistant']['name'],
                         'services-home-assistant_homeassistant')
        self.assertTrue(self.compose['networks']['homeassistant']['external'])

    def test_credentials_are_required_and_the_healthcheck_is_local(self):
        service = self.compose['services']['eufy-security-ws']
        self.assertIn(':?', service['environment']['USERNAME'])
        self.assertIn(':?', service['environment']['PASSWORD'])
        self.assertIn('127.0.0.1', ' '.join(service['healthcheck']['test']))
        self.assertIn('/data', ' '.join(service['volumes']))


class ManageTests(unittest.TestCase):
    def setUp(self):
        self.manage = load_manage()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patch = patch.object(self.manage, 'ROOT', self.root)
        self.patch.start()
        (self.root / '.env.example').write_text(
            'STORAGE_ROOT=/srv/services/eufy-security-ws\nTZ=Asia/Tokyo\n', encoding='utf-8')

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_init_rejects_state_inside_project(self):
        (self.root / '.env').write_text(f'STORAGE_ROOT={self.root / "state"}\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.manage.init()

    def test_init_creates_private_env_and_data(self):
        state = self.root.parent / f'{self.root.name}-state'
        (self.root / '.env').write_text(f'STORAGE_ROOT={state}\n', encoding='utf-8')
        self.manage.init()
        self.assertEqual((self.root / '.env').stat().st_mode & 0o777, 0o600)
        self.assertTrue((state / 'data').is_dir())

    def test_lock_pins_the_repository_digest(self):
        (self.root / '.env').write_text('STORAGE_ROOT=/tmp/eufy-state\n', encoding='utf-8')
        (self.root / 'compose.yaml').write_text(
            'services: {eufy-security-ws: {image: eufy-security-ws:3.1.0}}\n', encoding='utf-8')
        responses = [
            type('Result', (), {'stdout': ''})(),
            type('Result', (), {'stdout': json.dumps(
                {'services': {'eufy-security-ws': {'image': 'eufy-security-ws:3.1.0'}}})})(),
        ]
        with patch.object(self.manage, 'compose', side_effect=responses), \
             patch('subprocess.check_output', return_value=json.dumps([{
                 'RepoDigests': ['bropat/eufy-security-ws@sha256:' + 'a' * 64],
             }]).encode()):
            self.manage.lock()
        lock = yaml.safe_load((self.root / 'compose.lock.yaml').read_text(encoding='utf-8'))
        self.assertRegex(lock['services']['eufy-security-ws']['image'], r'@sha256:[0-9a-f]{64}$')


class AnsibleTests(unittest.TestCase):
    def setUp(self):
        self.text = PLAYBOOK.read_text(encoding='utf-8')
        self.play = yaml.safe_load(self.text)[0]

    def test_playbook_targets_services_01_and_reads_credentials_from_sops(self):
        self.assertEqual(self.play['hosts'], 'netbox_bootstrap')
        self.assertIn('eufy_credentials', self.text)
        self.assertIn('no_log: true', self.text)
        self.assertIn('manage.py', self.text)
        self.assertIn("when: eufy_configured", self.text)


if __name__ == '__main__':
    unittest.main()
