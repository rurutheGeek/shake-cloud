"""Flint 3 (GL-BE9300) takes over from router-01.

The Flint 3 keeps GL.iNet's stock config and only overrides what it must, so
there is no full UCI file to parse. These tests pin the parts that have to
stay in step with router-01 and with the address plan.
"""
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FLINT = ROOT / 'platform/flint3/rootfs/etc'
OPENWRT = ROOT / 'platform/openwrt/rootfs/etc'
APPLY = (FLINT / 'shakecloud/apply-router').read_text(encoding='utf-8')


def uci(key):
    match = re.search(rf"^uci set {re.escape(key)}='([^']*)'$", APPLY, re.M)
    return match.group(1) if match else None


class SharedWithRouterTests(unittest.TestCase):
    def test_the_helpers_are_the_ones_proven_on_router_01(self):
        # The MAP-E port spreading and the NDP proxy were debugged on router-01.
        # A copy that drifts would bring the port exhaustion back.
        for name in ('hotplug.d/iface/90-mape-ports', 'hotplug.d/iface/91-lan-prefix-route', 'ndppd.conf'):
            self.assertEqual((FLINT / name).read_bytes(), (OPENWRT / name).read_bytes(), name)

    def test_the_map_e_parameters_match_router_01(self):
        network = (OPENWRT / 'shakecloud/config/network').read_text(encoding='utf-8')
        for option in ('peeraddr', 'ip6prefix', 'ip6prefixlen', 'ipaddr', 'ip4prefixlen',
                       'ealen', 'psidlen', 'offset', 'legacymap', 'mtu', 'tunlink'):
            block = network[network.index("config interface 'wan'"):network.index("config interface 'wan6'")]
            expected = re.search(rf"option {option} '([^']*)'", block).group(1)
            self.assertEqual(uci(f'network.wan.{option}'), expected, option)

    def test_adguard_blocks_the_same_things(self):
        ours = yaml.safe_load((FLINT / 'AdGuardHome/config.yaml').read_text(encoding='utf-8'))
        theirs = yaml.safe_load((OPENWRT / 'adguardhome/adguardhome.yaml').read_text(encoding='utf-8'))
        self.assertEqual(ours['filters'], theirs['filters'])
        self.assertEqual(ours['user_rules'], theirs['user_rules'])
        # GL's integration forwards :53 to this port; AdGuard must not take :53 itself.
        self.assertEqual(ours['dns']['port'], 3053)
        self.assertFalse(ours['dns']['querylog_file_enabled'], 'クエリログを eMMC へ書かない')
        self.assertEqual(ours['users'], [], '認証はファイアウォールと Forward Auth に任せる')


class AddressPlanTests(unittest.TestCase):
    def setUp(self):
        self.network = yaml.safe_load((ROOT / 'platform/terraform/network.yaml').read_text(encoding='utf-8'))

    def test_the_lan_is_the_server_segment(self):
        server = self.network['segments']['server']
        self.assertEqual(uci('network.lan.ipaddr'), server['gateway'])

    def test_the_dhcp_pool_matches_the_declared_range(self):
        dhcp = self.network['dhcp']
        first = int(dhcp['range_start'].split('.')[-1].split('/')[0])
        last = int(dhcp['range_end'].split('.')[-1].split('/')[0])
        self.assertEqual(int(uci('dhcp.lan.start')), first)
        self.assertEqual(int(uci('dhcp.lan.limit')), last - first + 1)

    def test_segments_do_not_overlap(self):
        import ipaddress
        nets = [ipaddress.ip_network(s['prefix']) for s in self.network['segments'].values()]
        for i, a in enumerate(nets):
            for b in nets[i + 1:]:
                self.assertFalse(a.overlaps(b), f'{a} overlaps {b}')
        for name, segment in self.network['segments'].items():
            self.assertEqual(int(segment['prefix'].split('.')[2]), segment['vlan_id'], name)


class SafetyTests(unittest.TestCase):
    def test_apply_rolls_back_unless_confirmed(self):
        self.assertIn('cp -a /etc/config "$backup/config"', APPLY)
        self.assertLess(APPLY.index('/etc/shakecloud/rollback-router\n'), APPLY.index('uci commit network'))
        # The deadline counts uptime, so an NTP step after the WAN comes up cannot fire it.
        self.assertIn('/proc/uptime', APPLY)

    def test_ipv6_is_enabled_before_map_e(self):
        # GL.iNet ships with IPv6 disabled on every interface; MAP-E needs it.
        self.assertLess(APPLY.index('/etc/init.d/gl_ipv6 disable'), APPLY.index("uci set network.wan.proto='map'"))
        self.assertIn('net.ipv6.conf.all.disable_ipv6=0', APPLY)

    def test_the_temporary_ssh_rule_is_removed(self):
        self.assertIn("tmp-ssh-oldlan", APPLY)


if __name__ == '__main__':
    unittest.main()


class DmzTests(unittest.TestCase):
    def setUp(self):
        self.script = (FLINT / 'shakecloud/apply-dmz').read_text(encoding='utf-8')
        self.dmz = yaml.safe_load((ROOT / 'platform/terraform/network.yaml').read_text(encoding='utf-8'))['segments']['dmz']

    def test_matches_the_declared_segment(self):
        self.assertIn(f"network.vlan_dmz.vlan='{self.dmz['vlan_id']}'", self.script)
        self.assertIn(f"network.dmz.ipaddr='{self.dmz['gateway']}'", self.script)

    def test_lan4_is_dmz_only_and_k11_gets_it_tagged(self):
        self.assertIn("network.vlan_dmz.ports='4 6t 3t'", self.script)
        self.assertIn("network.vlan_lan.ports='6 7 3t'", self.script)

    def test_the_only_way_into_the_server_segment_is_pkdb(self):
        to_lan = [line for line in self.script.splitlines() if line.startswith(('rule', '\trule')) and 'dest=lan' in line]
        self.assertEqual(len(to_lan), 1)
        self.assertIn('dest_port=5432', to_lan[0])
        self.assertNotIn('dmz_lan', self.script)
