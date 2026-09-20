"""Check the post-cutover verification tool's calculations.

The tool runs against a live network, but its arithmetic (PSID extraction,
port-set membership, MTU binary search) can be pinned here. A wrong PSID check
would either pass a broken MAP-E setup or fail a healthy one at the switch.
"""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'verify_router', ROOT / 'tools/verify-router.py')
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


class UciTests(unittest.TestCase):
    def setUp(self):
        self.wan = verify.load_uci(ROOT / 'platform/openwrt/rootfs/etc/shakecloud/config/network')

    def test_it_reads_the_declared_map_e_values(self):
        self.assertEqual(self.wan['proto'], 'map')
        self.assertEqual(self.wan['maptype'], 'map-e')
        self.assertEqual(self.wan['offset'], '4')
        self.assertEqual(self.wan['psidlen'], '8')
        self.assertEqual(self.wan['mtu'], '1460')

    def test_the_rule_networks_come_from_the_file(self):
        self.assertEqual(str(verify.rule_ipv4_network(self.wan)), '106.72.0.0/15')
        self.assertEqual(str(verify.rule_ipv6_network(self.wan)), '240b:10::/31')


class PsidTests(unittest.TestCase):
    # JPNE: offset=4, psidlen=8, so the PSID is bits 4..11 of the port.
    PSID = 0x2C

    def port(self, a, j):
        return (a << 12) | (self.PSID << 4) | j

    def test_the_psid_is_the_middle_eight_bits(self):
        self.assertEqual(verify.psid_of(self.port(1, 0), 4, 8), self.PSID)
        self.assertEqual(verify.psid_of(self.port(15, 15), 4, 8), self.PSID)

    def test_assigned_ports_are_inside_the_set(self):
        for a in range(1, 16):
            for j in range(16):
                self.assertTrue(verify.port_in_set(self.port(a, j), self.PSID, 4, 8), (a, j))

    def test_the_system_port_block_is_not_assigned(self):
        # A=0 covers 0-4095; N06 measured only 15 blocks (240 ports).
        self.assertFalse(verify.port_in_set(self.port(0, 0), self.PSID, 4, 8))

    def test_another_psid_is_outside_the_set(self):
        other = (1 << 12) | ((self.PSID + 1) << 4)
        self.assertFalse(verify.port_in_set(other, self.PSID, 4, 8))

    def test_a_port_that_is_not_a_port_is_outside(self):
        self.assertFalse(verify.port_in_set(70000, self.PSID, 4, 8))


class RuleDataTests(unittest.TestCase):
    RULES = """rule=type=map-e,ipv6prefix=240b:10::,prefix6len=31
RULE_1_FMR=0
RULE_1_EALEN=25
RULE_1_PSIDLEN=8
RULE_1_OFFSET=4
RULE_1_IPV4ADDR=106.72.1.2
RULE_1_PORTSETS='2048-2063 6144-6159 10240-10255'
RULE_BMR=1
RULE_COUNT=1
"""

    def test_port_sets_parse(self):
        rule = verify.parse_rule_data(self.RULES)
        self.assertEqual(rule['RULE_1_IPV4ADDR'], '106.72.1.2')
        ranges = verify.parse_portsets(rule['RULE_1_PORTSETS'])
        self.assertEqual(ranges, [(2048, 2063), (6144, 6159), (10240, 10255)])

    def test_the_psid_is_recovered_from_the_ranges(self):
        # mapcalc starts at A=1, so 4096 | PSID<<4 is the first range.
        ranges = [(0x1 << 12 | 0x2C << 4, (0x1 << 12) | (0x2C << 4) | 15),
                  (0xF << 12 | 0x2C << 4, (0xF << 12) | (0x2C << 4) | 15)]
        self.assertEqual(verify.psid_from_portsets(ranges, 4, 8), 0x2C)


class PmtuSearchTests(unittest.TestCase):
    def test_the_search_finds_the_largest_passing_payload(self):
        original = verify.ping_ok
        verify.ping_ok = lambda target, size: size <= 1432
        try:
            self.assertEqual(verify.largest_payload('192.0.2.1'), 1432)
        finally:
            verify.ping_ok = original

    def test_no_reply_at_all_returns_none(self):
        original = verify.ping_ok
        verify.ping_ok = lambda target, size: False
        try:
            self.assertIsNone(verify.largest_payload('192.0.2.1'))
        finally:
            verify.ping_ok = original


if __name__ == '__main__':
    unittest.main()
