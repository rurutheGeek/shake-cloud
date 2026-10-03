"""Static checks for the AWX NetBox inventory integration."""

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIGURE = ROOT / 'platform/awx/configure.yml'


class AwxConfigureTests(unittest.TestCase):
    def setUp(self):
        self.text = CONFIGURE.read_text(encoding='utf-8')
        self.tasks = yaml.safe_load(self.text)[0]['tasks']

    def task(self, name):
        return next(task for task in self.tasks if task.get('name') == name)

    def test_netbox_credential_is_injected_by_a_dedicated_type(self):
        credential_type = self.task('Create NetBox credential type')
        injectors = credential_type['awx.awx.credential_type']['injectors']['env']
        self.assertIn('NETBOX_API', injectors)
        self.assertIn('NETBOX_TOKEN', injectors)
        stored = self.task('Store NetBox read credential')
        self.assertIn('NetBox inventory API',
                      stored['awx.awx.credential']['credential_type'])
        self.assertTrue(stored['no_log'])

    def test_the_inventory_source_uses_the_checked_in_entrypoint(self):
        source = self.task('Add SCM inventory source')['awx.awx.inventory_source']
        self.assertEqual(source['source_path'], 'ansible/inventory.netbox.yml')
        self.assertEqual(source['update_cache_timeout'], 0)

    def test_the_retired_cloud_inventory_is_not_referenced(self):
        self.assertNotIn('inventory.cloud.py', self.text)
        self.assertNotIn('cloud-inventory.yml', self.text)
        self.assertNotIn('SHAKECLOUD_ACCESS_KEY', self.text)

    def test_deployment_job_uses_the_netbox_inventory(self):
        job = self.task('Register deployment job')['awx.awx.job_template']
        self.assertEqual(job['playbook'], 'ansible/deploy.yml')
        self.assertEqual(job['inventory'], 'Media hosts from NetBox')


if __name__ == '__main__':
    unittest.main()
