"""Guard the media-01 VM declaration (I02).

The module is applied by hand against a live cloud API, so a wrong size, a
missing data-disk guard, or a secret in Git would only show up during apply.
These are source-text assertions, in the same spirit as
test_platform_inventory.py: nothing here reaches the cloud.
"""
from pathlib import Path
import re
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'platform/terraform/services/media'
TERRAFORM = ROOT / 'platform/terraform'


def source(name):
    return (MODULE / name).read_text(encoding='utf-8')


def variable_block(text, name):
    """Return the source of one `variable "<name>" { ... }` declaration."""
    for part in ('\n' + text).split('\nvariable "'):
        if part.startswith(name + '" {'):
            return part
    raise AssertionError(f'variable "{name}" is not declared')


def default_of(text, name):
    match = re.search(r'default\s*=\s*(\d+)', variable_block(text, name))
    if not match:
        raise AssertionError(f'variable "{name}" has no numeric default')
    return int(match.group(1))


class SizeTests(unittest.TestCase):
    """The starting budget is 4vCPU / 6GiB / OS32GiB + data64GiB.

    It is a budget, not the measured value, so a change is allowed -- but it
    must be a deliberate edit, not a copied instance_type.
    """

    def setUp(self):
        self.variables = source('variables.tf')
        self.main = source('main.tf')

    def test_the_starting_sizes_are_explicit(self):
        self.assertEqual(default_of(self.variables, 'vcpus'), 4)
        self.assertEqual(default_of(self.variables, 'memory_mib'), 6144)
        self.assertEqual(default_of(self.variables, 'root_disk_gib'), 32)
        self.assertEqual(default_of(self.variables, 'data_disk_gib'), 64)

    def test_it_does_not_use_an_instance_type_preset(self):
        self.assertNotRegex(self.main, r'^\s*instance_type\s*=')

    def test_memory_floor_stays_below_the_ceiling(self):
        ceiling = default_of(self.variables, 'memory_mib')
        floor = default_of(self.variables, 'memory_min_mib')
        self.assertLessEqual(floor, ceiling)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.versions = source('versions.tf')

    def test_the_state_key_is_owned_by_this_service(self):
        # I05 keys service states as shake-cloud/services/<name>/...
        self.assertIn('key                         = "shake-cloud/services/media/terraform.tfstate"',
                      self.versions)

    def test_no_world_readable_state_is_committed(self):
        for name in ('terraform.tfstate', 'terraform.tfvars'):
            self.assertFalse((MODULE / name).exists(),
                             f'{name} must not be committed')


class DataDiskTests(unittest.TestCase):
    """The data disk carries the library. Losing it is the worst failure here."""

    def setUp(self):
        self.main = source('main.tf')
        self.init = source('cloud-init.yaml')

    def test_the_volume_is_guarded_from_destroy(self):
        block = self.main.split('resource "shakecloud_volume" "data"')[1].split('\n}')[0]
        self.assertIn('prevent_destroy = true', block)

    def test_the_guest_mounts_by_a_stable_path(self):
        # The device name (vda/vdb) is not ours to predict; the serial is.
        self.assertIn('data_device = "/dev/disk/by-id/virtio-', self.main)
        self.assertIn('shakecloud_volume.data.serial', self.main)
        self.assertIn('${data_device}', self.init)
        self.assertIn('${data_mount_path}', self.init)

    def test_an_existing_filesystem_is_never_overwritten(self):
        format_at = self.init.index('mkfs.ext4')
        self.assertIn('if ! blkid', self.init[:format_at])

    def test_docker_waits_for_the_mount(self):
        # Without this ordering a missing disk would silently move the
        # library onto the root disk.
        self.assertIn('Requires=media-data-mount.service', self.init)
        self.assertIn('Before=docker.service', self.init)
        self.assertIn('exit 1', self.init)


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.main = source('main.tf')

    def test_the_lan_cidr_comes_from_site_yaml(self):
        # Two writers of 192.168.10.0/24 would drift apart.
        self.assertIn('site.yaml', self.main)
        self.assertIn('local.site.network.prefix', self.main)

    def test_only_ssh_the_web_ports_and_localsend_are_opened_to_the_lan(self):
        ports = sorted(int(value) for value in
                       re.findall(r'from_port\s*=\s*(\d+)', self.main))
        self.assertEqual(ports, [22, 80, 443, 53317])
        self.assertEqual(len(re.findall(r'cidr\s*=\s*local\.lan_cidr', self.main)), 4)
        self.assertNotIn('0.0.0.0/0', self.main)


class OwnershipTests(unittest.TestCase):
    def test_media_is_not_declared_among_the_platform_hosts(self):
        hosts = yaml.safe_load((TERRAFORM / 'hosts.yaml').read_text(encoding='utf-8'))
        self.assertNotIn('media-01', hosts['hosts'])
        self.assertNotIn('media', (TERRAFORM / '10-platform/hosts.tf').read_text(encoding='utf-8'))


class SecretTests(unittest.TestCase):
    def test_no_private_key_or_credential_is_in_the_module(self):
        for path in MODULE.glob('*'):
            # .terraform/ appears once init has run; it is gitignored, not source.
            if path.name == 'README.md' or not path.is_file():
                continue
            text = path.read_text(encoding='utf-8')
            self.assertNotIn('PRIVATE KEY', text, path.name)
            self.assertNotIn('AKIA', text, path.name)


if __name__ == '__main__':
    unittest.main()
