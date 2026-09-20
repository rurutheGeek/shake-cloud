"""Check the NetBox ↔ router DHCP sync tool's parsing and rendering.

The tool talks to a live NetBox and a live router, but the pieces that decide
what gets written are pure: lease parsing, MAC normalisation, dnsmasq host
rendering and range filtering. A bug here would write a wrong reservation or
mark the wrong address as leased.
"""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'netbox_dhcp_sync', ROOT / 'tools/netbox-dhcp-sync.py')
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


class LeaseTests(unittest.TestCase):
    LEASES = """1789928681 a8:48:fa:ca:2a:09 192.168.10.37 SwitchBot-HubMini-CA2A09 *
1789928113 DE:78:35:35:AC:8C 192.168.10.44 Pixel-8a 01:de:78:35:35:ac:8c
1789929273 * 192.168.10.35 * *
bad line
"""

    def test_leases_parse_into_mac_address_hostname(self):
        leases = sync.parse_leases(self.LEASES)
        self.assertEqual(len(leases), 2)
        self.assertEqual(leases[0], {'mac': 'a8:48:fa:ca:2a:09',
                                     'address': '192.168.10.37',
                                     'hostname': 'SwitchBot-HubMini-CA2A09'})
        self.assertEqual(leases[1]['mac'], 'de:78:35:35:ac:8c')
        self.assertEqual(leases[1]['hostname'], 'Pixel-8a')

    def test_a_line_without_a_mac_is_skipped(self):
        # dnsmasq writes `*` for the hostname, not for the MAC, but be strict:
        # a malformed line must not become a lease record.
        self.assertNotIn('192.168.10.35',
                         [lease['address'] for lease in sync.parse_leases(self.LEASES)])


class RenderTests(unittest.TestCase):
    RECORDS = [
        {'mac': 'E4:5F:01:F2:B8:DC', 'address': '192.168.10.11/24', 'name': 'tarakoserver'},
        {'mac': '80:22:a7:8f:27:80', 'address': '192.168.10.2/24', 'name': 'aterm'},
        {'mac': '', 'address': '192.168.10.3/24', 'name': 'printer'},
    ]

    def test_hosts_are_sorted_and_macs_normalised(self):
        lines = sync.render_hosts(self.RECORDS)
        self.assertEqual(lines, [
            'dhcp-host=80:22:a7:8f:27:80,192.168.10.2,aterm',
            'dhcp-host=e4:5f:01:f2:b8:dc,192.168.10.11,tarakoserver',
        ])

    def test_a_device_without_a_mac_cannot_be_reserved(self):
        self.assertNotIn('printer', '\n'.join(sync.render_hosts(self.RECORDS)))

    def test_the_file_carries_a_generated_header(self):
        text = sync.render_file(self.RECORDS)
        self.assertIn('手で編集しない', text)
        self.assertTrue(text.endswith('\n'))


class RangeTests(unittest.TestCase):
    def setUp(self):
        self.infrastructure = {'range_start': '192.168.10.2/24',
                               'range_end': '192.168.10.19/24'}
        self.dhcp = {'range_start': '192.168.10.20/24',
                     'range_end': '192.168.10.99/24'}

    def test_membership_is_inclusive(self):
        self.assertTrue(sync.in_range('192.168.10.2/24', self.infrastructure))
        self.assertTrue(sync.in_range('192.168.10.19/24', self.infrastructure))
        self.assertFalse(sync.in_range('192.168.10.20/24', self.infrastructure))
        self.assertFalse(sync.in_range('192.168.10.10/24', self.dhcp))

    def test_the_bands_do_not_touch(self):
        self.assertFalse(sync.in_range('192.168.10.19/24', self.dhcp))
        self.assertFalse(sync.in_range('192.168.10.20/24', self.infrastructure))


class DeviceSpecTests(unittest.TestCase):
    def setUp(self):
        self.spec = sync.load_yaml(sync.DEVICES)

    def test_the_static_devices_are_declared_with_macs(self):
        devices = {device['name']: device for device in self.spec['devices']}
        self.assertEqual(devices['aterm']['interface']['mac'], '80:22:a7:8f:27:80')
        self.assertEqual(devices['apextox']['address'], '192.168.10.10/24')
        self.assertEqual(devices['tarakoserver']['interface']['mac'], 'e4:5f:01:f2:b8:dc')
        self.assertEqual(devices['shakeserver']['address'], '192.168.10.12/24')

    def test_every_declared_device_sits_in_the_infrastructure_band(self):
        network = sync.load_yaml(sync.NETWORK)
        for device in self.spec['devices']:
            self.assertTrue(sync.in_range(device['address'], network['infrastructure']),
                            device['name'])


if __name__ == '__main__':
    unittest.main()
