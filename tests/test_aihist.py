"""Guard the aihist deployment on media-01.

The program lives in the private repository rurutheGeek/aihist and is pulled
from a pinned GitHub release by the controller's gh. This file guards what
stays here: the pin, the play, the systemd unit and the entry point.
"""
from pathlib import Path
import unittest

import yaml

from support import read, role_task, syntax_check

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/aihist'
PLAYBOOK = ROOT / 'platform/ansible/media-aihist.yml'
GROUP_VARS = ROOT / 'platform/ansible/group_vars/media.yml'
DNS = yaml.safe_load(read(ROOT / 'platform/terraform/dns.yaml'))


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tasks = yaml.safe_load(read(PLAYBOOK))[0]['tasks']

    def test_the_release_is_pinned_in_group_vars(self):
        group = yaml.safe_load(read(GROUP_VARS))
        self.assertRegex(group['aihist_version'], r'^\d+\.\d+\.\d+$')
        self.assertIn('aihist-linux-amd64', group['aihist_sha256s'])
        for name, digest in group['aihist_sha256s'].items():
            self.assertRegex(name, r'^aihist-(linux|darwin|windows)-(amd64|arm64)(\.exe)?$')
            self.assertRegex(digest, r'^[0-9a-f]{64}$')

    def test_the_binary_is_checked_against_the_pin_before_install(self):
        names = [task['name'] for task in self.tasks]
        self.assertLess(names.index('Refuse an aihist binary that does not match the pin'),
                        names.index('Install aihist'))
        task = role_task(self.tasks, 'Check the downloaded aihist')
        self.assertEqual(task['ansible.builtin.stat']['checksum_algorithm'], 'sha256')
        self.assertIn('aihist_sha256s', task['loop'])


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.play = yaml.safe_load(read(PLAYBOOK))[0]
        self.tasks = self.play['tasks']

    def test_the_data_lives_on_the_bulk_disk(self):
        self.assertEqual(self.play['vars']['aihist_data_dir'], '{{ media_bulk_mount }}/aihist')

    def test_the_token_is_read_from_sops_without_logging(self):
        task = role_task(self.tasks, 'Read the aihist token')
        self.assertTrue(task['no_log'])
        self.assertIn('aihist.sops.yaml', str(task['ansible.builtin.command']['argv']))
        env = role_task(self.tasks, 'Write the aihist environment')
        self.assertTrue(env['no_log'])
        self.assertEqual(env['ansible.builtin.copy']['mode'], '0440')

    def test_the_port_matches_the_entry_point(self):
        record = DNS['records']['aihist']
        self.assertEqual(record['upstream'], f"127.0.0.1:{self.play['vars']['aihist_port']}")
        self.assertTrue(record['auth'])
        # push はブラウザを持たないので /api だけを SSO の外に出す。
        self.assertEqual(record['auth_except'], ['/api/*'])


class SystemdUnitTests(unittest.TestCase):
    def test_the_unit_listens_on_loopback_and_writes_only_its_data(self):
        unit = read(STACK / 'aihist.service.j2')
        self.assertIn('-addr 127.0.0.1:{{ aihist_port }}', unit)
        self.assertIn('ProtectSystem=strict', unit)
        self.assertIn('ReadWritePaths={{ aihist_data_dir }}', unit)
        self.assertIn('RequiresMountsFor={{ aihist_data_dir }}', unit)
        self.assertIn('User=aihist', unit)
        self.assertIn('-bin {{ aihist_dir }}/bin', unit)


class SyntaxTests(unittest.TestCase):
    def test_the_playbook_parses(self):
        result = syntax_check(PLAYBOOK)
        self.assertEqual(result.returncode, 0,
                         f'{PLAYBOOK.name} did not parse:\n{result.stdout}\n{result.stderr}')


if __name__ == '__main__':
    unittest.main()
