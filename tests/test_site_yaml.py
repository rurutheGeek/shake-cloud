"""Check that site.yaml is derived from the host rather than guessed.

The values Terraform needs exist only on the Proxmox host. Guessing them is
how you get an ACL pointing at a storage that does not exist, reported by
Proxmox as a permission error three steps later. These tests pin the
selection rules, including the cases where the honest answer is "the host
offers two candidates, a human has to choose".
"""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('site_yaml', ROOT / 'tools/site-yaml.py')
site = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(site)

INTERFACES = """auto lo
iface lo inet loopback

iface enp1s0 inet manual

auto vmbr0
iface vmbr0 inet static
        address 192.168.10.126/24
        gateway 192.168.10.1
        bridge-ports enp1s0
        bridge-stp off
        bridge-fd 0
        bridge-vlan-aware yes
        bridge-vids 2-4094
"""


def facts(storage=None, nodes=None, interfaces=INTERFACES, zones='[]'):
    """The shape survey-pve.yml writes: command output, mostly JSON strings."""
    return {
        'nodes_json': json.dumps(nodes or [{'node': 'apextox', 'status': 'online'}]),
        'storage_json': json.dumps(storage or [
            {'storage': 'local', 'type': 'dir', 'content': 'iso,vztmpl,backup,import'},
            {'storage': 'local-lvm', 'type': 'lvmthin', 'content': 'rootdir,images'},
        ]),
        'interfaces_file': interfaces,
        'sdn_zones': zones,
    }


def build(**kwargs):
    node = kwargs.pop('node', None)
    return site.from_survey(facts(**kwargs), node)


class SelectionTests(unittest.TestCase):
    def test_a_plain_single_node_host_is_fully_determined(self):
        result = build()
        self.assertEqual(result['node_name'], 'apextox')
        self.assertEqual(result['vm_disks'], 'local-lvm')
        self.assertEqual(result['admin_images'], 'local')
        self.assertEqual(result['bridge'], 'vmbr0')
        self.assertEqual(result['bridge_vlan_aware'], 'true')
        self.assertEqual(result['sdn_zone'], 'localnetwork')

    def test_two_image_stores_refuse_to_guess_and_name_both(self):
        # Choosing silently would put user VM disks somewhere the operator
        # never intended, and the mistake only shows up as a full disk.
        with self.assertRaises(site.Ambiguous) as raised:
            build(storage=[
                {'storage': 'local-lvm', 'content': 'rootdir,images'},
                {'storage': 'fast-nvme', 'content': 'images'},
                {'storage': 'local', 'content': 'import'},
            ])
        self.assertIn('local-lvm', str(raised.exception))
        self.assertIn('fast-nvme', str(raised.exception))

    def test_the_cloud_image_store_is_not_a_candidate_for_the_admin_store(self):
        # 00-bootstrap creates cloud-images with content import,iso. Without
        # excluding it, running this a second time would suddenly report two
        # candidates and refuse -- for a storage this repo created itself.
        result = build(storage=[
            {'storage': 'local', 'content': 'iso,backup,import'},
            {'storage': 'cloud-images', 'content': 'import,iso'},
            {'storage': 'local-lvm', 'content': 'images'},
        ])
        self.assertEqual(result['admin_images'], 'local')

    def test_a_bridge_with_no_physical_port_is_not_a_candidate(self):
        # An internal-only bridge carries nothing off the host, so a VM
        # attached to it cannot reach the LAN or be reached from it.
        interfaces = INTERFACES + """
auto vmbr1
iface vmbr1 inet manual
        bridge-stp off
"""
        self.assertEqual(build(interfaces=interfaces)['bridge'], 'vmbr0')

    def test_a_guest_link_bridge_without_a_host_address_is_not_a_candidate(self):
        # The router VM's WAN bridge (vmbr1, nic0) has physical ports but no
        # host address. It is not where the management prefix lives, so adding
        # it must not make site.yaml refuse to regenerate.
        interfaces = INTERFACES + """
auto vmbr1
iface vmbr1 inet manual
        bridge-ports nic0
"""
        self.assertEqual(build(interfaces=interfaces)['bridge'], 'vmbr0')

    def test_two_addressed_bridges_refuse_to_guess(self):
        # Two bridges both claiming to carry the host's address is genuinely
        # ambiguous; naming them is the honest answer.
        interfaces = INTERFACES + """
auto vmbr1
iface vmbr1 inet static
        address 10.0.0.1/24
        bridge-ports nic0
"""
        with self.assertRaises(site.Ambiguous):
            build(interfaces=interfaces)

    def test_a_named_sdn_zone_wins_over_the_implicit_default(self):
        result = build(zones=json.dumps([{'zone': 'lanzone', 'type': 'simple'}]))
        self.assertEqual(result['sdn_zone'], 'lanzone')

    def test_more_than_one_node_needs_an_explicit_choice(self):
        nodes = [{'node': 'apextox'}, {'node': 'second'}]
        with self.assertRaises(site.Ambiguous):
            build(nodes=nodes)
        self.assertEqual(build(nodes=nodes, node='second')['node_name'], 'second')


