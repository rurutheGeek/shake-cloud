"""Static checks for the AWX registration (platform/awx/configure.yml)."""

import json
from pathlib import Path
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIGURE = ROOT / 'platform/awx/configure.yml'



class AwxConfigureTests(unittest.TestCase):
    def setUp(self):
        self.text = CONFIGURE.read_text(encoding='utf-8')
        self.plays = yaml.safe_load(self.text)
        self.tasks = [task for play in self.plays for task in play['tasks']]

    def task(self, name):
        return next(task for task in self.tasks if task.get('name') == name)

    def test_secrets_are_read_before_the_play_that_uses_them(self):
        # module_defaults are templated for every task of their play, so the
        # password must come from an earlier play.
        self.assertNotIn('module_defaults', self.plays[0])
        self.assertIn('module_defaults', self.plays[1])
        self.assertTrue(self.task('Read the AWX admin password and the job key')['no_log'])
        self.assertTrue(self.task('Store the credentials')['no_log'])

    def test_netbox_credential_is_injected_by_a_dedicated_type(self):
        netbox = self.task('Define the NetBox credential type')['awx.awx.credential_type']
        self.assertEqual(set(netbox['injectors']['env']), {'NETBOX_API', 'NETBOX_TOKEN'})

    def test_host_keys_stay_checked(self):
        known = self.task('Define the known hosts credential type')['awx.awx.credential_type']
        self.assertIn('UserKnownHostsFile', known['injectors']['extra_vars']['ansible_ssh_common_args'])
        self.assertNotIn('StrictHostKeyChecking', self.text)

    def test_the_inventory_source_uses_the_checked_in_entrypoint(self):
        source = self.task('Read the hosts from NetBox')['awx.awx.inventory_source']
        self.assertEqual(source['source_path'], 'platform/ansible/inventory.netbox.yml')
        self.assertTrue((ROOT / source['source_path']).exists())

    def test_the_retired_cloud_inventory_is_not_referenced(self):
        self.assertNotIn('inventory.cloud.py', self.text)
        self.assertNotIn('cloud-inventory.yml', self.text)
        self.assertNotIn('SHAKECLOUD_ACCESS_KEY', self.text)


class AwxCatalogTests(unittest.TestCase):
    def setUp(self):
        result = subprocess.run(['python3', str(ROOT / 'tools/awx-catalog.py'), '--json'],
                                capture_output=True, text=True, check=True)
        self.items = json.loads(result.stdout)

    def test_every_playbook_is_listed(self):
        listed = {item['file'] for item in self.items}
        for path in (ROOT / 'platform/ansible').glob('*.yml'):
            plays = yaml.safe_load(path.read_text())
            if isinstance(plays, list) and any(isinstance(play, dict) and 'hosts' in play for play in plays):
                self.assertIn(path.name, listed)

    def test_every_listed_playbook_has_a_title(self):
        for item in self.items:
            if not item['local_only']:
                self.assertNotEqual(item['title'], item['name'], item['file'])

    def test_infrastructure_defaults_to_check(self):
        by_file = {item['file']: item for item in self.items}
        for name in ('pve-users.yml', 'kubernetes.yml', 'identity.yml', 'site.yml'):
            self.assertEqual(by_file[name]['job_type'], 'check', name)


if __name__ == '__main__':
    unittest.main()
