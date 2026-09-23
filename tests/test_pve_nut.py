"""Guard the UPS shutdown path: the order from power.md must survive edits.

The Proxmox host is the only machine that can stop the cluster on low battery.
A template that stops the control plane first, or that never stops the host,
would look fine until the day the power actually fails.
"""
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / 'platform/ansible/roles/pve_nut'
DEFAULTS = yaml.safe_load((ROLE / 'defaults/main.yml').read_text(encoding='utf-8'))


def load_task_names():
    tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text(encoding='utf-8'))
    return [task.get('name', '') for task in tasks]


class UpsmonTests(unittest.TestCase):
    def test_the_role_starts_upsmon_after_the_ups_answers(self):
        names = load_task_names()
        self.assertIn('Enable and start upsmon', names)
        self.assertLess(names.index('Wait for the UPS to answer'),
                        names.index('Enable and start upsmon'))

    def test_upsmon_watches_the_local_ups_as_primary(self):
        text = (ROLE / 'templates/upsmon.conf.j2').read_text(encoding='utf-8')
        self.assertIn('MONITOR {{ pve_nut_ups_name }}@localhost 1 {{ pve_nut_upsmon_user }}', text)
        self.assertIn(' primary', text)
        self.assertIn('MINSUPPLIES 1', text)
        self.assertIn('SHUTDOWNCMD "{{ pve_nut_shutdown_script }}"', text)

    def test_the_monitor_user_stays_read_only(self):
        text = (ROLE / 'templates/upsd.users.j2').read_text(encoding='utf-8')
        monitor, upsmon = text.split('[{{ pve_nut_upsmon_user }}]')
        self.assertIn('[{{ pve_nut_monitor_user }}]', monitor)
        self.assertNotIn('upsmon primary', monitor)
        self.assertIn('upsmon primary', upsmon)


class ShutdownScriptTests(unittest.TestCase):
    def script(self):
        return (ROLE / 'templates/pve-ups-shutdown.sh.j2').read_text(encoding='utf-8')

    def test_workers_stop_before_the_control_plane(self):
        text = self.script()
        self.assertLess(text.index('stop_group k8s-worker'), text.index('stop_group k8s-cp'))

    def test_the_host_stops_last(self):
        text = self.script()
        self.assertGreater(text.rindex('shutdown -h now'), text.rindex('stop_group k8s-cp'))

    def test_the_script_can_be_dry_run(self):
        text = self.script()
        self.assertIn('PVE_UPS_SHUTDOWN_DRY_RUN', text)
        # 実停止（shutdown -h now）は dry-run の分岐より後ろにだけ置く。
        self.assertLess(text.index('exit 0'), text.rindex('shutdown -h now'))

    def test_the_grace_and_timeout_are_declared(self):
        script = self.script()
        self.assertIn('GRACE={{ pve_nut_shutdown_grace_seconds }}', script)
        self.assertIn('TIMEOUT={{ pve_nut_k8s_stop_timeout }}', script)
        self.assertGreaterEqual(DEFAULTS['pve_nut_shutdown_grace_seconds'], 0)
        self.assertGreater(DEFAULTS['pve_nut_k8s_stop_timeout'], 0)
        self.assertTrue(DEFAULTS['pve_nut_shutdown_script'].startswith('/usr/local/'))


if __name__ == '__main__':
    unittest.main()
