import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'stacks/netbox'
SPEC = importlib.util.spec_from_file_location('netbox_manage', SOURCE / 'manage.py')
netbox = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(netbox)


class NetBoxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patch = patch.object(netbox, 'ROOT', self.root)
        self.patch.start()
        for name in ('.env.example', 'seed_inventory.py', 'seed_terraform_identity.py'):
            shutil.copyfile(SOURCE / name, self.root / name)

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_postgres18_can_traverse_mount_parent(self):
        with patch.object(netbox.os, 'chown'):
            netbox.init()
        parent = self.root / 'storage/postgres'
        self.assertEqual(parent.stat().st_mode & 0o777, 0o755)

    def test_terraform_write_token_is_preserved_on_repeat_seed(self):
        # seed_terraform must not call init(), so create the secrets directory here.
        (self.root / 'secrets').mkdir(mode=0o700)
        with patch.object(netbox, 'compose'):
            netbox.seed_terraform()
            original = (self.root / 'secrets/terraform-token.json').read_bytes()
            netbox.seed_terraform()
        self.assertEqual(original, (self.root / 'secrets/terraform-token.json').read_bytes())

    def test_terraform_identity_is_separate_from_the_read_only_inventory_identity(self):
        source = (SOURCE / 'seed_terraform_identity.py').read_text()
        self.assertIn("'write_enabled': True", source)
        self.assertIn("username='terraform'", source)
        inventory = (SOURCE / 'seed_inventory.py').read_text()
        self.assertIn("'write_enabled': False", inventory)
        self.assertIn("username='ansible-inventory'", inventory)

    def test_inventory_token_is_preserved_on_repeat_seed(self):
        with patch.object(netbox.os, 'chown'):
            netbox.init()
        with patch.object(netbox, 'compose'):
            netbox.seed('test-host', '192.0.2.10/32')
            original = (self.root / 'secrets/inventory-token.json').read_bytes()
            netbox.seed('test-host', '192.0.2.10/32')
        self.assertEqual(original, (self.root / 'secrets/inventory-token.json').read_bytes())


if __name__ == '__main__':
    unittest.main()
