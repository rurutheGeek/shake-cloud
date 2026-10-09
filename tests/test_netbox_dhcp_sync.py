"""Check the NetBox ↔ router DHCP sync tool's parsing and rendering.

The tool talks to a live NetBox and a live router, but the pieces that decide
what gets written are pure: lease parsing, MAC normalisation, dnsmasq host
rendering and range filtering. A bug here would write a wrong reservation or
mark the wrong address as leased.
"""
import copy
import datetime
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

    def test_reserved_names_are_published_without_a_lease(self):
        # dnsmasq 2.93 の実測: dhcp-host だけでは、リースを取らない静的 IP の
        # 端末名が引けない（NXDOMAIN）。host-record ならリースと無関係に引ける。
        self.assertEqual(sync.render_names(self.RECORDS), [
            'host-record=aterm.lan,192.168.10.2',
            'host-record=printer.lan,192.168.10.3',
            'host-record=tarakoserver.lan,192.168.10.11',
        ])

    def test_a_device_without_a_mac_still_gets_a_name(self):
        # MAC が無くても DNS 名は付けられる（プリンタなど）。
        self.assertIn('host-record=printer.lan,192.168.10.3',
                      sync.render_file(self.RECORDS))

    def test_a_qualified_name_is_not_rewritten(self):
        records = [{'mac': '', 'address': '192.168.10.101/24',
                    'name': 'nextcloud.apextox.dpdns.org'}]
        self.assertEqual(sync.render_names(records),
                         ['host-record=nextcloud.apextox.dpdns.org,192.168.10.101'])

    def test_a_record_without_a_name_is_skipped(self):
        records = [{'mac': 'aa:bb:cc:dd:ee:ff', 'address': '192.168.10.5/24', 'name': ''}]
        self.assertEqual(sync.render_names(records), [])

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

    def test_devices_without_an_address_get_a_name_only_entry(self):
        # Wi-Fi 家電など。MAC を interface に書くだけで名前が付く（IP は動的のまま）。
        spec = {'devices': [
            {'name': 'oven', 'interface': {'mac': 'AA:BB:CC:DD:EE:FF'}},
            {'name': 'fixed', 'address': '192.168.10.5/24',
             'interface': {'mac': '11:22:33:44:55:66'}}],
            'clients': []}
        clients = sync.declared_clients(spec)
        self.assertEqual(clients, [{'mac': 'aa:bb:cc:dd:ee:ff', 'name': 'oven'}])
        self.assertIn('dhcp-host=aa:bb:cc:dd:ee:ff,oven', sync.render_file([], clients))

    def test_a_device_can_opt_out_of_dhcp(self):
        # 家の LAN に居ない機器（リモートの Pi など）。
        spec = {'devices': [{'name': 'remote', 'dhcp': False,
                             'interface': {'mac': 'AA:BB:CC:DD:EE:FF'}}]}
        self.assertEqual(sync.declared_clients(spec), [])

    def test_the_same_mac_is_not_declared_twice(self):
        # dnsmasq は重複した dhcp-host で起動に失敗する。
        spec = {'clients': [{'name': 'cam', 'mac': 'AA:BB:CC:DD:EE:FF'}],
                'devices': [{'name': 'cam2', 'interface': {'mac': 'aa:bb:cc:dd:ee:ff'}}]}
        self.assertEqual(sync.declared_clients(spec),
                         [{'mac': 'aa:bb:cc:dd:ee:ff', 'name': 'cam'}])

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

        def macs(name):
            return {interface.get('mac')
                    for interface in sync.interface_specs(devices[name])}

        self.assertIn('80:22:a7:8f:27:80', macs('aterm'))
        self.assertEqual(devices['apextox']['address'], '192.168.10.10/24')
        self.assertIn('e4:5f:01:f2:b8:dc', macs('tarakoserver'))
        self.assertEqual(devices['shakeserver']['address'], '192.168.10.12/24')
        # Wi-Fi 接続のプリンタ。MAC が無いと予約（dhcp-host）を生成できない。
        self.assertIn('f8:a2:6d:a5:e9:fb', macs('printer'))
        self.assertEqual(devices['printer']['interface']['type'], 'ieee802.11ac')

    def test_pool_clients_are_declared_with_a_reserved_address(self):
        # 静的 IP の端末は devices に書く（clients は「名前だけ」用で、いまは空）。
        # reserved にすると dnsmasq が同じ IP を他の端末へ配らない。
        devices = {device['name']: device for device in self.spec['devices']}
        self.assertEqual(devices['eufycam-s4']['address'], '192.168.10.98/24')
        self.assertEqual(devices['alexa']['address'], '192.168.10.46/24')
        self.assertEqual(devices['switchbot-hubmini-ca2a09']['address'], '192.168.10.99/24')
        self.assertEqual(self.spec.get('clients', []), [])

    def test_every_declared_address_sits_in_a_managed_band(self):
        # 機器帯（.2〜.19）か DHCP プール内（reserved にして衝突を防ぐ）。
        # ネット接続の無い機器は address を持たない（dcim にだけ載る）。
        network = sync.load_yaml(sync.NETWORK)
        for device in self.spec['devices']:
            address = device.get('address')
            if not address:
                continue
            self.assertTrue(
                sync.in_range(address, network['infrastructure']) or
                sync.in_range(address, network['dhcp']),
                device['name'])

    def test_every_device_references_declared_roles_and_types(self):
        roles = {role['name'] for role in self.spec['roles']}
        models = {entry['model'] for entry in self.spec['device_types']}
        makers = {maker['name'] for maker in self.spec['manufacturers']}
        for device in self.spec['devices']:
            self.assertIn(device['role'], roles, device['name'])
            self.assertIn(device['device_type'], models, device['name'])
        for entry in self.spec['device_types']:
            self.assertIn(entry['manufacturer'], makers, entry['slug'])

    def test_a_device_type_can_carry_the_product_specs(self):
        # 型番は part_number、JAN・寸法・重さなどの仕様は comments に残す。
        types = {entry['model']: entry for entry in self.spec['device_types']}
        capture = types['ゲーミングビデオキャプチャ Light']
        self.assertEqual(capture['part_number'], 'CRC-GVCAP03')
        self.assertIn('4549032017595', capture['comments'])

    def test_cable_endpoints_are_declared(self):
        devices = {device['name']: device for device in self.spec['devices']}
        for cable in self.spec.get('cables', []):
            for end in (cable['a'], cable['b']):
                self.assertIn(end['device'], devices, cable)
                device = devices[end['device']]
                names = {interface['name'] for interface in sync.interface_specs(device)}
                names.update(device.get('power_ports', []))
                names.update(device.get('power_outlets', []))
                self.assertIn(sync.endpoint_name(end), names, cable)

    def test_address_interface_names_a_declared_interface(self):
        for device in self.spec['devices']:
            wanted = device.get('address_interface')
            if not wanted:
                continue
            names = {interface['name'] for interface in sync.interface_specs(device)}
            self.assertIn(wanted, names, device['name'])

    def test_non_network_devices_are_declared_without_addresses(self):
        devices = {device['name']: device for device in self.spec['devices']}
        self.assertNotIn('address', devices['arduino-nano-1'])
        # NetBox の interface 種別に USB は無い。マイコンは interface を省く。
        self.assertNotIn('interface', devices['arduino-nano-1'])
        self.assertNotIn('address', devices['arduino-leonardo-1'])
        # アンマネージドスイッチは管理 interface を持たない。
        self.assertNotIn('interface', devices['tl-sg605'])
        self.assertNotIn('address', devices['tl-sg605'])


