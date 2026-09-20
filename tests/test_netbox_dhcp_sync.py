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


class DeleteGuardTests(unittest.TestCase):
    """再起動直後の「リース無し」で台帳を消さないための門番。"""

    LEASE = {'mac': 'de:78:35:35:ac:8c', 'address': '192.168.10.44', 'hostname': 'Pixel-8a'}

    def test_an_empty_lease_table_is_not_trusted(self):
        # 再起動でリースDB（tmpfs）が空になった直後の状態。
        self.assertFalse(sync.deletes_are_trustworthy([], sync.LEASE_TRUST_SECONDS + 1))

    def test_a_fresh_boot_is_not_trusted_even_with_a_few_leases(self):
        # 一部の端末だけが先に取り直した状態。残りを「去った」と誤解しない。
        self.assertFalse(sync.deletes_are_trustworthy([self.LEASE], 60))

    def test_a_long_uptime_with_leases_is_trusted(self):
        self.assertTrue(sync.deletes_are_trustworthy([self.LEASE], sync.LEASE_TRUST_SECONDS))


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


class ClientTests(unittest.TestCase):
    CLIENTS = [{'name': 'eufycam-s4', 'mac': '2C:8D:48:2C:5A:33'}]

    def test_clients_get_a_name_without_a_fixed_address(self):
        lines = sync.render_clients(self.CLIENTS)
        self.assertEqual(lines, ['dhcp-host=2c:8d:48:2c:5a:33,eufycam-s4'])
        # IP を書かない。動的アドレスのまま名前だけ付ける。
        self.assertNotIn('192.168.', lines[0])
        self.assertIn(lines[0], sync.render_file([], self.CLIENTS))

    def test_lease_name_prefers_the_client_then_the_declaration(self):
        names = sync.client_names({'clients': self.CLIENTS})
        self.assertEqual(
            sync.lease_name({'mac': '2c:8d:48:2c:5a:33', 'hostname': 'cam'}, names), 'cam')
        self.assertEqual(
            sync.lease_name({'mac': '2c:8d:48:2c:5a:33', 'hostname': ''}, names), 'eufycam-s4')
        self.assertEqual(
            sync.lease_name({'mac': 'aa:bb:cc:dd:ee:ff', 'hostname': ''}, names), '')


class DeviceSpecTests(unittest.TestCase):
    def setUp(self):
        self.spec = sync.load_yaml(sync.DEVICES)

    def test_the_static_devices_are_declared_with_macs(self):
        devices = {device['name']: device for device in self.spec['devices']}
        self.assertEqual(devices['aterm']['interface']['mac'], '80:22:a7:8f:27:80')
        self.assertEqual(devices['apextox']['address'], '192.168.10.10/24')
        self.assertEqual(devices['tarakoserver']['interface']['mac'], 'e4:5f:01:f2:b8:dc')
        self.assertEqual(devices['shakeserver']['address'], '192.168.10.12/24')
        # Wi-Fi 接続のプリンタ。MAC が無いと予約（dhcp-host）を生成できない。
        self.assertEqual(devices['printer']['interface']['mac'], 'f8:a2:6d:a5:e9:fb')
        self.assertEqual(devices['printer']['interface']['type'], 'ieee802.11ac')

    def test_pool_clients_are_declared_with_a_reserved_address(self):
        # 静的 IP の端末は devices に書く（clients は「名前だけ」用で、いまは空）。
        # reserved にすると dnsmasq が同じ IP を他の端末へ配らない。
        devices = {device['name']: device for device in self.spec['devices']}
        self.assertEqual(devices['eufycam-s4']['address'], '192.168.10.98/24')
        self.assertEqual(devices['alexa']['address'], '192.168.10.46/24')
        self.assertEqual(devices['switchbot-hubmini-ca2a09']['address'], '192.168.10.99/24')
        self.assertEqual(self.spec.get('clients', []), [])

    def test_every_declared_device_sits_in_a_managed_band(self):
        # 機器帯（.2〜.19）か DHCP プール内（reserved にして衝突を防ぐ）。
        network = sync.load_yaml(sync.NETWORK)
        for device in self.spec['devices']:
            self.assertTrue(
                sync.in_range(device['address'], network['infrastructure']) or
                sync.in_range(device['address'], network['dhcp']),
                device['name'])


class DiscoverTests(unittest.TestCase):
    """静的な IP の端末はリースを取らない。ARP から見つけて宣言する。"""

    NEIGH = """192.168.10.46 dev br-lan lladdr 4C:EF:C0:58:EA:66 REACHABLE
192.168.10.36 dev br-lan FAILED
240b:10:b280:2400::1 dev br-lan lladdr 4c:ef:c0:58:ea:66 REACHABLE
192.168.10.98 dev br-lan lladdr 2c:8d:48:2c:5a:33 STALE
bad line
"""

    def test_neigh_parses_ipv4_with_lladdr(self):
        entries = sync.parse_neigh(self.NEIGH)
        self.assertEqual([entry['address'] for entry in entries],
                         ['192.168.10.46', '192.168.10.98'])
        self.assertEqual(entries[0]['mac'], '4c:ef:c0:58:ea:66')
        self.assertEqual(entries[0]['state'], 'REACHABLE')

    def test_declared_macs_covers_devices_and_clients(self):
        spec = {'devices': [{'interface': {'mac': '4C:EF:C0:58:EA:66'}}],
                'clients': [{'mac': 'a8:48:fa:ca:2a:09'}]}
        self.assertEqual(sync.declared_macs(spec),
                         {'4c:ef:c0:58:ea:66', 'a8:48:fa:ca:2a:09'})


class ReservedRangeTests(unittest.TestCase):
    """プール内の reserved も dnsmasq の予約に入れる（衝突対策）。"""

    class FakeApi:
        def __init__(self, entries):
            self.entries = entries

        def get(self, path, **params):
            if path.startswith('/ipam/ip-addresses/'):
                return {'results': self.entries}
            raise AssertionError(path)

    ENTRIES = [
        {'address': '192.168.10.2/24', 'dns_name': 'aterm',
         'assigned_object_type': None, 'assigned_object_id': None},
        {'address': '192.168.10.46/24', 'dns_name': 'alexa',
         'assigned_object_type': None, 'assigned_object_id': None},
        {'address': '192.168.10.101/24', 'dns_name': 'media',
         'assigned_object_type': None, 'assigned_object_id': None},
    ]

    def test_pool_reservations_are_included_but_cloud_is_not(self):
        network = sync.load_yaml(sync.NETWORK)
        records = sync.reserved_records(
            self.FakeApi(self.ENTRIES), [network['infrastructure'], network['dhcp']])
        self.assertEqual([record['address'] for record in records],
                         ['192.168.10.2/24', '192.168.10.46/24'])


class TimerTests(unittest.TestCase):
    def test_the_timer_runs_the_tool(self):
        role = ROOT / 'platform/ansible/roles/netbox_dhcp_sync'
        service = (role / 'templates/netbox-dhcp-sync.service.j2').read_text(encoding='utf-8')
        for command in ('ensure', 'pull', 'push'):
            self.assertIn(f'tools/netbox-dhcp-sync.py {command}', service)
        timer = (role / 'templates/netbox-dhcp-sync.timer.j2').read_text(encoding='utf-8')
        self.assertIn('OnCalendar=', timer)
        playbook = (ROOT / 'platform/ansible/netbox-dhcp-sync.yml').read_text(encoding='utf-8')
        self.assertIn('netbox_dhcp_sync', playbook)


if __name__ == '__main__':
    unittest.main()
