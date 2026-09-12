"""Safety checks for the isolated services-01 application units."""

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_manage(name):
    stack = ROOT / 'stacks' / name
    spec = importlib.util.spec_from_file_location(f'{name}_manage', stack / 'manage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UnitTests(unittest.TestCase):
    units = {
        'home-assistant': {
            'service': 'homeassistant', 'port': '${HOME_ASSISTANT_PORT:-8123}',
            'prefixes': ['/srv/services/home-assistant'], 'playbook': 'home-assistant.yml',
        },
        'homarr': {
            'service': 'homarr', 'port': '${HOMARR_PORT:-7575}',
            'prefixes': ['/srv/services/homarr', '/srv/homarr-stack'], 'playbook': 'homarr.yml',
        },
        'vaultwarden': {
            'service': 'vaultwarden', 'port': '${VAULTWARDEN_PORT:-8222}',
            'prefixes': ['/srv/services/vaultwarden'], 'playbook': 'vaultwarden.yml',
        },
    }

    def test_each_unit_is_loopback_only_and_has_private_state(self):
        for name, expected in self.units.items():
            compose = yaml.safe_load(
                (ROOT / 'stacks' / name / 'compose.yaml').read_text(encoding='utf-8'))
            service = compose['services'][expected['service']]
            self.assertEqual(len(service['ports']), 1, name)
            self.assertIn(expected['port'], service['ports'][0], name)
            self.assertIn('127.0.0.1', service['ports'][0], name)
            self.assertTrue(any('STORAGE_ROOT' in volume and '/appdata' in volume
                                or any(prefix in volume for prefix in expected['prefixes'])
                                for volume in service['volumes']), name)
            self.assertNotIn('network_mode', service, name)

    def test_vaultwarden_uses_a_file_secret_and_disables_signups_by_default(self):
        compose = yaml.safe_load(
            (ROOT / 'stacks/vaultwarden/compose.yaml').read_text(encoding='utf-8'))
        service = compose['services']['vaultwarden']
        self.assertEqual(service['environment']['SIGNUPS_ALLOWED'],
                         '${VAULTWARDEN_SIGNUPS_ALLOWED:-false}')
        self.assertEqual(service['environment']['ADMIN_TOKEN_FILE'], '/run/secrets/admin_token')
        self.assertEqual(compose['secrets']['admin_token']['file'], './secrets/admin_token')

    def test_homarr_requires_an_encryption_key(self):
        compose = yaml.safe_load(
            (ROOT / 'stacks/homarr/compose.yaml').read_text(encoding='utf-8'))
        self.assertIn('SECRET_ENCRYPTION_KEY',
                      compose['services']['homarr']['environment']['SECRET_ENCRYPTION_KEY'])
        self.assertIn(':?', compose['services']['homarr']['environment']['SECRET_ENCRYPTION_KEY'])

    def test_playbooks_use_the_static_bootstrap_group_and_isolated_paths(self):
        for name, expected in self.units.items():
            path = ROOT / 'platform/ansible' / expected['playbook']
            text = path.read_text(encoding='utf-8')
            play = yaml.safe_load(text)[0]
            self.assertEqual(play['hosts'], 'netbox_bootstrap', name)
            # Services may be entered directly through manage.py (the new
            # units) or through the existing role wrapper (Homarr).
            role_based = 'manage.py' not in text and name in str(play.get('roles', []))
            self.assertTrue('manage.py' in text or role_based, name)
            if role_based:
                role_defaults = ROOT / 'platform/ansible/roles' / name / 'defaults/main.yml'
                text += role_defaults.read_text(encoding='utf-8')
            self.assertTrue(any(prefix in text for prefix in expected['prefixes']), name)


class InitTests(unittest.TestCase):
    def test_vaultwarden_init_creates_a_private_token(self):
        manage = load_manage('vaultwarden')
        project = Path(tempfile.mkdtemp(prefix='vw-project-'))
        state = project.parent / f'{project.name}-state'
        try:
            patcher = patch.object(manage, 'ROOT', project)
            patcher.start()
            (project / '.env.example').write_text(f'STORAGE_ROOT={state}\n', encoding='utf-8')
            with patch.object(manage.os, 'chown'):
                manage.init()
            token = project / 'secrets/admin_token'
            self.assertEqual(token.stat().st_mode & 0o777, 0o400)
            self.assertTrue(token.read_text(encoding='utf-8').strip())
            self.assertTrue((state / 'data').is_dir())
        finally:
            patcher.stop()
            shutil.rmtree(project, ignore_errors=True)
            shutil.rmtree(state, ignore_errors=True)

    def test_homarr_init_fills_a_missing_encryption_key(self):
        manage = load_manage('homarr')
        project = Path(tempfile.mkdtemp(prefix='homarr-project-'))
        state = project.parent / f'{project.name}-state'
        try:
            patcher = patch.object(manage, 'ROOT', project)
            patcher.start()
            (project / '.env.example').write_text(f'STORAGE_ROOT={state}\n', encoding='utf-8')
            with patch.object(manage.os, 'chown'):
                manage.init()
            key = project / 'secrets/secret_encryption_key'
            self.assertEqual(len(key.read_text(encoding='utf-8').strip()), 64)
            self.assertEqual(key.stat().st_mode & 0o777, 0o400)
            self.assertTrue((state / 'homarr').is_dir())
        finally:
            patcher.stop()
            shutil.rmtree(project, ignore_errors=True)
            shutil.rmtree(state, ignore_errors=True)

    def test_homarr_rejects_state_nested_in_the_project(self):
        manage = load_manage('homarr')
        project = Path(tempfile.mkdtemp(prefix='homarr-nested-'))
        try:
            patcher = patch.object(manage, 'ROOT', project)
            patcher.start()
            (project / '.env').write_text(f'STORAGE_ROOT={project / "storage"}\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                manage.storage()
        finally:
            patcher.stop()
            shutil.rmtree(project, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
