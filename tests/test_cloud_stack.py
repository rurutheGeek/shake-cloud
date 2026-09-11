import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
CLOUD = ROOT / 'cloud'
SPEC = importlib.util.spec_from_file_location('cloud_manage', CLOUD / 'manage.py')
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)

# tokenPattern in cloud/api/internal/accesskey/accesskey.go.
TOKEN = r'^sca_([a-z2-7]{20})\.([A-Za-z0-9_-]{43})$'


class BootstrapKeyTests(unittest.TestCase):
    def test_manage_py_mints_keys_the_api_accepts(self):
        # The API refuses to start on a malformed key file, so a drift here
        # would take the service down at the next deploy.
        self.assertIn('`' + TOKEN + '`', (CLOUD / 'api/internal/accesskey/accesskey.go').read_text())
        keys = {manage.bootstrap_key() for _ in range(50)}
        self.assertEqual(len(keys), 50)
        for key in keys:
            self.assertRegex(key, TOKEN)

    def test_init_keeps_existing_secrets_and_a_disabled_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env.example').write_text('STORAGE_ROOT=./data\n')
            with mock.patch.object(manage, 'ROOT', root), mock.patch.object(manage.os, 'chown') as chown:
                manage.init()
                password = (root / 'secrets/db_password').read_text()
                (root / 'secrets/bootstrap_admin_key').chmod(0o644)
                (root / 'secrets/bootstrap_admin_key').write_text('')
                manage.init()
            self.assertEqual((root / 'secrets/db_password').read_text(), password)
            self.assertEqual((root / 'secrets/bootstrap_admin_key').read_text(), '')
            self.assertTrue((root / 'data/postgres').is_dir())
            # PostgreSQL 18 cannot create its data directory inside a root-owned mount.
            chown.assert_called_with(root / 'data/postgres', 70, 70)


class ComposeTests(unittest.TestCase):
    services = yaml.safe_load((CLOUD / 'compose.yaml').read_text())['services']

    def test_every_image_is_pinned_to_a_digest(self):
        lock = json.loads((CLOUD / 'compose.lock.yaml').read_text())['services']
        pulled = {name for name, service in self.services.items() if 'build' not in service}
        self.assertEqual(pulled, set(lock))
        for entry in lock.values():
            self.assertIn('@sha256:', entry['image'])
        base_images = [line for line in (CLOUD / 'api/Dockerfile').read_text().splitlines() if line.startswith('FROM ')]
        self.assertTrue(base_images)
        for line in base_images:
            self.assertIn('@sha256:', line)

    def test_the_api_container_cannot_write_or_escalate(self):
        api = self.services['api']
        self.assertTrue(api['read_only'])
        self.assertIn('no-new-privileges:true', api['security_opt'])
        self.assertEqual(api['cap_drop'], ['ALL'])

    def test_secrets_are_files_not_environment_values(self):
        environment = self.services['api']['environment']
        for name, value in environment.items():
            if re.search('PASSWORD|SECRET|CREDENTIALS|KEY|TOKEN', name):
                self.assertTrue(name.endswith('_FILE') and str(value).startswith('/run/secrets/'), name)


class DeploymentTests(unittest.TestCase):
    def test_the_portal_url_matches_the_redirect_uri_authentik_registers(self):
        # Authentik matches the redirect URI strictly; the portal must build the
        # same origin, or every login fails after Authentik approves it.
        identity = yaml.safe_load((ROOT / 'platform/ansible/roles/identity/defaults/main.yml').read_text())
        cloud = yaml.safe_load((ROOT / 'platform/ansible/roles/cloud_api/defaults/main.yml').read_text())
        self.assertEqual(identity['identity_cloud_portal_url'].replace('identity_dns', 'dns'),
                         cloud['cloud_api_public_url'].replace('cloud_api_dns', 'dns'))
        self.assertTrue(cloud['cloud_api_public_url'].startswith('https://cloud.'))
        self.assertTrue(cloud['cloud_api_oidc_issuer'].startswith('https://auth.'))

    def test_the_oidc_secret_never_reaches_the_ansible_log(self):
        tasks = yaml.safe_load((ROOT / 'platform/ansible/roles/cloud_api/tasks/main.yml').read_text())
        # The slurp result and anything that reads its content. The issuer URL
        # and the "changed" flag are not secret.
        touching = [task for task in tasks
                    if task.get('register') == 'cloud_api_oidc' or 'cloud_api_oidc.content' in json.dumps(task)]
        self.assertEqual(len(touching), 3)
        for task in touching:
            self.assertTrue(task.get('no_log'), task['name'])

    def test_copied_content_has_no_literal_backslash_n(self):
        # A YAML single-quoted '{{ x }}\n' keeps the backslash instead of adding
        # a newline. That put a stray character at the end of site.json and the
        # API refused to start (2026-09-10).
        for role in ('cloud_api', 'tls_proxy', 'netbox', 'docs_site', 'identity'):
            path = ROOT / f'platform/ansible/roles/{role}/tasks/main.yml'
            for task in yaml.safe_load(path.read_text()):
                for module in ('ansible.builtin.copy', 'ansible.builtin.template'):
                    content = (task.get(module) or {}).get('content', '')
                    self.assertNotIn('\\n', content, f'{role}: {task["name"]}')

    def test_no_path_under_cloud_is_rejected_by_the_publication_check(self):
        # tools/check-publication.py rejects these path segments anywhere.
        forbidden = {'storage', 'library', 'backups', 'runtime', 'secrets', 'trust', '.terraform'}
        for path in CLOUD.rglob('*'):
            self.assertFalse(forbidden & set(path.relative_to(ROOT).parts), path)

    def test_the_site_playbook_deploys_the_cloud_after_identity(self):
        order = [entry['import_playbook'] for entry in yaml.safe_load((ROOT / 'platform/ansible/site.yml').read_text())]
        self.assertLess(order.index('identity.yml'), order.index('cloud.yml'))


if __name__ == '__main__':
    unittest.main()
