"""The network map reads the router's config and turns it into tables.

The page itself needs the live sources; these tests feed the model a small
router config instead, and pin the safety properties of the deployment.
"""
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'stacks/netmap'))

from app import checks, model, uci  # noqa: E402

DUMP = """### uci
network.lan=interface
network.lan.device='br-lan'
network.lan.proto='static'
network.lan.ipaddr='192.168.10.1'
network.lan.netmask='255.255.255.0'
network.personal=interface
network.personal.device='br-personal'
network.personal.proto='static'
network.personal.ipaddr='192.168.40.1'
network.guest=interface
network.guest.proto='static'
network.guest.ipaddr='192.168.9.1'
network.guest.disabled='1'
network.wan=interface
network.wan.proto='map'
network.@device[0]=device
network.@device[0].name='br-lan'
network.@device[0].ports='eth1.1'
network.br_personal=device
network.br_personal.name='br-personal'
network.br_personal.ports='eth1.40'
network.vlan_lan=switch_vlan
network.vlan_lan.vlan='1'
network.vlan_lan.ports='4 6 7 3t'
network.vlan_personal=switch_vlan
network.vlan_personal.vlan='40'
network.vlan_personal.ports='5 3t'
firewall.@zone[0]=zone
firewall.@zone[0].name='lan'
firewall.@zone[0].network='lan'
firewall.@zone[0].input='ACCEPT'
firewall.@zone[0].forward='ACCEPT'
firewall.@zone[1]=zone
firewall.@zone[1].name='wan'
firewall.@zone[1].network='wan' 'wan6'
firewall.@zone[1].input='DROP'
firewall.@zone[1].forward='REJECT'
firewall.@zone[2]=zone
firewall.@zone[2].name='guest'
firewall.@zone[2].network='guest'
firewall.personal=zone
firewall.personal.name='personal'
firewall.personal.network='personal'
firewall.personal.input='REJECT'
firewall.personal.forward='REJECT'
firewall.personal_lan=forwarding
firewall.personal_lan.src='personal'
firewall.personal_lan.dest='lan'
firewall.@rule[0]=rule
firewall.@rule[0].name='Dev-to-Personal'
firewall.@rule[0].src='lan'
firewall.@rule[0].dest='personal'
firewall.@rule[0].src_ip='192.168.10.202' '192.168.10.203'
firewall.@rule[0].target='ACCEPT'
firewall.@rule[1]=rule
firewall.@rule[1].name='Personal-DNS'
firewall.@rule[1].src='personal'
firewall.@rule[1].proto='tcp' 'udp'
firewall.@rule[1].dest_port='53'
firewall.@rule[1].target='ACCEPT'
wireless.wifi5g=wifi-iface
wireless.wifi5g.device='wifi1'
wireless.wifi5g.network='personal'
wireless.wifi5g.ssid='ditto'
wireless.guest5g=wifi-iface
wireless.guest5g.network='guest'
wireless.guest5g.ssid='guest'
dhcp.personal=dhcp
dhcp.personal.interface='personal'
dhcp.personal.start='20'
dhcp.personal.limit='180'
### leases
1792015362 06:6d:e4:99:dc:16 192.168.40.110 * 01:06
### links
5 port:5 link:up speed:2500baseT full-duplex
"""


class UciTests(unittest.TestCase):
    def test_lists_and_anonymous_sections(self):
        config = uci.parse("firewall.@zone[1]=zone\nfirewall.@zone[1].network='wan' 'wan6'\n")
        self.assertEqual(config['firewall']['@zone[1]']['network'], ['wan', 'wan6'])
        self.assertEqual(config['firewall']['@zone[1]']['.type'], 'zone')


