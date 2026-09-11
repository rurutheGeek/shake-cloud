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


def source(name):
    return (TERRAFORM / name).read_text(encoding='utf-8')


def variable_block(text, name):
    """Return the source of one `variable "<name>" { ... }` declaration."""
    for part in ('\n' + text).split('\nvariable "'):
        if part.startswith(name + '" {'):
            return part
    raise AssertionError(f'variable "{name}" is not declared')


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

    def test_every_flavor_declares_a_balloon_floor(self):
        # Memory is ballooned by default, so a flavor without a floor would
        # silently pin a VM to its ceiling and waste the host's headroom.
        for name, flavor in self.flavors.items():
            self.assertIn('memory_min_mib', flavor, name)
            self.assertLessEqual(flavor['memory_min_mib'], flavor['memory_mib'], name)

    def test_a_host_override_stays_inside_its_own_bounds(self):
        # An override exists so the ledger can follow a VM that was grown by
        # hand. A floor above the ceiling is a typo Proxmox would reject.
        for name, host in self.hosts.items():
            ceiling = host.get('memory_mib', self.flavors[host['flavor']]['memory_mib'])
            floor = host.get('memory_min_mib',
                             self.flavors[host['flavor']]['memory_min_mib'])
            self.assertLessEqual(floor, ceiling, name)

    def test_no_host_claims_a_vmid_that_is_already_taken_outside_the_ledger(self):
        # game1 sits at VMID 100 and Terraform does not manage it. Declaring
        # a host there would make Terraform try to create a VM on top of a
        # running one. pools.yaml records it so the clash is caught here.
        reserved = {entry['vm_id']: entry['name']
                    for entry in load('pools.yaml').get('reserved_vmids', [])}
        for name, host in self.hosts.items():
            self.assertNotIn(host['vm_id'], reserved,
                             f"{name} claims VMID {host['vm_id']}, already used by "
                             f"{reserved.get(host['vm_id'])}")

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



class SiteTests(unittest.TestCase):
    """site.yaml replaces the machine-specific values that used to live in
    terraform.tfvars, so that no one has to retype them per run. Nothing else
    checks that the file still holds what the modules read out of it.
    """

    def setUp(self):
        self.site = load('site.yaml')
        self.bootstrap = source('00-bootstrap/identities.tf')

    def test_every_key_the_modules_read_is_present(self):
        self.assertIn('node_name', self.site)
        for key in ('vm_disks', 'admin_images', 'cloud_images', 'cloud_images_path'):
            self.assertIn(key, self.site['storage'], key)
        for key in ('bridge', 'sdn_zone', 'prefix', 'gateway', 'dns_servers'):
            self.assertIn(key, self.site['network'], key)

    def test_the_cloud_image_store_is_not_shared_with_another_store(self):
        # CloudApiImages carries Datastore.Allocate, which can remove the
        # storage definition itself. Pointing it at the VM disk store would
        # let the user-facing API delete where every platform VM lives; at the
        # admin image store, where the shared official images live.
        cloud = self.site['storage']['cloud_images']
        self.assertNotEqual(cloud, self.site['storage']['vm_disks'])
        self.assertNotEqual(cloud, self.site['storage']['admin_images'])

    def test_every_unmeasured_value_is_one_a_module_checks_for(self):
        # UNMEASURED means "nobody has asked the host yet". A value carrying
        # it must be listed in some module's site_unknown, or the sentinel
        # reaches apply and becomes a storage name that does not exist.
        declared = ''.join(source(f'{module}/{f}') for module, f in
                           (('00-bootstrap', 'pools.tf'), ('10-platform', 'hosts.tf')))
        for section, values in self.site.items():
            if not isinstance(values, dict):
                continue
            for key, value in values.items():
                if value == 'UNMEASURED':
                    self.assertIn(f'"{section}.{key}"', declared,
                                  f'{section}.{key} is UNMEASURED but no module '
                                  'lists it in site_unknown')

    def test_both_modules_stop_before_applying_an_unmeasured_value(self):
        for module in ('00-bootstrap', '10-platform'):
            check = source(f'{module}/site.tf')
            self.assertIn('precondition', check, module)
            self.assertIn('local.site_unknown', check, module)

    def test_no_acl_path_is_typed_by_hand(self):
        # Every cloud ACL path is derived, so a rename in site.yaml cannot
        # leave an ACL pointing at a storage that no longer exists.
        for name in ('cloudapi_vm_storage', 'cloudapi_image_storage',
                     'cloudapi_node_audit', 'cloudapi_network'):
            block = self.bootstrap.split(f'"proxmox_acl" "{name}"')[1].split('\n}')[0]
            self.assertNotIn('var.', block, name)


