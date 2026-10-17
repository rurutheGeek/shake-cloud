"""Guard the touch panel on tarakoserver (docs/development/M02-touch-panel.md).

The C source only builds on the Pi, so these tests check what CI can see:
the configuration names every query the program reads, the program reads
only from this machine, and the role pins LVGL and keeps writes off the SD
card.
"""
import json
import re
import unittest
from pathlib import Path

import yaml

from support import role_task, syntax_check

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/touch-panel'
ROLE = ROOT / 'platform/ansible/roles/touch_panel'
PANEL = json.loads((STACK / 'panel.json').read_text(encoding='utf-8'))
DEFAULTS = yaml.safe_load((ROLE / 'defaults/main.yml').read_text(encoding='utf-8'))
TASKS = yaml.safe_load((ROLE / 'tasks/main.yml').read_text(encoding='utf-8'))
CONFIG_C = (STACK / 'src/config.c').read_text(encoding='utf-8')


class PanelConfigTests(unittest.TestCase):
    def test_every_query_the_program_reads_is_configured(self):
        wanted = set(re.findall(r'Q\(q_\w+, "(\w+)"\)', CONFIG_C))
        self.assertTrue(wanted)
        self.assertEqual(wanted, set(PANEL['queries']))
        for key, expr in PANEL['queries'].items():
            self.assertTrue(expr.strip(), key)

    def test_data_is_read_from_this_machine(self):
        self.assertTrue(PANEL['prometheus'].startswith('http://127.0.0.1:'))
        self.assertTrue(PANEL['alertmanager'].startswith('http://127.0.0.1:'))

    def test_settings_live_on_the_data_disk(self):
        self.assertTrue(PANEL['settings_file'].startswith(DEFAULTS['touch_panel_state_dir'] + '/'))
        self.assertTrue(DEFAULTS['touch_panel_state_dir'].startswith('/srv/'))


class RoleTests(unittest.TestCase):
    def test_lvgl_is_pinned_by_version_and_checksum(self):
        self.assertRegex(DEFAULTS['touch_panel_lvgl_version'], r'^\d+\.\d+\.\d+$')
        self.assertRegex(DEFAULTS['touch_panel_lvgl_sha256'], r'^[0-9a-f]{64}$')
        item = role_task(TASKS, 'Download LVGL')
        self.assertIn('touch_panel_lvgl_sha256', item['ansible.builtin.get_url']['checksum'])

    def test_the_login_prompt_is_hidden(self):
        item = role_task(TASKS, 'Hide the login prompt on the screen')
        self.assertEqual(item['ansible.builtin.systemd']['name'], 'getty@tty1')
        self.assertTrue(item['ansible.builtin.systemd']['masked'])

    def test_the_service_restarts_and_writes_only_to_the_data_disk(self):
        unit = (ROLE / 'templates/touch-panel.service.j2').read_text(encoding='utf-8')
        self.assertIn('Restart=always', unit)
        self.assertIn('WatchdogSec=', unit)
        self.assertIn('ProtectSystem=strict', unit)
        self.assertIn('ReadWritePaths=-{{ touch_panel_state_dir }}', unit)

    def test_the_playbook_parses(self):
        playbook = ROOT / 'platform/ansible/touch-panel.yml'
        result = syntax_check(playbook)
        self.assertEqual(result.returncode, 0, f'{playbook.name} did not parse:\n{result.stdout}\n{result.stderr}')


if __name__ == '__main__':
    unittest.main()