class DiscoverTests(unittest.TestCase):
    """静的な IP の端末はリースを取らない。ARP から見つけて宣言する。"""

    NEIGH = """192.168.10.46 dev br-lan lladdr 4C:EF:C0:58:EA:66 REACHABLE
192.168.10.36 dev br-lan FAILED
2001:db8:10:2400::1 dev br-lan lladdr 4c:ef:c0:58:ea:66 REACHABLE
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
        spec = {'devices': [{'interface': {'mac': '4C:EF:C0:58:EA:66'}},
                            {'interfaces': [{'mac': '00:1C:BE:B7:21:F7'},
                                            {'mac': '88:A2:9E:C8:4A:AE'}]}],
                'clients': [{'mac': 'a8:48:fa:ca:2a:09'}]}
        self.assertEqual(sync.declared_macs(spec),
                         {'4c:ef:c0:58:ea:66', '00:1c:be:b7:21:f7',
                          '88:a2:9e:c8:4a:ae', 'a8:48:fa:ca:2a:09'})


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


class DeviceSyncTests(unittest.TestCase):
    """ensure が dcim を宣言へ合わせる（ネット接続の無い機器も含む）。"""

    class FakeApi:
        """ensure_devices が使う API だけを模す最小の NetBox。"""

        def __init__(self):
            self.store = {'/dcim/sites/': [{'id': 1, 'name': 'Homelab'}]}
            self.next_id = 100

        def _matches(self, entry, params):
            for key, value in params.items():
                if key == 'limit':
                    continue
                # NetBox の絞り込みは `device_id` でも、返るオブジェクトの
                # フィールドは `device`（{'id': ..}）。
                current = entry.get(key[:-3] if key.endswith('_id') else key)
                if isinstance(current, dict):
                    current = current.get('id')
                if current != value:
                    return False
            return True

        def one(self, path, **params):
            return next((entry for entry in self.store.get(path, [])
                         if self._matches(entry, params)), None)

        def post(self, path, payload):
            entry = dict(payload)
            if entry.get('comments'):
                # NetBox は comments の末尾空白を落として保存する。
                entry['comments'] = entry['comments'].strip()
            entry['id'] = self.next_id
            self.next_id += 1
            self.store.setdefault(path, []).append(entry)
            return entry

        def patch(self, path, payload):
            payload = dict(payload)
            if payload.get('comments'):
                payload['comments'] = payload['comments'].strip()
            collection, _, pk = path.rstrip('/').rpartition('/')
            for entry in self.store.get(collection + '/', []):
                if str(entry['id']) == pk:
                    entry.update(payload)
                    return entry
            raise AssertionError(f'no object at {path}')

    SPEC = {
        'site': 'Homelab',
        'roles': [{'name': 'Microcontroller', 'slug': 'microcontroller',
                   'color_hex': '00b0b0'}],
        'manufacturers': [{'name': 'Arduino', 'slug': 'arduino'}],
        'device_types': [{'manufacturer': 'Arduino', 'model': 'Arduino Nano',
                          'slug': 'arduino-nano'}],
        'devices': [
            {'name': 'arduino-nano-1', 'device_type': 'Arduino Nano',
             'role': 'Microcontroller', 'description': 'USB',
             'interface': {'name': 'usb', 'type': 'other'}},
            {'name': 'tl-sg605', 'device_type': 'Arduino Nano',
             'role': 'Microcontroller'},
        ],
    }

    def test_ensure_is_idempotent_and_needs_no_interface(self):
        api = self.FakeApi()
        first = sync.ensure_devices(api, self.SPEC)
        self.assertIn('create device tl-sg605', first)
        self.assertNotIn('create interface tl-sg605/usb', first)
        # 2回目は差分なし。interface の無い機器でも落ちない。
        self.assertEqual(sync.ensure_devices(api, self.SPEC), [])

    def test_block_scalar_comments_do_not_cause_a_diff_loop(self):
        # YAML の `|` は末尾に改行を入れるが、NetBox は落として保存する。
        api = self.FakeApi()
        spec = copy.deepcopy(self.SPEC)
        spec['device_types'][0]['comments'] = 'ATmega328P\n'
        spec['devices'][0]['comments'] = 'USB\n'
        sync.ensure_devices(api, spec)
        self.assertEqual(sync.ensure_devices(api, spec), [])

    def test_declared_fields_are_corrected_on_the_next_run(self):
        api = self.FakeApi()
        sync.ensure_devices(api, self.SPEC)
        spec = copy.deepcopy(self.SPEC)
        spec['devices'][0]['description'] = 'USB (ATmega328P)'
        spec['devices'][0]['serial'] = 'SN-1'
        spec['devices'][0]['comments'] = '書き込み用'
        actions = sync.ensure_devices(api, spec)
        self.assertIn('update device arduino-nano-1 (comments, description, serial)', actions)
        self.assertEqual(api.store['/dcim/devices/'][0]['serial'], 'SN-1')
        self.assertEqual(api.store['/dcim/devices/'][0]['comments'], '書き込み用')
        # 宣言していない asset_tag は画面側の値を消さない。
        self.assertNotIn('asset_tag', api.store['/dcim/devices/'][0])

    def test_a_part_number_and_comments_are_added_to_an_existing_device_type(self):
        api = self.FakeApi()
        sync.ensure_devices(api, self.SPEC)
        spec = copy.deepcopy(self.SPEC)
        spec['device_types'][0]['part_number'] = 'A000005'
        spec['device_types'][0]['comments'] = 'ATmega328P'
        self.assertIn('update device_type arduino-nano (comments, part_number)',
                      sync.ensure_devices(api, spec))

    def test_multiple_interfaces_are_created_and_macs_set(self):
        api = self.FakeApi()
        spec = copy.deepcopy(self.SPEC)
        spec['devices'] = [{'name': 'pi', 'device_type': 'Arduino Nano',
                            'role': 'Microcontroller',
                            'interfaces': [{'name': 'eth0', 'type': 'other',
                                            'mac': '00:1C:BE:B7:21:F7'},
                                           {'name': 'wlan0', 'type': 'ieee802.11ac',
                                            'mac': '88:A2:9E:C8:4A:AE'}]}]
        sync.ensure_devices(api, spec)
        self.assertEqual(sync.ensure_devices(api, spec), [])
        macs = {entry['name']: entry['mac_address']
                for entry in api.store['/dcim/interfaces/']}
        self.assertEqual(macs, {'eth0': '00:1c:be:b7:21:f7',
                                'wlan0': '88:a2:9e:c8:4a:ae'})

    def test_address_interface_picks_which_port_gets_the_ip(self):
        api = self.FakeApi()
        spec = copy.deepcopy(self.SPEC)
        spec['devices'] = [{'name': 'box', 'device_type': 'Arduino Nano',
                            'role': 'Microcontroller', 'address': '192.168.10.15/24',
                            'address_interface': 'wlan0',
                            'interfaces': [{'name': 'eth0', 'type': 'other'},
                                           {'name': 'wlan0', 'type': 'ieee802.11ac'}]}]
        sync.ensure_devices(api, spec)
        interfaces = {entry['name']: entry['id']
                      for entry in api.store['/dcim/interfaces/']}
        self.assertEqual(api.store['/ipam/ip-addresses/'][0]['assigned_object_id'],
                         interfaces['wlan0'])

    def test_purchase_and_warranty_are_synced_as_custom_fields(self):
        api = self.FakeApi()
        spec = copy.deepcopy(self.SPEC)
        spec['custom_fields'] = [
            {'name': 'purchase_date', 'label': '購入日', 'type': 'date'},
            {'name': 'warranty_until', 'label': '保証期限', 'type': 'date'}]
        spec['devices'][0]['purchase_date'] = datetime.date(2026, 3, 11)
        spec['devices'][0]['warranty_until'] = datetime.date(2029, 3, 11)
        first = sync.ensure_devices(api, spec)
        self.assertIn('create custom_field purchase_date', first)
        self.assertEqual(sync.ensure_devices(api, spec), [])
        self.assertEqual(api.store['/dcim/devices/'][0]['custom_fields'],
                         {'purchase_date': '2026-03-11',
                          'warranty_until': '2029-03-11'})
        spec['devices'][0]['warranty_until'] = datetime.date(2030, 3, 11)
        self.assertIn('update device arduino-nano-1 (custom_fields)',
                      sync.ensure_devices(api, spec))

    def test_power_ports_and_outlets_are_created(self):
        api = self.FakeApi()
        spec = copy.deepcopy(self.SPEC)
        spec['devices'][0]['power_ports'] = ['ac']
        spec['devices'][1]['power_outlets'] = ['battery1']
        first = sync.ensure_devices(api, spec)
        self.assertIn('create power port arduino-nano-1/ac', first)
        self.assertIn('create power outlet tl-sg605/battery1', first)
        self.assertEqual(sync.ensure_devices(api, spec), [])

    def test_a_power_cable_connects_an_outlet_to_a_port(self):
        api = self.FakeApi()
        spec = copy.deepcopy(self.SPEC)
        spec['devices'][0]['power_ports'] = ['ac']
        spec['devices'][1]['power_outlets'] = ['battery1']
        spec['cables'] = [{'a': {'device': 'tl-sg605', 'power_outlet': 'battery1'},
                           'b': {'device': 'arduino-nano-1', 'power_port': 'ac'},
                           'type': 'power'}]
        first = sync.ensure_devices(api, spec)
        self.assertIn('create cable tl-sg605/battery1 - arduino-nano-1/ac', first)
        cable = api.store['/dcim/cables/'][0]
        self.assertEqual(cable['a_terminations'][0]['object_type'], 'dcim.poweroutlet')
        self.assertEqual(cable['b_terminations'][0]['object_type'], 'dcim.powerport')
        self.assertEqual(sync.ensure_devices(api, spec), [])

    def test_cables_are_created_and_kept_in_step(self):
        api = self.FakeApi()
        spec = copy.deepcopy(self.SPEC)
        spec['devices'][1]['interface'] = {'name': 'usb', 'type': 'other'}
        spec['cables'] = [{'a': {'device': 'arduino-nano-1', 'interface': 'usb'},
                           'b': {'device': 'tl-sg605', 'interface': 'usb'},
                           'type': 'usb', 'description': 'テスト'}]
        first = sync.ensure_devices(api, spec)
        self.assertIn('create cable arduino-nano-1/usb - tl-sg605/usb', first)
        self.assertEqual(sync.ensure_devices(api, spec), [])
        spec['cables'][0]['description'] = 'テスト2'
        self.assertIn('update cable arduino-nano-1/usb - tl-sg605/usb (description)',
                      sync.ensure_devices(api, spec))

    def test_a_cable_needs_declared_interfaces(self):
        api = self.FakeApi()
        spec = copy.deepcopy(self.SPEC)
        spec['cables'] = [{'a': {'device': 'arduino-nano-1', 'interface': 'nope'},
                           'b': {'device': 'tl-sg605', 'interface': 'usb'}}]
        with self.assertRaises(SystemExit):
            sync.ensure_devices(api, spec)

    def test_an_address_without_an_interface_is_created_unassigned(self):
        api = self.FakeApi()
        spec = copy.deepcopy(self.SPEC)
        spec['devices'] = [{'name': 'static-box', 'device_type': 'Arduino Nano',
                            'role': 'Microcontroller', 'address': '192.168.10.15/24'}]
        self.assertIn('create ip 192.168.10.15/24 (static-box)',
                      sync.ensure_devices(api, spec))
        self.assertNotIn('assigned_object_id', api.store['/ipam/ip-addresses/'][0])

    def test_an_interface_added_later_is_assigned_to_the_ip(self):
        api = self.FakeApi()
        spec = copy.deepcopy(self.SPEC)
        spec['devices'] = [{'name': 'static-box', 'device_type': 'Arduino Nano',
                            'role': 'Microcontroller', 'address': '192.168.10.15/24'}]
        sync.ensure_devices(api, spec)
        spec['devices'][0]['interface'] = {'name': 'wlan0', 'type': 'ieee802.11ac'}
        self.assertIn('update ip 192.168.10.15/24 (static-box)',
                      sync.ensure_devices(api, spec))
        self.assertEqual(api.store['/ipam/ip-addresses/'][0]['assigned_object_type'],
                         'dcim.interface')


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
