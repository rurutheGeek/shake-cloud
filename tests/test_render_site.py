import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('render_site', ROOT / 'render_site.py')
render_site = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render_site)

# The declarations themselves live in the platform repository, so these tests
# feed subnets() a synthetic network instead of reading platform/terraform.
NETWORK = {
    'vlan': {'cloud': {'vlan_id': 110}},
    'cloud': {'range_start': '10.0.10.100'},
    'segments': {
        'server': {'prefix': '10.0.10.0/24', 'gateway': '10.0.10.1', 'vlan_id': 110,
                   'bridge_tag': 0},
        'personal': {'prefix': '10.0.20.0/24', 'gateway': '10.0.20.1', 'vlan_id': 120},
        'dmz': {'prefix': '10.0.30.0/24', 'gateway': '10.0.30.1', 'vlan_id': 130,
                'cloud': {'range_start': '10.0.30.100'}},
        'reserved': {'prefix': '10.0.40.0/24', 'gateway': '10.0.40.1', 'vlan_id': 140,
                     'reserved': True},
    },
}


class SubnetTests(unittest.TestCase):
    """The API learns the segments of the network from network.yaml."""

    def setUp(self):
        self.subnets = {entry['name']: entry for entry in render_site.subnets(NETWORK)}

    def test_the_server_segment_is_the_default_and_keeps_the_cloud_range(self):
        defaults = [name for name, entry in self.subnets.items() if entry.get('default')]
        self.assertEqual(defaults, ['server'])
        self.assertEqual(self.subnets['server']['ip_range_start'], NETWORK['cloud']['range_start'])
        # Untagged on the bridge until the cloud VLAN is set, VLAN number or not.
        self.assertEqual(self.subnets['server']['bridge_tag'], NETWORK['vlan']['cloud']['vlan_id'] or 0)

    def test_only_segments_with_a_cloud_range_take_instances(self):
        for name in ('personal', 'reserved'):
            self.assertNotIn('ip_range_start', self.subnets[name], name)
        self.assertEqual(self.subnets['dmz']['ip_range_start'], '10.0.30.100')

    def test_a_reserved_segment_keeps_its_marker(self):
        self.assertEqual(self.subnets['reserved']['description'], 'reserved')
        self.assertNotIn('description', self.subnets['dmz'])

    def test_every_segment_keeps_its_shape(self):
        self.assertEqual(list(self.subnets), ['server', 'personal', 'dmz', 'reserved'])
        for name, entry in self.subnets.items():
            self.assertEqual(entry['prefix'], NETWORK['segments'][name]['prefix'])
            self.assertEqual(entry['gateway'], NETWORK['segments'][name]['gateway'])
            self.assertEqual(entry['vlan_id'], NETWORK['segments'][name]['vlan_id'])


if __name__ == '__main__':
    unittest.main()