class VlanTests(unittest.TestCase):
    def test_a_vlan_aware_bridge_is_detected(self):
        self.assertTrue(site.vlan_aware(site.bridges_from_interfaces(INTERFACES), 'vmbr0'))

    def test_a_bridge_without_the_flag_is_not_vlan_aware(self):
        # The VLAN phase needs this to be true before it can tag anything.
        plain = INTERFACES.replace('        bridge-vlan-aware yes\n', '')
        self.assertFalse(site.vlan_aware(site.bridges_from_interfaces(plain), 'vmbr0'))


class ApiTests(unittest.TestCase):
    """The API path must agree with the survey path on the same host."""

    API = {
        'nodes': [{'node': 'apextox'}],
        'storage': [{'storage': 'local', 'content': 'backup,import,vztmpl,iso'},
                    {'storage': 'local-lvm', 'content': 'images,rootdir'}],
        'network': [{'iface': 'lo', 'type': 'loopback'},
                    {'iface': 'nic1', 'type': 'eth'},
                    {'iface': 'vmbr0', 'type': 'bridge', 'bridge_ports': 'nic1',
                     'bridge_vlan_aware': '1', 'cidr': '192.168.10.126/24',
                     'gateway': '192.168.10.1'}],
        'sdn_zones': [],
    }

    def test_the_api_and_the_survey_reach_the_same_answer(self):
        # Two sources, one truth. If they can disagree, neither is trustworthy.
        self.assertEqual(site.from_api(self.API), build())

    def test_the_prefix_is_the_network_not_the_host_address(self):
        # Proxmox reports the host's own address; a prefix of
        # 192.168.10.126/24 would be a ledger entry nobody can allocate from.
        self.assertEqual(site.from_api(self.API)['prefix'], '192.168.10.0/24')

    def test_the_node_resolvers_win_over_the_gateway_fallback(self):
        data = dict(self.API, dns={'dns1': '10.0.0.53', 'dns2': '10.0.0.54'})
        self.assertIn('10.0.0.53', site.from_api(data)['dns_servers'])
        self.assertIn('10.0.0.54', site.from_api(data)['dns_servers'])

    def test_a_bridge_with_no_port_is_dropped_from_the_api_answer(self):
        data = dict(self.API, network=self.API['network'] + [
            {'iface': 'vmbr1', 'type': 'bridge', 'bridge_ports': '',
             'cidr': '10.0.0.1/24'}])
        self.assertEqual(site.from_api(data)['bridge'], 'vmbr0')

    def test_the_api_reports_vlan_awareness(self):
        bridges = site.bridges_from_api(self.API['network'])
        self.assertTrue(site.vlan_aware(bridges, 'vmbr0'))
        unaware = site.bridges_from_api([dict(self.API['network'][2], bridge_vlan_aware='0')])
        self.assertFalse(site.vlan_aware(unaware, 'vmbr0'))


class OutputTests(unittest.TestCase):
    def test_the_rendered_file_parses_and_carries_no_sentinel(self):
        import yaml
        rendered = yaml.safe_load(site.TEMPLATE.format(**build()))
        self.assertNotIn('UNMEASURED', str(rendered))
        self.assertEqual(rendered['storage']['cloud_images'], site.CLOUD_IMAGES_STORE)
        self.assertEqual(rendered['network']['bridge'], 'vmbr0')

    def test_the_rendered_file_has_the_shape_terraform_reads(self):
        import yaml
        committed = yaml.safe_load(
            (ROOT / 'platform/terraform/site.yaml').read_text(encoding='utf-8'))
        rendered = yaml.safe_load(site.TEMPLATE.format(**build()))
        self.assertEqual(sorted(rendered), sorted(committed))
        self.assertEqual(sorted(rendered['storage']), sorted(committed['storage']))
        self.assertEqual(sorted(rendered['network']), sorted(committed['network']))


if __name__ == '__main__':
    unittest.main()
