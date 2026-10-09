"""Check the home server's egress guard without touching the host.

The guard is what keeps a compromised shakeserver from walking the LAN; the
rules that let replies and the gateway through are the difference between a
guard and an outage, so they are worth reading twice.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from support import read, syntax_check  # noqa: E402

import yaml  # noqa: E402

ROLE = ROOT / 'platform/ansible/roles/home_egress'
PLAYBOOK = ROOT / 'platform/ansible/home-egress.yml'
INVENTORY = ROOT / 'platform/ansible/outpost.ini'


class PlaybookTest(unittest.TestCase):
    def test_it_parses(self):
        result = syntax_check(PLAYBOOK)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_it_targets_the_home_group(self):
        play = yaml.safe_load(read(PLAYBOOK))[0]
        self.assertEqual(play['hosts'], 'home')

    def test_the_home_group_is_tarakoserver_free(self):
        text = read(INVENTORY)
        home = text.split('[home]')[1]
        self.assertIn('shakeserver', home)
        self.assertNotIn('tarakoserver', home)


class GuardTest(unittest.TestCase):
    def test_xrdp_is_stopped_and_disabled(self):
        tasks = yaml.safe_load(read(ROLE / 'tasks/main.yml'))
        task = [t for t in tasks if 'xrdp' in t.get('name', '')][0]
        self.assertEqual(task['loop'], ['xrdp', 'xrdp-sesman'])
        self.assertFalse(task['ansible.builtin.systemd']['enabled'])
        self.assertEqual(task['ansible.builtin.systemd']['state'], 'stopped')

    def test_the_guard_is_loaded_and_kept_on(self):
        tasks = yaml.safe_load(read(ROLE / 'tasks/main.yml'))
        names = [t.get('name', '') for t in tasks]
        self.assertTrue(any('Install the egress guard' in name for name in names))
        self.assertTrue(any('Enable the egress guard' in name for name in names))
        handlers = yaml.safe_load(read(ROLE / 'handlers/main.yml'))
        self.assertEqual([h['ansible.builtin.command'] for h in handlers],
                         ['nft delete table inet homeguard', 'nft -f /etc/nftables.conf'])

    def test_the_template_lets_replies_and_the_gateway_through(self):
        template = read(ROLE / 'templates/nftables.conf.j2')
        self.assertIn('ct state established,related accept', template)
        self.assertIn('ip daddr {{ home_egress_gateway }} accept', template)
        self.assertIn('ip daddr {{ home_egress_lan }} drop', template)
        # ゲートウェイの許可が LAN の drop より先に来ていること。
        self.assertLess(template.index('home_egress_gateway }} accept'),
                        template.index('home_egress_lan }} drop'))
        # Docker の nft テーブルを消さない（消えるとコンテナの通信が壊れる）。
        self.assertNotIn('flush ruleset', [line.strip() for line in template.splitlines()])

    def test_the_ipv6_prefix_comes_from_the_router_advertisement(self):
        tasks = yaml.safe_load(read(ROLE / 'tasks/main.yml'))
        task = [t for t in tasks if 'Find the on-link IPv6 prefix' in t.get('name', '')][0]
        self.assertIn('proto ra', task['ansible.builtin.command'])
        template = read(ROLE / 'templates/nftables.conf.j2')
        self.assertIn('home_egress_ipv6_prefix', template)

    def test_loopback_and_tailnet_are_not_named(self):
        # いずれもデフォルト accept のまま。名前を足すと閉じてしまう。
        template = read(ROLE / 'templates/nftables.conf.j2')
        self.assertNotIn('127.0.0.1', template)
        self.assertNotIn('tailscale0', template)
        self.assertNotIn('100.64', template)


if __name__ == '__main__':
    unittest.main()