class ImageTests(unittest.TestCase):
    """The shared cloud image must be declared in Git, not in tfvars.

    It lived in a gitignored terraform.tfvars once. Planning from a machine
    without that file produced `proxmox_download_file.cloud_image["debian13"]
    will be destroyed (because key is not in for_each map)` -- a plan that
    deletes the base image every platform VM is built from. The URL and the
    checksum are published by the distributor; nothing here is secret.
    """

    def setUp(self):
        self.spec = load('images.yaml')

    def test_the_default_image_exists(self):
        self.assertIn(self.spec['default_image'], self.spec['images'])

    def test_every_image_pins_an_exact_build_and_a_checksum(self):
        # `latest` would change what a re-run downloads, and a missing
        # checksum would let it change silently.
        for name, image in self.spec['images'].items():
            self.assertNotIn('latest', image['url'], name)
            self.assertIn(image['file_name'], image['url'], name)
            self.assertGreater(len(image['checksum']), 32, name)

    def test_the_image_declaration_is_not_a_terraform_variable(self):
        # A variable would default to {} on a machine without tfvars, and
        # Terraform reads "no declaration" as "destroy it".
        for module in ('00-bootstrap', '10-platform'):
            self.assertNotIn('variable "cloud_images"', source(f'{module}/variables.tf'))
            self.assertNotIn('variable "image_file_id"', source(f'{module}/variables.tf'))


class AllocationTests(unittest.TestCase):
    """network.yaml decides how the measured prefix is carved up.

    Two writers allocate from this network: admin Terraform for platform VMs
    and the cloud API for user VMs. If their ranges overlap they will hand out
    the same address to different machines, and the collision shows up as an
    intermittent network fault long after the fact.
    """

    def setUp(self):
        self.network = load('network.yaml')
        self.site = load('site.yaml')

    @staticmethod
    def addresses(section):
        import ipaddress
        first = ipaddress.ip_interface(section['range_start']).ip
        last = ipaddress.ip_interface(section['range_end']).ip
        return first, last

    def test_each_range_is_ordered(self):
        for name in ('management', 'cloud'):
            first, last = self.addresses(self.network[name])
            self.assertLess(first, last, name)

    def test_the_two_ranges_do_not_overlap(self):
        management = self.addresses(self.network['management'])
        cloud = self.addresses(self.network['cloud'])
        self.assertTrue(management[1] < cloud[0] or cloud[1] < management[0],
                        f'management {management} overlaps cloud {cloud}')

    def test_every_range_sits_inside_the_measured_prefix(self):
        # A range outside the prefix would be allocated happily by NetBox and
        # then be unreachable, because the guests are on this L2 and no other.
        import ipaddress
        if self.site['network']['prefix'] == 'UNMEASURED':
            self.skipTest('prefix not measured yet')
        network = ipaddress.ip_network(self.site['network']['prefix'])
        for name in ('management', 'cloud'):
            for address in self.addresses(self.network[name]):
                self.assertIn(address, network, f'{name}: {address}')

    def test_the_cloud_prefix_stays_unset_until_the_network_is_split(self):
        # Declaring the same CIDR twice would duplicate it in the ledger.
        # It gets a value only once the cloud VLAN exists.
        if self.network['cloud']['prefix'] is not None:
            self.assertNotEqual(self.network['cloud']['prefix'],
                                self.site['network']['prefix'])


class AccessTests(unittest.TestCase):
    """Public keys belong in Git; their order is load-bearing."""

    def setUp(self):
        self.access = load('access.yaml')

    def test_keys_are_public_keys_and_nothing_else(self):
        # A private key here would be committed in clear. check-publication
        # would catch a PEM block, but not an unlucky paste of something else.
        for key in self.access['admin_ssh_public_keys']:
            self.assertTrue(key.startswith(('ssh-ed25519 ', 'ssh-rsa ', 'ecdsa-')), key[:20])
            self.assertNotIn('PRIVATE', key)

    def test_at_least_one_admin_key_exists(self):
        # An empty list would silently lock everyone out of every new VM.
        self.assertTrue(self.access['admin_ssh_public_keys'])

    def test_the_module_preserves_the_declared_order(self):
        # Proxmox stores the keys as one newline-joined string, so sorting or
        # de-duplicating them rewrites the cloud-init drive of every VM.
        hosts = source('10-platform/hosts.tf')
        block = hosts.split('ssh_public_keys')[1].split(')')[0]
        self.assertIn('concat(', block)
        for forbidden in ('sort(', 'toset('):
            self.assertNotIn(forbidden, block)


