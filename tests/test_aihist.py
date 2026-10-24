"""Guard the aihist deployment.

aihist runs as a cloud service (platform/terraform/services/aihist). This file
guards the declaration, the entry point and the retirement of the old systemd
unit on media-01.
"""
from pathlib import Path
import re
import unittest

import yaml

from support import read, role_task, syntax_check
from test_tls_proxy import caddyfile, site_block

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'platform/terraform/services/aihist'
PLAYBOOK = ROOT / 'platform/ansible/media-aihist.yml'
DNS = yaml.safe_load(read(ROOT / 'platform/terraform/dns.yaml'))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.main = read(MODULE / 'main.tf')

    def test_the_image_is_pinned_by_tag_and_digest(self):
        self.assertRegex(self.main, r'image\s+= "ghcr\.io/ruruthegeek/aihist:\d+\.\d+\.\d+@sha256:[0-9a-f]{64}"')

    def test_the_data_lives_on_the_service_disk(self):
        self.assertIn('disk_mount_path = "/data"', self.main)
        self.assertRegex(self.main, r'disk_size_gib\s+= \d+')

    def test_the_token_comes_from_sops_as_a_secret(self):
        self.assertIn('secrets         = { AIHIST_TOKEN = var.aihist_token }', self.main)
        self.assertRegex(self.main, r'variable "aihist_token" \{[^}]*sensitive = true')
        self.assertTrue((ROOT / 'platform/sops/aihist.sops.yaml').exists())

    def test_the_state_key_is_its_own(self):
        self.assertIn('key                         = "shake-cloud/services/aihist/terraform.tfstate"',
                      read(MODULE / 'versions.tf'))


class EntryPointTests(unittest.TestCase):
    def test_the_entry_point_forwards_to_the_service_port(self):
        record = DNS['records']['aihist']
        port = re.search(r'port\s+= (\d+)', read(MODULE / 'main.tf')).group(1)
        self.assertEqual(record['host'], 'core-01')
        self.assertRegex(record['upstream'], rf'^192\.168\.10\.\d+:{port}$')
        self.assertTrue(record['auth'])
        # push はブラウザを持たないので /api だけを SSO の外に出す。
        self.assertEqual(record['auth_except'], ['/api/*'])

    def test_api_is_handled_before_the_forward_auth(self):
        rendered = caddyfile([{'key': 'aihist', 'value': DNS['records']['aihist']}])
        block = site_block(rendered, 'aihist')
        self.assertIn('handle /api/* {', block)
        self.assertLess(block.index('handle /api/*'), block.index('forward_auth https://'))


class RetireTests(unittest.TestCase):
    def setUp(self):
        self.tasks = yaml.safe_load(read(PLAYBOOK))[0]['tasks']

    def test_the_old_unit_is_stopped_and_removed(self):
        task = role_task(self.tasks, 'Stop and disable aihist')
        self.assertEqual(task['ansible.builtin.systemd']['state'], 'stopped')
        self.assertFalse(task['ansible.builtin.systemd']['enabled'])
        self.assertEqual(role_task(self.tasks, 'Remove the aihist unit')['ansible.builtin.file']['state'], 'absent')

    def test_the_conversation_originals_are_kept(self):
        self.assertNotIn('media_bulk_mount', read(PLAYBOOK).split('- name:', 1)[1])
        self.assertNotIn('/srv/media-bulk', read(PLAYBOOK).split('- name:', 1)[1])

    def test_the_playbook_parses(self):
        result = syntax_check(PLAYBOOK)
        self.assertEqual(result.returncode, 0,
                         f'{PLAYBOOK.name} did not parse:\n{result.stdout}\n{result.stderr}')


if __name__ == '__main__':
    unittest.main()