class RouterModelTests(unittest.TestCase):
    def setUp(self):
        self.state = model.router(DUMP)

    def test_disabled_segments_are_left_out(self):
        self.assertEqual([z['name'] for z in self.state['zones']], ['lan', 'wan', 'personal'])

    def test_segments_carry_their_ssids_ports_and_dhcp(self):
        personal = self.state['by_name']['personal']
        self.assertEqual(personal['subnets'], ['192.168.40.0/24'])
        self.assertEqual([s['ssid'] for s in personal['ssids']], ['ditto'])
        self.assertEqual(personal['ports'], ['LAN3'])
        self.assertEqual(personal['dhcp'], '192.168.40.20〜192.168.40.199')
        self.assertEqual(self.state['by_name']['lan']['ports'], ['LAN4', 'LAN2', 'LAN1'])

    def test_the_matrix_tells_full_partial_and_denied_apart(self):
        rows = {row['zone']['name']: row['cells'] for row in model.matrix(self.state)['rows']}
        order = ['lan', 'wan', 'personal', '__router__']
        personal = dict(zip(order, rows['personal']))
        self.assertEqual(personal['lan']['kind'], 'allow')
        self.assertEqual(personal['wan']['kind'], 'deny')
        self.assertEqual(personal['__router__']['kind'], 'partial')
        lan = dict(zip(order, rows['lan']))
        self.assertEqual(lan['personal']['kind'], 'partial')
        self.assertIn('192.168.10.202', lan['personal']['rules'][0]['what'])

    def test_the_segment_diagram_draws_full_and_partial_paths(self):
        diagram = model.segment_diagram(self.state)
        self.assertIn('n_personal ==>|すべて| n_lan', diagram)
        self.assertIn('n_lan -.->|一部 1件| n_personal', diagram)


CHECKED = """### uci
firewall.shakecloud_ts_lan=forwarding
firewall.shakecloud_ts_lan.src='tailscale'
firewall.shakecloud_ts_lan.dest='lan'
firewall.tailscale_personal=forwarding
firewall.tailscale_personal.src='tailscale'
firewall.tailscale_personal.dest='personal'
tailscale.settings=settings
tailscale.settings.lan_enabled='1'
### tailscale-routes
[ "192.168.10.0\\/24" ]
"""


class RouterCheckTests(unittest.TestCase):
    def test_the_applied_config_passes_every_check(self):
        results = checks.run(CHECKED)
        self.assertTrue(all(results.values()), results)

    def test_what_gl_inet_removes_is_reported(self):
        dump = CHECKED.replace('192.168.10.0\\/24', '').replace("dest='lan'", "dest='wan'")
        results = checks.run(dump)
        self.assertFalse(results['tailscale_to_lan'])
        self.assertFalse(results['advertise_192.168.10.0/24'])
        self.assertIn('shakecloud_router_check{check="tailscale_to_lan"} 0', checks.metrics(results))

    def test_advertising_the_personal_segment_is_reported(self):
        dump = CHECKED.replace('[ "192.168.10.0\\/24" ]', '[ "192.168.10.0\\/24", "192.168.40.0\\/24" ]')
        self.assertFalse(checks.run(dump)['not_advertise_192.168.40.0/24'])

    def test_the_forwarding_does_not_use_the_name_gl_inet_deletes(self):
        script = (ROOT / 'platform/flint3/rootfs/etc/shakecloud/apply-segments').read_text()
        self.assertNotIn('set firewall.tailscale_lan', script)
        self.assertIn("uci set tailscale.settings.lan_enabled='1'", script)


class DeploymentTests(unittest.TestCase):
    def test_the_dump_never_prints_secret_options(self):
        dump = (ROOT / 'platform/flint3/rootfs/etc/shakecloud/netmap-dump').read_text()
        self.assertIn('(key|password|secret|psk)', dump)
        # prefs のほかの項目には鍵が入る。経路の一覧だけを抜き出す。
        prefs = [line for line in dump.splitlines() if 'debug prefs' in line]
        self.assertEqual(len(prefs), 1)
        self.assertIn("jsonfilter -e '@.AdvertiseRoutes'", prefs[0])

    def test_the_service_listens_on_loopback_only(self):
        compose = yaml.safe_load((ROOT / 'stacks/netmap/compose.yaml').read_text())
        ports = compose['services']['netmap']['ports']
        self.assertTrue(all(port.startswith('127.0.0.1:') for port in ports))
        self.assertIn('./secrets:/run/netmap:ro', compose['services']['netmap']['volumes'])

    def test_the_base_image_is_pinned(self):
        dockerfile = (ROOT / 'stacks/netmap/Dockerfile').read_text()
        self.assertRegex(dockerfile, r'(?m)^FROM \S+@sha256:[0-9a-f]{64}$')

    def test_the_flint_key_may_only_run_the_dump(self):
        tasks = (ROOT / 'platform/ansible/roles/netmap/tasks/main.yml').read_text()
        self.assertIn('command="/etc/shakecloud/netmap-dump",no-pty,no-port-forwarding', tasks)


if __name__ == '__main__':
    unittest.main()
