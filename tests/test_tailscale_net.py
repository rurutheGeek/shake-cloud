"""Check tools/tailscale-net.py's judgement without touching the API.

The console settings it applies are easy to get wrong twice: a route the node
does not advertise cannot be enabled, and the endpoints replace whole lists, so
sending only the missing entry would drop the rest. The judgement is tested
here; the HTTP calls are not.
"""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('tailscale_net', ROOT / 'tools/tailscale-net.py')
tailscale_net = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tailscale_net)


class DeviceTests(unittest.TestCase):
    def test_finds_the_one_device(self):
        devices = [{'hostname': 'net-01', 'id': '1'}]
        self.assertEqual(tailscale_net.find_device(devices, 'net-01')['id'], '1')

    def test_a_missing_device_is_an_error(self):
        with self.assertRaises(tailscale_net.TailscaleError):
            tailscale_net.find_device([], 'net-01')

    def test_duplicates_are_refused_before_writing_to_the_wrong_one(self):
        devices = [{'hostname': 'net-01', 'id': '1'},
                   {'hostname': 'net-01', 'id': '2'}]
        with self.assertRaises(tailscale_net.TailscaleError):
            tailscale_net.find_device(devices, 'net-01')


class RouteTests(unittest.TestCase):
    def test_the_prefix_is_added_and_existing_routes_kept(self):
        self.assertEqual(
            tailscale_net.routes_to_enable(
                ['10.1.0.0/16', '192.168.10.0/24'], ['10.1.0.0/16'], '192.168.10.0/24'),
            ['10.1.0.0/16', '192.168.10.0/24'])

    def test_an_enabled_prefix_is_no_change(self):
        self.assertIsNone(tailscale_net.routes_to_enable(
            ['192.168.10.0/24'], ['192.168.10.0/24'], '192.168.10.0/24'))

    def test_an_unadvertised_prefix_is_refused(self):
        # Enabling it would "succeed" and route nothing; Ansible must run first.
        with self.assertRaises(tailscale_net.TailscaleError):
            tailscale_net.routes_to_enable(['10.1.0.0/16'], [], '192.168.10.0/24')


class ConfigurationTests(unittest.TestCase):
    def test_adguard_replaces_the_resolvers_and_override_is_set(self):
        current = {
            'nameservers': [{'address': '8.8.8.8', 'useWithExitNode': True}],
            'preferences': {'magicDNS': True, 'overrideLocalDNS': False},
        }
        plan = tailscale_net.configuration_plan(current, '192.168.10.1')
        self.assertEqual(plan['nameservers'], [{'address': '192.168.10.1'}])
        self.assertEqual(plan['preferences'],
                         {'magicDNS': True, 'overrideLocalDNS': True})

    def test_parts_the_tool_does_not_own_are_sent_back_unchanged(self):
        current = {
            'nameservers': [],
            'splitDNS': {'corp.example.com': [{'address': '10.0.0.53'}]},
            'searchPaths': ['corp.example.com'],
            'preferences': {'magicDNS': True},
        }
        plan = tailscale_net.configuration_plan(current, '192.168.10.1')
        self.assertEqual(plan['splitDNS'], current['splitDNS'])
        self.assertEqual(plan['searchPaths'], current['searchPaths'])

    def test_a_matching_configuration_is_no_change(self):
        current = {
            'nameservers': [{'address': '192.168.10.1'}],
            'preferences': {'magicDNS': True, 'overrideLocalDNS': True},
        }
        self.assertIsNone(tailscale_net.configuration_plan(current, '192.168.10.1'))

    def test_a_missing_override_is_a_change_even_when_the_resolver_matches(self):
        current = {
            'nameservers': [{'address': '192.168.10.1'}],
            'preferences': {'magicDNS': True, 'overrideLocalDNS': False},
        }
        self.assertIsNotNone(tailscale_net.configuration_plan(current, '192.168.10.1'))


class PolicyTests(unittest.TestCase):
    def test_the_legacy_allow_all_is_recognised(self):
        summary = tailscale_net.acl_summary(
            '{"acls": [{"action": "accept", "src": ["*"], "dst": ["*:*"]}]}')
        self.assertIn('allow all', summary)

    def test_the_grants_form_of_allow_all_is_recognised(self):
        summary = tailscale_net.acl_summary(
            '{"grants": [{"src": ["*"], "dst": ["*"], "ip": ["*"]}]}')
        self.assertIn('allow all', summary)

    def test_a_port_restricted_policy_is_not_called_allow_all(self):
        summary = tailscale_net.acl_summary(
            '{"grants": [{"src": ["*"], "dst": ["*"], "ip": ["tcp:443"]}]}')
        self.assertNotIn('DNS も許可されている', summary)


if __name__ == '__main__':
    unittest.main()
