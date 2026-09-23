"""Guard the storage lifespan settings: journald, noatime and Docker logs.

These settings are invisible until the SSD wears out or a log fills a disk.
The role must stay safe to re-run: it only adds noatime when it is missing,
and it never rewrites the root line blindly. The Docker restart is what makes
the log limits real for newly created containers.
"""
import unittest
from pathlib import Path

import yaml

from support import read, role_task, syntax_check

ROOT = Path(__file__).resolve().parents[1]
ANSIBLE = ROOT / 'platform/ansible'
ROLE = ANSIBLE / 'roles/storage_health'
DEFAULTS = yaml.safe_load((ROLE / 'defaults/main.yml').read_text(encoding='utf-8'))
TASKS = yaml.safe_load((ROLE / 'tasks/main.yml').read_text(encoding='utf-8'))
HANDLERS = yaml.safe_load((ROLE / 'handlers/main.yml').read_text(encoding='utf-8'))
PLAYBOOK = ANSIBLE / 'storage-health.yml'


class JournaldTests(unittest.TestCase):
    def test_it_caps_the_journal(self):
        self.assertEqual(DEFAULTS['storage_health_journald_max_use'], '200M')
        item = role_task(TASKS, 'Cap the systemd journal')
        self.assertEqual(item['ansible.builtin.copy']['dest'],
                         '/etc/systemd/journald.conf.d/20-storage-health.conf')
        self.assertIn('SystemMaxUse={{ storage_health_journald_max_use }}',
                      item['ansible.builtin.copy']['content'])
        self.assertEqual(item['notify'], 'Restart systemd-journald')

    def test_the_journald_handler_restarts_the_service(self):
        self.assertEqual(role_task(HANDLERS, 'Restart systemd-journald')['ansible.builtin.systemd']['name'],
                         'systemd-journald')


class NoatimeTests(unittest.TestCase):
    def test_it_reads_the_current_mount_options(self):
        item = role_task(TASKS, "Read the root filesystem's mount options")
        self.assertEqual(item['ansible.builtin.command']['argv'], ['findmnt', '-n', '-o', 'OPTIONS', '/'])

    def test_it_only_adds_noatime_when_missing(self):
        item = role_task(TASKS, 'Add noatime to the root filesystem in fstab')
        self.assertIn('(?m)', item['ansible.builtin.replace']['regexp'])
        self.assertIn('(?!noatime)', item['ansible.builtin.replace']['regexp'])
        self.assertIn("'noatime' not in storage_health_root_options.stdout", item['when'])

    def test_it_remounts_only_after_the_fstab_change(self):
        item = role_task(TASKS, 'Remount the root filesystem with noatime')
        self.assertEqual(item['ansible.builtin.command']['argv'], ['mount', '-o', 'remount', '/'])
        self.assertIn('storage_health_fstab is changed', item['when'])


class DockerLogTests(unittest.TestCase):
    def test_it_caps_the_container_logs(self):
        item = role_task(TASKS, 'Cap the container logs')
        content = item['ansible.builtin.copy']['content']
        self.assertIn('"log-driver": "json-file"', content)
        self.assertIn('storage_health_docker_log_max_size', content)
        self.assertIn('storage_health_docker_log_max_file', content)
        self.assertEqual(item['notify'], 'Restart Docker to apply the log limits')

    def test_it_skips_hosts_without_docker(self):
        item = role_task(TASKS, 'Cap the container logs')
        self.assertIn('storage_health_docker.stat.exists', item['when'])

    def test_the_restart_can_be_deferred(self):
        # サービスVMでは次回の配備に任せられるようにしてある。
        item = role_task(HANDLERS, 'Restart Docker to apply the log limits')
        self.assertIn('storage_health_restart_docker | bool', item['when'])

    def test_the_defaults_match_the_documented_values(self):
        self.assertEqual(DEFAULTS['storage_health_docker_log_max_size'], '10m')
        self.assertEqual(DEFAULTS['storage_health_docker_log_max_file'], '3')


class PlaybookTests(unittest.TestCase):
    def test_it_targets_the_host_and_the_service_vms(self):
        plays = yaml.safe_load(read(PLAYBOOK))
        hosts = set(plays[0]['hosts'].split(':'))
        for group in ('pve', 'monitoring', 'media', 'identity_provider',
                      'cloud_control', 'storage'):
            self.assertIn(group, hosts)
        self.assertEqual(plays[0]['roles'], ['storage_health'])

    def test_the_playbook_parses(self):
        result = syntax_check(PLAYBOOK)
        self.assertEqual(result.returncode, 0,
                         f'{PLAYBOOK.name} did not parse:\n{result.stdout}\n{result.stderr}')


if __name__ == '__main__':
    unittest.main()
