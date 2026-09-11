import json
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class DocsSiteTests(unittest.TestCase):
    def test_every_service_is_pinned_to_a_digest(self):
        # The role starts the stack with compose.lock.yaml; a service missing from
        # the lock would silently follow the moving nginx:alpine tag.
        services = yaml.safe_load((ROOT / 'stacks/docs/compose.yaml').read_text())['services']
        lock = json.loads((ROOT / 'stacks/docs/compose.lock.yaml').read_text())['services']
        self.assertEqual(set(services), set(lock))
        for entry in lock.values():
            self.assertIn('@sha256:', entry['image'])

    def test_the_site_is_served_read_only(self):
        # Pages come only from the Git docs/ build; the web server must not be
        # able to alter what it serves.
        web = yaml.safe_load((ROOT / 'stacks/docs/compose.yaml').read_text())['services']['web']
        self.assertTrue(web['read_only'])
        self.assertTrue(all(volume.endswith(':ro') for volume in web['volumes']))

    def test_the_build_refuses_broken_links_before_publishing(self):
        tasks = (ROOT / 'platform/ansible/roles/docs_site/tasks/main.yml').read_text()
        self.assertIn('--strict', tasks)


if __name__ == '__main__':
    unittest.main()
