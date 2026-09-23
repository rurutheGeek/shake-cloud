"""Guard the Proxmox host metrics: I/O, filesystem and SMART.

The 6TB HDD and the NVMe are only visible from the host's node_exporter.
The Debian package ships the SMART/NVMe textfile timers; if the role stops
enabling them, the storage dashboard and the SMART alerts go quiet without
any error. These are source-text and YAML assertions; only
`ansible-playbook --syntax-check` runs.
"""
import unittest
from pathlib import Path

import yaml

from support import read, role_task, syntax_check

ROOT = Path(__file__).resolve().parents[1]
ANSIBLE = ROOT / 'platform/ansible'
ROLE = ANSIBLE / 'roles/pve_node_exporter'
DEFAULTS = yaml.safe_load((ROLE / 'defaults/main.yml').read_text(encoding='utf-8'))
TASKS = yaml.safe_load((ROLE / 'tasks/main.yml').read_text(encoding='utf-8'))
PLAYBOOK = ANSIBLE / 'pve-node-exporter.yml'


class RoleTests(unittest.TestCase):
    def test_it_installs_the_exporter_and_smartmontools(self):
        packages = DEFAULTS['pve_node_exporter_packages']
        self.assertIn('prometheus-node-exporter', packages)
        self.assertIn('smartmontools', packages)

    def test_it_enables_the_textfile_timers(self):
        timers = DEFAULTS['pve_node_exporter_timers']
        self.assertIn('prometheus-node-exporter-smartmon.timer', timers)
        self.assertIn('prometheus-node-exporter-nvme.timer', timers)

    def test_node_exporter_is_enabled_and_started(self):
        item = role_task(TASKS, 'Enable and start node_exporter')
        self.assertEqual(item['ansible.builtin.systemd']['name'], 'prometheus-node-exporter')
        self.assertTrue(item['ansible.builtin.systemd']['enabled'])
        self.assertEqual(item['ansible.builtin.systemd']['state'], 'started')

    def test_the_timers_are_looped_over(self):
        item = role_task(TASKS, 'Enable the textfile collector timers')
        self.assertEqual(item['ansible.builtin.systemd']['name'], '{{ item }}')
        self.assertEqual(item['loop'], '{{ pve_node_exporter_timers }}')

    def test_it_collects_once_when_a_textfile_is_missing(self):
        # timerの初回は15分後。ダッシュボードを待たせない。
        smart = role_task(TASKS, 'Collect SMART once when the textfile is missing')
        nvme = role_task(TASKS, 'Collect NVMe once when the textfile is missing')
        self.assertIn('not pve_node_exporter_smartmon.stat.exists', smart['when'])
        self.assertIn('not pve_node_exporter_nvme.stat.exists', nvme['when'])

    def test_the_playbook_runs_the_role_on_the_pve_host(self):
        plays = yaml.safe_load(read(PLAYBOOK))
        self.assertEqual(plays[0]['hosts'], 'pve')
        self.assertTrue(plays[0]['become'])
        self.assertEqual(plays[0]['roles'], ['pve_node_exporter'])


class SyntaxTests(unittest.TestCase):
    def test_the_playbook_parses(self):
        result = syntax_check(PLAYBOOK, 'platform/ansible/pve.ini')
        self.assertEqual(result.returncode, 0,
                         f'{PLAYBOOK.name} did not parse:\n{result.stdout}\n{result.stderr}')


if __name__ == '__main__':
    unittest.main()
