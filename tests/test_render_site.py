import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
TERRAFORM = ROOT / 'platform/terraform'
SPEC = importlib.util.spec_from_file_location('render_site', ROOT / 'cloud/render_site.py')
render_site = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render_site)


class RenderSiteTests(unittest.TestCase):
    site = render_site.render(TERRAFORM)

    def yaml(self, name):
        return yaml.safe_load((TERRAFORM / name).read_text())

    def test_the_values_come_from_the_declarations(self):
        # Nothing here may be a second copy: every value is checked against the
        # file Terraform reads.
        site, pools = self.yaml('site.yaml'), self.yaml('pools.yaml')
        network, flavors = self.yaml('network.yaml'), self.yaml('flavors.yaml')
        self.assertEqual(self.site['node'], site['node_name'])
        self.assertEqual(self.site['storage'], {'vm_disks': site['storage']['vm_disks'],
                                                'images': site['storage']['cloud_images']})
        self.assertEqual(self.site['network']['bridge'], site['network']['bridge'])
        self.assertEqual(self.site['network']['gateway'], site['network']['gateway'])
        self.assertEqual(self.site['network']['dns_servers'], site['network']['dns_servers'])
        self.assertEqual(self.site['network']['ip_range_start'], network['cloud']['range_start'])
        self.assertEqual(self.site['vmid_from'], pools['pools']['cloud']['vmid_from'])
        self.assertEqual(self.site['vmid_to'], pools['pools']['cloud']['vmid_to'])
        self.assertEqual(set(self.site['instance_types']), set(flavors['flavors']))

    def test_images_point_at_the_store_the_cloud_account_can_read(self):
        images = self.yaml('images.yaml')['images']
        store = self.yaml('site.yaml')['storage']['cloud_images']
        expected = {f'img-{name}' for name, image in images.items() if image.get('shared_with_cloud')}
        self.assertEqual(set(self.site['images']), expected)
        self.assertTrue(expected, 'no image is shared with the cloud')
        for image_id, image in self.site['images'].items():
            self.assertTrue(image['volume'].startswith(f'{store}:import/'), image_id)
            self.assertIn(images[image['name']]['file_name'], image['volume'])

    def test_limits_come_from_cloud_yaml(self):
        cloud = self.yaml('cloud.yaml')
        self.assertEqual(self.site['limits']['account_quota'], cloud['account_quota'])
        self.assertEqual(self.site['limits']['capacity'], cloud['capacity'])
        self.assertEqual(self.site['limits']['volume_size_gib'], cloud['volume_size_gib'])
        self.assertEqual(self.site['probe_vmids'], cloud['probe_vmids'])
        self.assertEqual(self.site['volume_holder_vmid'], cloud['volume_holder_vmid'])
        # The probe VMIDs must sit inside the pool, or reserving them means nothing.
        for vmid in self.site['probe_vmids']:
            self.assertTrue(self.site['vmid_from'] <= vmid <= self.site['vmid_to'], vmid)
        # Same for the holder: outside the pool it sits where the API's ACLs
        # cannot reach, and colliding with a probe VMID means a probe run
        # could delete or overwrite the volume holder.
        self.assertTrue(self.site['vmid_from'] <= self.site['volume_holder_vmid'] <= self.site['vmid_to'])
        self.assertNotIn(self.site['volume_holder_vmid'], self.site['probe_vmids'])

    def test_the_output_is_json_the_api_can_read(self):
        # site.Load refuses a half-rendered file; keep the shape it expects.
        encoded = json.loads(json.dumps(self.site))
        for key in ('node', 'pool', 'vmid_from', 'vmid_to', 'storage', 'network', 'images', 'instance_types', 'limits'):
            self.assertIn(key, encoded)

    def test_an_unmeasured_site_stops_instead_of_guessing(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ('site.yaml', 'pools.yaml', 'network.yaml', 'images.yaml', 'flavors.yaml', 'cloud.yaml'):
                (Path(directory) / name).write_text((TERRAFORM / name).read_text())
            broken = yaml.safe_load((TERRAFORM / 'site.yaml').read_text())
            broken['storage']['vm_disks'] = 'UNMEASURED'
            (Path(directory) / 'site.yaml').write_text(yaml.safe_dump(broken))
            with self.assertRaises(SystemExit):
                render_site.render(directory)

    def test_a_holder_outside_the_pool_range_stops_rendering(self):
        # A holder outside 5000-5999 would sit where the cloud API's ACLs
        # cannot reach it; catch that at render time, not at first volume detach.
        with tempfile.TemporaryDirectory() as directory:
            for name in ('site.yaml', 'pools.yaml', 'network.yaml', 'images.yaml', 'flavors.yaml', 'cloud.yaml'):
                (Path(directory) / name).write_text((TERRAFORM / name).read_text())
            broken = yaml.safe_load((TERRAFORM / 'cloud.yaml').read_text())
            broken['volume_holder_vmid'] = 1
            (Path(directory) / 'cloud.yaml').write_text(yaml.safe_dump(broken))
            with self.assertRaises(SystemExit):
                render_site.render(directory)

    def test_a_holder_equal_to_a_probe_vmid_stops_rendering(self):
        # The probe script deletes and recreates its VMIDs; a holder sharing
        # one would lose its volumes the next time a probe runs.
        with tempfile.TemporaryDirectory() as directory:
            for name in ('site.yaml', 'pools.yaml', 'network.yaml', 'images.yaml', 'flavors.yaml', 'cloud.yaml'):
                (Path(directory) / name).write_text((TERRAFORM / name).read_text())
            broken = yaml.safe_load((TERRAFORM / 'cloud.yaml').read_text())
            broken['volume_holder_vmid'] = broken['probe_vmids'][0]
            (Path(directory) / 'cloud.yaml').write_text(yaml.safe_dump(broken))
            with self.assertRaises(SystemExit):
                render_site.render(directory)


if __name__ == '__main__':
    unittest.main()
