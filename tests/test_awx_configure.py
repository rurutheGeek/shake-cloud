"""Static checks for the opt-in AWX cloud inventory integration."""

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

    def test_cloud_integration_is_opt_in(self):
        cloud_tasks = [task for task in self.tasks
                       if 'awx_enable_cloud_inventory' in str(task)]
        self.assertGreaterEqual(len(cloud_tasks), 6)
        for task in cloud_tasks:
            self.assertIn('awx_enable_cloud_inventory', str(task.get('when', task)))

    def test_cloud_key_is_injected_by_a_dedicated_credential(self):
        credential_type = self.task('Register shake-cloud inventory credential type')
        injectors = credential_type['awx.awx.credential_type']['injectors']['env']
        self.assertIn('SHAKECLOUD_ACCESS_KEY', injectors)
        self.assertIn('SHAKECLOUD_ENDPOINT', injectors)
        stored = self.task('Store shake-cloud inventory credential')
        self.assertIn('Shake-cloud inventory API',
                      stored['awx.awx.credential']['credential_type'])
        self.assertTrue(stored['no_log'])

    def test_cloud_source_and_media_job_use_the_checked_in_entrypoints(self):
        source = self.task('Add the read-only cloud inventory source')['awx.awx.inventory_source']
        self.assertEqual(source['source_path'], 'ansible/inventory.cloud.py')
        self.assertEqual(source['update_cache_timeout'], 0)
        job = self.task('Register the isolated media deployment job')['awx.awx.job_template']
        self.assertEqual(job['playbook'], 'ansible/media.yml')
        self.assertTrue(job['ask_limit_on_launch'])
        self.assertFalse(job['allow_simultaneous'])

    def test_existing_netbox_job_remains_present(self):
        self.assertEqual(self.task('Register deployment job')['awx.awx.job_template']['playbook'],
                         'ansible/deploy.yml')


if __name__ == '__main__':
    unittest.main()
