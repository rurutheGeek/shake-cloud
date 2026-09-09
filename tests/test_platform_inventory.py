"""Keep the declarative platform inputs consistent with each other.

hosts.yaml, pools.yaml, flavors.yaml and tags.yaml are read by Terraform and
by the Ansible dynamic inventory. Nothing else checks that they agree, and a
mismatch only shows up during a real apply against the host.
"""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TERRAFORM = ROOT / 'platform/terraform'


def load(name):
    return yaml.safe_load((TERRAFORM / name).read_text(encoding='utf-8'))


class PoolTests(unittest.TestCase):
    def setUp(self):
        self.spec = load('pools.yaml')

    def test_cloud_pool_is_not_reachable_by_the_automation_user(self):
        # The whole point of the reserved pool: a future user-facing delete API
        # must not be able to reach the platform VMs, and vice versa.
        self.assertIn('cloud', self.spec['pools'])
        self.assertNotIn('cloud', self.spec['automation_pools'])

    def test_automation_pools_exist(self):
        for name in self.spec['automation_pools']:
            self.assertIn(name, self.spec['pools'])

    def test_vmid_ranges_do_not_overlap(self):
        ranges = sorted((p['vmid_from'], p['vmid_to'], name)
                        for name, p in self.spec['pools'].items())
        for (_, first_to, first), (second_from, _, second) in zip(ranges, ranges[1:]):
            self.assertLess(first_to, second_from, f'{first} overlaps {second}')

    def test_every_range_is_ordered(self):
        for name, pool in self.spec['pools'].items():
            self.assertLess(pool['vmid_from'], pool['vmid_to'], name)


class HostTests(unittest.TestCase):
    def setUp(self):
        self.hosts = load('hosts.yaml')['hosts']
        self.pools = load('pools.yaml')['pools']
        self.flavors = load('flavors.yaml')['flavors']
        self.tags = load('tags.yaml')['tags']

    def test_every_vmid_is_inside_its_pool_range(self):
        for name, host in self.hosts.items():
            pool = self.pools[host['pool']]
            self.assertGreaterEqual(host['vm_id'], pool['vmid_from'], name)
            self.assertLessEqual(host['vm_id'], pool['vmid_to'], name)

    def test_vmids_are_unique(self):
        used = [host['vm_id'] for host in self.hosts.values()]
        self.assertEqual(len(used), len(set(used)))

    def test_no_host_claims_the_reserved_cloud_pool(self):
        for name, host in self.hosts.items():
            self.assertNotEqual(host['pool'], 'cloud', name)

    def test_flavors_and_tags_are_declared(self):
        for name, host in self.hosts.items():
            self.assertIn(host['flavor'], self.flavors, name)
            for tag in host.get('tags', []):
                self.assertIn(tag, self.tags, f'{name} uses an undeclared tag')

    def test_hosts_that_are_started_on_demand_do_not_autostart(self):
        # dev and lab VMs exist inside a fixed RAM budget; they must be
        # releasable. See docs/architecture/operations.md.
        for name, host in self.hosts.items():
            if host['pool'] in ('dev', 'lab'):
                self.assertFalse(host.get('on_boot', False), name)


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tags = load('tags.yaml')['tags']
        self.inventory = yaml.safe_load(
            (ROOT / 'platform/ansible/inventory.netbox.yml').read_text(encoding='utf-8'))

    def test_every_tag_group_exists_in_the_dynamic_inventory(self):
        for tag, spec in self.tags.items():
            group = spec['ansible_group']
            if group is None:
                continue
            self.assertIn(group, self.inventory['groups'], tag)
            self.assertIn(f"'{tag}'", self.inventory['groups'][group])

    def test_the_media_group_expression_is_unchanged(self):
        # Existing playbooks target `hosts: media`; widening or narrowing this
        # expression silently changes what a redeploy touches.
        self.assertEqual(
            self.inventory['groups']['media'],
            "'media-stack' in tags or 'media-stack' in "
            "(tags | map(attribute='slug', default='') | list)")

    def test_the_inventory_no_longer_filters_on_the_media_tag(self):
        keys = [key for entry in self.inventory['query_filters'] for key in entry]
        self.assertNotIn('tag', keys)


if __name__ == '__main__':
    unittest.main()
