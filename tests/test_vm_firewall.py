"""Guard the inbound allow-list of the platform VMs (platform/terraform/firewall.yaml).

A VM listed there drops every inbound connection it does not allow. A missing
SSH or node_exporter rule locks the operator or the monitoring out, and a typo
in a source name fails only at plan time; these checks catch both offline.
"""
import ipaddress
from pathlib import Path
import unittest

import yaml

from support import read

ROOT = Path(__file__).resolve().parents[1]
TERRAFORM = ROOT / 'platform/terraform'
FIREWALL = yaml.safe_load(read(TERRAFORM / 'firewall.yaml'))
HOSTS = yaml.safe_load(read(TERRAFORM / 'hosts.yaml'))['hosts']


def allows(rules, proto, port, source=None):
    for rule in rules:
        ports = (rule.get('dport') or '').split(',')
        if rule['proto'] == proto and str(port) in ports:
            if source is None or rule.get('from') is None or source in rule['from']:
                return True
    return False


class FirewallFileTests(unittest.TestCase):
    def test_sources_are_networks(self):
        for name, cidr in FIREWALL['sources'].items():
            ipaddress.ip_network(cidr)

    def test_rules_name_known_sources_and_have_comments(self):
        for host, rules in FIREWALL['hosts'].items():
            for rule in rules:
                self.assertIn(rule['proto'], ('tcp', 'udp', 'icmp'), host)
                self.assertTrue(rule.get('comment'), host)
                for source in rule.get('from') or []:
                    self.assertIn(source, FIREWALL['sources'], host)

    def test_every_host_is_a_platform_vm(self):
        # core-01 は 05-seed が持つ。ほかは hosts.yaml の基盤VM。
        for host in FIREWALL['hosts']:
            self.assertTrue(host == 'core-01' or host in HOSTS, host)

    def test_ssh_stays_open_from_the_server_segment(self):
        for host, rules in FIREWALL['hosts'].items():
            self.assertTrue(allows(rules, 'tcp', 22, 'servers'), host)

    def test_the_monitoring_can_still_scrape(self):
        self.assertEqual(FIREWALL['sources']['monitor'], '192.168.10.11/32')
        for host, rules in FIREWALL['hosts'].items():
            self.assertTrue(allows(rules, 'tcp', 9100, 'monitor'), host)
            self.assertTrue(allows(rules, 'tcp', 443), host)

    def test_the_admin_api_of_garage_is_not_opened(self):
        rules = FIREWALL['hosts']['cloud-01']
        self.assertTrue(allows(rules, 'tcp', 3900, 'servers'))
        self.assertFalse(allows(rules, 'tcp', 3903))
        self.assertFalse(allows(rules, 'tcp', 3901))


class TerraformWiringTests(unittest.TestCase):
    def test_both_stacks_read_the_same_file(self):
        for path in ('05-seed/main.tf', '10-platform/hosts.tf'):
            self.assertIn('../firewall.yaml', read(TERRAFORM / path), path)

    def test_the_default_drop_waits_for_the_allow_rules(self):
        module = read(TERRAFORM / 'modules/vm-firewall/main.tf')
        self.assertIn('input_policy  = "DROP"', module)
        self.assertIn('depends_on = [proxmox_virtual_environment_firewall_rules.inbound]', module)

    def test_the_nic_flag_follows_the_file(self):
        self.assertIn('firewall = contains(keys(local.firewall.hosts), var.name)',
                      read(TERRAFORM / '05-seed/main.tf'))
        self.assertIn('network_firewall = contains(keys(local.firewall.hosts), each.key)',
                      read(TERRAFORM / '10-platform/hosts.tf'))


if __name__ == '__main__':
    unittest.main()
