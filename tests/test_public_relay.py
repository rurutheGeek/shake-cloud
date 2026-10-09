"""Check the public relay's declaration without touching the host.

The relay is the one node the internet can reach directly, so its settings are
worth reading twice: sshd must not take passwords, the firewall opens SSH only
on the tailnet, and nothing may forward to the stopped Minecraft.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from support import read, syntax_check  # noqa: E402

import yaml  # noqa: E402

ROLE = ROOT / 'platform/ansible/roles/public_relay'
PLAYBOOK = ROOT / 'platform/ansible/public-relay.yml'
INVENTORY = ROOT / 'platform/ansible/outpost.ini'


def tasks():
    return yaml.safe_load(read(ROLE / 'tasks/main.yml'))


def task_named(fragment):
    """Find a task by name, looking inside blocks for nested tasks."""
    def walk(items):
        for task in items:
            if fragment in task.get('name', ''):
                return task
            if 'block' in task:
                found = walk(task['block'])
                if found:
                    return found
        return None
    return walk(tasks())


class PlaybookTest(unittest.TestCase):
    def test_it_parses(self):
        result = syntax_check(PLAYBOOK)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_it_targets_only_the_relay_group(self):
        play = yaml.safe_load(read(PLAYBOOK))[0]
        self.assertEqual(play['hosts'], 'relay')

    def test_the_inventory_keeps_the_monitor_target_separate(self):
        text = read(INVENTORY)
        outpost = text.split('[outpost]')[1].split('[')[0]
        relay = text.split('[relay]')[1]
        self.assertIn('tarakoserver', outpost)
        self.assertNotIn('negitoroserver', outpost)
        self.assertIn('negitoroserver', relay)


class HardeningTest(unittest.TestCase):
    def test_sshd_refuses_passwords_ahead_of_cloud_init(self):
        task = task_named('Harden sshd')
        self.assertIn('PasswordAuthentication no', task['ansible.builtin.copy']['content'])
        self.assertTrue(task['ansible.builtin.copy']['dest'].endswith('/10-managed.conf'))

    def test_the_firewall_allows_ssh_only_on_the_tailnet(self):
        task = task_named('Allow SSH only on the tailnet interface')
        self.assertIn('ufw allow in on {{ public_relay_ssh_interface }}', task['ansible.builtin.command'])

    def test_the_firewall_is_rebuilt_when_a_wide_rule_is_left(self):
        task = task_named('Rebuild the firewall')
        self.assertIn('on tailscale0', task['when'])
        self.assertIn('select', task['when'])
        self.assertIn('public_relay_cloudflare_ranges', task['when'])

    def test_the_lan_route_is_not_accepted(self):
        task = task_named('Do not accept routes')
        self.assertIn('accept-routes=false', task['ansible.builtin.command'])


class CloudflareTest(unittest.TestCase):
    def test_https_is_open_only_to_cloudflare(self):
        task = task_named('Allow HTTPS only from Cloudflare')
        self.assertIn('public_relay_cloudflare_ranges', task['loop'])
        self.assertIn('to any port {{ public_relay_https_port }}',
                      task['ansible.builtin.command'])

    def test_the_old_blanket_https_rule_is_gone(self):
        def all_names(items):
            names = []
            for task in items:
                names.append(task.get('name', ''))
                names.extend(all_names(task.get('block', [])))
            return names

        self.assertFalse(any('HTTPS from anywhere' in name for name in all_names(tasks())))

    def test_the_declared_ranges_look_like_cloudflare(self):
        defaults = yaml.safe_load(read(ROLE / 'defaults/main.yml'))
        self.assertEqual(len(defaults['public_relay_cloudflare_ipv4']), 15)
        self.assertEqual(len(defaults['public_relay_cloudflare_ipv6']), 7)
        self.assertIn('173.245.48.0/20', defaults['public_relay_cloudflare_ipv4'])
        self.assertIn('2400:cb00::/32', defaults['public_relay_cloudflare_ipv6'])

    def test_a_moved_range_stops_the_run(self):
        task = task_named("Refuse to run when Cloudflare's ranges moved")
        self.assertTrue(task)
        self.assertIn('public_relay_cloudflare_ipv4',
                      task['ansible.builtin.assert']['that'][0])


class RelayTest(unittest.TestCase):
    def test_https_goes_to_web01_with_the_proxy_protocol(self):
        template = read(ROLE / 'templates/stream_proxy.conf.j2')
        self.assertIn('proxy_pass {{ public_relay_web_upstream }}:{{ public_relay_https_port }}',
                      template)
        self.assertIn('proxy_protocol on;', template)

    def test_http_goes_to_web01(self):
        template = read(ROLE / 'templates/sslh.default.j2')
        self.assertIn('--http {{ public_relay_web_upstream }}:{{ public_relay_http_port }}',
                      template)

    def test_minecraft_is_not_forwarded(self):
        template = read(ROLE / 'templates/sslh.default.j2')
        self.assertNotIn('anyprot', template)
        self.assertNotIn('25565', template)

    def test_the_upstream_is_web01(self):
        defaults = yaml.safe_load(read(ROLE / 'defaults/main.yml'))
        self.assertEqual(defaults['public_relay_web_upstream'], '100.75.249.112')


if __name__ == '__main__':
    unittest.main()
