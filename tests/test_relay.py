"""Guard the outside relay (negitoroserver): what it forwards and what it accepts.

The relay is the only host reachable from the internet. Its firewall used to be
set by hand; these checks keep the declared ufw rules in place: SSH only over
the tailnet, 80/443 only from Cloudflare. Only `--syntax-check` runs.
"""
import ipaddress
from pathlib import Path
import unittest

import yaml

from support import read, role_task, syntax_check

ROOT = Path(__file__).resolve().parents[1]
ANSIBLE = ROOT / 'platform/ansible'
ROLE = ANSIBLE / 'roles/relay'
DEFAULTS = yaml.safe_load(read(ROLE / 'defaults/main.yml'))
TASKS = yaml.safe_load(read(ROLE / 'tasks/main.yml'))
SCRIPT = read(ROLE / 'templates/relay-firewall.sh.j2')


class FirewallTests(unittest.TestCase):
    def test_the_ranges_are_cloudflare_networks(self):
        ranges = [ipaddress.ip_network(r) for r in DEFAULTS['relay_cloudflare_ranges']]
        self.assertIn(ipaddress.ip_network('173.245.48.0/20'), ranges)
        self.assertIn(ipaddress.ip_network('2606:4700::/32'), ranges)
        self.assertEqual(len(ranges), len(set(ranges)))

    def test_web_ports_only_from_cloudflare_and_ssh_only_on_the_tailnet(self):
        self.assertIn('ufw allow from {{ range }} to any port 80,443 proto tcp', SCRIPT)
        self.assertIn('ufw allow in on tailscale0 to any port 22 proto tcp', SCRIPT)
        self.assertIn('ufw default deny incoming', SCRIPT)
        self.assertNotIn('ufw allow 80', SCRIPT)

    def test_rerunning_changes_nothing_when_the_rules_match(self):
        self.assertIn('OK: ufw rules match', SCRIPT)
        task = role_task(TASKS, 'Make the ufw rules match')
        self.assertEqual(task['changed_when'], "'CHANGED' in relay_firewall.stdout")


class SyntaxTests(unittest.TestCase):
    def test_the_playbook_parses(self):
        result = syntax_check(ANSIBLE / 'relay.yml')
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