class OwnershipBoundaryTests(unittest.TestCase):
    """Guard the ACL side of the boundary PoolTests guards on the pool side.

    pools.yaml keeps `cloud` out of automation_pools, so terraform@pve cannot
    reach user VMs. These check the mirror image: that cloudapi@pve cannot
    reach the platform VMs, and that its privileges stay narrow. Both are
    source-text assertions -- nothing else looks at 00-bootstrap until an
    apply against the real host.
    """

    def setUp(self):
        self.identities = source('00-bootstrap/identities.tf')
        self.roles = source('00-bootstrap/roles.tf')
        self.variables = source('00-bootstrap/variables.tf')

    def test_the_cloud_api_account_reaches_only_the_cloud_pool(self):
        # One ACL, one hardcoded pool. If this ever becomes a for_each over
        # local.automation_pools, the delete API reaches the platform VMs.
        self.assertIn('resource "proxmox_acl" "cloudapi_pool"', self.identities)
        block = self.identities.split('resource "proxmox_acl" "cloudapi_pool"')[1]
        block = block.split('\n}')[0]
        self.assertIn('pool.this["cloud"]', block)
        self.assertNotIn('automation_pools', block)

    def test_the_cloud_api_role_does_not_share_its_privilege_list(self):
        # Sharing var.platform_admin_privileges means widening TerraformAdmin
        # silently widens what a user-facing API can do, and the reverse.
        operator = self.roles.split('"cloud_api_operator"')[1].split('\n}')[0]
        self.assertIn('var.cloud_api_privileges', operator)
        self.assertNotIn('var.platform_admin_privileges', operator)

    def test_the_vm_disk_storage_role_cannot_remove_a_datastore(self):
        # Datastore.Allocate covers the storage definition itself, not just
        # volumes. VM-owned disks delete fine under VM.Config.Disk, so the
        # role that covers user VM disks must not carry it.
        block = variable_block(self.variables, 'cloud_api_storage_privileges')
        self.assertIn('"Datastore.AllocateSpace"', block)
        self.assertNotIn('"Datastore.Allocate"', block)

    def test_the_cloud_api_cannot_clone_or_migrate(self):
        # The API builds every VM from an image; it never clones a template,
        # and there is only one node to migrate between.
        block = variable_block(self.variables, 'cloud_api_privileges')
        self.assertNotIn('"VM.Clone"', block)
        self.assertNotIn('"VM.Migrate"', block)

    def test_the_cloud_api_does_not_touch_the_builtin_cloudinit_drive(self):
        # The seed ISO carries everything, so VM.Config.Cloudinit is dead
        # weight -- and without it nothing can write cicustom by accident.
        block = variable_block(self.variables, 'cloud_api_privileges')
        self.assertNotIn('"VM.Config.Cloudinit"', block)

    def test_the_node_audit_role_is_read_only(self):
        # Admission control needs GET /nodes/<node>/status, which wants
        # Sys.Audit on /nodes/<node> -- outside /pool/cloud. It is the one
        # grant that leaves the pool, so it must stay read-only.
        block = variable_block(self.variables, 'cloud_api_node_audit_privileges')
        self.assertIn('"Sys.Audit"', block)
        self.assertNotIn('"Sys.Modify"', block)
        self.assertNotIn('"Sys.PowerMgmt"', block)

    def test_the_cloud_api_can_attach_a_cdrom(self):
        # Arbitrary user-data rides on a NoCloud seed ISO attached as a
        # CD-ROM, because the upload API refuses content=snippets. Dropping
        # this privilege breaks user-data without breaking VM creation.
        block = variable_block(self.variables, 'cloud_api_privileges')
        self.assertIn('"VM.Config.CDROM"', block)


class ProviderLockTests(unittest.TestCase):
    """Lock files must carry provider hashes for every machine that runs
    Terraform, not just the one that last ran `init`.

    An h1 hash is per-platform. A lock recorded on one OS makes `init` fail on
    another with "does not match any of the checksums recorded in the
    dependency lock file", and the only ways out are `-upgrade` (which defeats
    the pinning) or deleting the lock. That blocks an unattended runner, and
    it blocks whoever is not on the same OS as the last committer.

    Regenerate with, from each module directory:
        terraform providers lock \
          -platform=linux_amd64 -platform=windows_amd64 \
          -platform=darwin_arm64 -platform=darwin_amd64
    """

    PLATFORMS = 4

    def test_every_provider_is_locked_for_every_supported_platform(self):
        locks = sorted(TERRAFORM.glob('*/.terraform.lock.hcl'))
        self.assertTrue(locks, 'no lock files found')
        for lock in locks:
            text = lock.read_text(encoding='utf-8')
            for block in text.split('provider "')[1:]:
                name = block.split('"', 1)[0]
                self.assertGreaterEqual(
                    block.count('"h1:'), self.PLATFORMS,
                    f'{lock.parent.name}: {name} is locked for fewer than '
                    f'{self.PLATFORMS} platforms; see this test docstring')


if __name__ == '__main__':
    unittest.main()
