"""Guard the CUPS print relay for the Canon TS8430 (services-01).

The printer is a LAN device; services-01 sits in front of it so LAN and VPN
clients can print without talking to the printer directly. The admin page must
never become reachable without authentication, so these are source-text and
YAML assertions plus an Ansible syntax check -- nothing here touches the host.
"""
import shutil
from pathlib import Path
import subprocess
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / 'platform/ansible/roles/cups'
PLAYBOOK = ROOT / 'platform/ansible/cups.yml'


def read(path):
    return path.read_text(encoding='utf-8')


def task_argv(task):
    return [str(part) for part in task['ansible.builtin.command']['argv']]


class RoleTests(unittest.TestCase):
    def setUp(self):
        self.defaults = yaml.safe_load(read(ROLE / 'defaults/main.yml'))
        self.tasks = yaml.safe_load(read(ROLE / 'tasks/main.yml'))
        self.conf = read(ROLE / 'templates/cupsd.conf.j2')
        self.names = [task['name'] for task in self.tasks]

    def task(self, name):
        return next(task for task in self.tasks if task['name'] == name)

    def test_the_packages_include_lpadmin_and_ipptool(self):
        packages = self.defaults['cups_packages']
        for package in ('cups', 'cups-client', 'cups-filters', 'cups-ipp-utils'):
            self.assertIn(package, packages)

    def test_the_driverless_print_queue_is_declared(self):
        self.assertEqual(self.defaults['cups_printer_name'], 'ts8430')
        self.assertEqual(self.defaults['cups_printer_uri'], 'ipp://192.168.10.9/ipp/print')
        argv = [str(part) for part in
                self.task('Create the print queue')['ansible.builtin.command']['argv']]
        self.assertIn('-m', argv)
        self.assertIn('everywhere', argv)
        self.assertIn('{{ cups_printer_uri }}', argv)

    def test_printing_is_allowed_only_from_lan_and_vpn(self):
        self.assertIn('Listen 0.0.0.0:631', self.conf)
        self.assertIn('Allow {{ cups_lan_cidr }}', self.conf)
        self.assertIn('Allow {{ cups_vpn_cidr }}', self.conf)

    def test_the_admin_pages_stay_on_localhost(self):
        admin = self.conf.split('<Location /admin>')[1].split('</Location>')[0]
        self.assertIn('Allow localhost', admin)
        self.assertIn('Require user @SYSTEM', admin)
        for path in ('/admin/conf', '/admin/log'):
            block = self.conf.split(f'<Location {path}>')[1].split('</Location>')[0]
            self.assertIn('Allow localhost', block, path)

    def test_the_socket_listens_on_the_lan(self):
        # Debian 13 activates cupsd through cups.socket (127.0.0.1:631 only).
        content = self.task('Listen on the LAN through the socket unit')[
            'ansible.builtin.copy']['content']
        self.assertIn('ListenStream=', content)
        self.assertIn('ListenStream=0.0.0.0:631', content)

    def test_a_stale_localhost_override_is_removed(self):
        task = self.task('Drop the old localhost-only service override')
        self.assertEqual(task['ansible.builtin.file']['state'], 'absent')
        self.assertIn('cups.service.d/10-listen.conf', task['ansible.builtin.file']['path'])

    def test_the_queue_is_reconciled_idempotently(self):
        for name in ('Look up the print queue', 'Check for a generated driverless PPD',
                     'Drop a raw queue so the driverless one can be rebuilt',
                     'Create the print queue', 'Fix a drifted queue URI',
                     'Require the queue to exist'):
            self.assertIn(name, self.names)
        lookup = self.task('Look up the print queue')
        self.assertFalse(lookup['changed_when'])
        self.assertFalse(lookup['failed_when'])
        drop = self.task('Drop a raw queue so the driverless one can be rebuilt')
        self.assertIn('lpadmin', task_argv(drop))
        self.assertIn('-x', task_argv(drop))

    def test_the_printer_moves_are_followed_over_mdns(self):
        self.assertIn('Discover the printer over mDNS', self.names)
        self.assertEqual(self.task('Discover the printer over mDNS')['when'],
                         'cups_direct_probe is failed')
        pick = self.task('Point the queue at the address the printer advertises')
        uri = str(pick['ansible.builtin.set_fact']['cups_printer_uri'])
        self.assertIn('item.split(";")[6]', uri)
        self.assertIn('/ipp/print', uri)
        self.assertIn('services-01', str(pick['when']))

    def test_the_proxy_hostname_is_accepted(self):
        # Caddy は元の Host を保って 127.0.0.1:631 へ中継する。CUPS は未知の
        # Host を 400 で拒否するので、dns.yaml と同じ名前を ServerAlias に置く。
        self.assertIn('ServerAlias {{ cups_server_alias }}', self.conf)
        dns = yaml.safe_load((ROOT / 'platform/terraform/dns.yaml').read_text())
        self.assertTrue(dns['records']['cups']['upstream'].endswith(':631'))
        self.assertEqual(f"cups.{dns['zone']}", self.defaults['cups_server_alias'])

    def test_a_sleeping_printer_fails_with_a_clear_message(self):
        task = self.task('Make sure the printer is reachable before building the queue')
        self.assertIn('電源', task['ansible.builtin.fail']['msg'])

    def test_a_config_change_restarts_cups(self):
        template = self.task('Write the CUPS configuration')
        self.assertIn('Restart cups', template['notify'])

    def test_the_playbook_targets_services_01(self):
        play = yaml.safe_load(read(PLAYBOOK))[0]
        self.assertEqual(play['hosts'], 'netbox_bootstrap')
        self.assertTrue(play['become'])
        self.assertIn('cups', play['roles'])


class SyntaxTests(unittest.TestCase):
    def test_the_playbook_parses(self):
        candidate = Path(sys.executable).with_name('ansible-playbook')
        playbook = str(candidate) if candidate.exists() else shutil.which('ansible-playbook')
        if not playbook:
            self.skipTest('ansible-playbook is not installed')
        result = subprocess.run([playbook, '--syntax-check', '-i', 'localhost,', str(PLAYBOOK)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
