import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('stack', Path(__file__).resolve().parents[1] / 'scripts/stack.py')
stack = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stack)
PROJECT = stack.ROOT


class StackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.root_patch = patch.object(stack, 'ROOT', self.root)
        self.root_patch.start()
        shutil.copy(PROJECT / '.env.example', self.root / '.env.example')
        shutil.copy(PROJECT / '.env.example', self.root / '.env')

    def tearDown(self):
        self.root_patch.stop()
        self.tmp.cleanup()

    def test_secret_generation_is_not_repeated(self):
        with patch.object(stack.os, 'geteuid', return_value=0), patch.object(stack.os, 'chown'):
            stack.init()
            before = {p.name: p.read_text() for p in (self.root / 'secrets').iterdir()}
            stack.init()
        self.assertEqual(before, {p.name: p.read_text() for p in (self.root / 'secrets').iterdir()})
        self.assertEqual(len(before), 3)
        self.assertEqual((self.root / 'secrets').stat().st_mode & 0o777, 0o700)

    def test_nested_storage_is_rejected(self):
        (self.root / '.env').write_text('STORAGE_ROOT=./data\nLIBRARY_ROOT=./data/library\n')
        with self.assertRaises(ValueError):
            stack.paths()

    def test_existing_mount_access_is_preserved(self):
        mounts = [{'mount_point': '/' + n, 'configuration': {'datadir': '/library/' + n}}
                  for n in ('books', 'music')]
        with patch.object(stack, 'occ', return_value=SimpleNamespace(stdout=json.dumps(mounts))) as occ:
            stack.setup()
        self.assertFalse(any(c.args[0] == 'files_external:create' for c in occ.call_args_list))

    def test_mounts_are_restricted_at_creation(self):
        with patch.object(stack, 'occ', return_value=SimpleNamespace(stdout='[]')) as occ:
            stack.setup()
        creates = [c for c in occ.call_args_list if c.args[0] == 'files_external:create']
        self.assertEqual(len(creates), 2)
        for call in creates:
            self.assertIn('--applicable-user', call.args)
            self.assertEqual(call.args[-1], 'admin')

    def test_nextcloud_apps_install_missing_and_enable_disabled(self):
        state = json.dumps({'enabled': {'files': '1.0'}, 'disabled': {'tasks': '1.0'}})
        with patch.object(stack, 'occ', side_effect=[
            SimpleNamespace(stdout=state),
            SimpleNamespace(stdout=''),
            SimpleNamespace(stdout=''),
        ]) as occ:
            stack.apps('calendar,tasks,files')
        calls = [call.args for call in occ.call_args_list]
        self.assertIn(('app:install', 'calendar'), calls)
        self.assertIn(('app:enable', 'tasks'), calls)
        self.assertNotIn(('app:enable', 'files'), calls)

    def test_conflicting_mount_is_not_replaced(self):
        raw = [{'mount_point': '/books', 'configuration': {'datadir': '/other'}}]
        with patch.object(stack, 'occ', return_value=SimpleNamespace(stdout=json.dumps(raw))):
            with self.assertRaises(RuntimeError):
                stack.setup()

    def test_backup_failure_restarts_original_services(self):
        def compose(*args, **kwargs):
            return SimpleNamespace(stdout='nextcloud\nvaultwarden\n' if args[0] == 'ps' else '')
        with patch.object(stack.os, 'geteuid', return_value=0), \
             patch.object(stack, 'compose', side_effect=compose) as cp, \
             patch.object(stack, 'run', side_effect=subprocess.CalledProcessError(2, 'tar')):
            with self.assertRaises(subprocess.CalledProcessError):
                stack.backup(self.root / 'backups')
        self.assertEqual(cp.call_args_list[-1].args, ('start', 'nextcloud', 'vaultwarden'))
        self.assertEqual(len(list((self.root / 'backups').glob('*.incomplete'))), 1)

    def test_existing_image_digest_is_not_refreshed(self):
        existing = {'services': {'nextcloud': {'image': 'nextcloud@sha256:old'}}}
        (self.root / 'compose.lock.yaml').write_text(json.dumps(existing))
        with patch.object(stack, 'compose', return_value=SimpleNamespace(stdout=json.dumps(
                {'services': {'nextcloud': {'image': 'nextcloud:new-tag'}}}))) as cp, \
             patch.object(stack, 'run') as run:
            stack.lock()
        run.assert_not_called()
        self.assertFalse(any(c.args[0] == 'pull' for c in cp.call_args_list))
        self.assertEqual(json.loads((self.root / 'compose.lock.yaml').read_text()), existing)

    def test_image_lock_wins_over_https_overlay(self):
        (self.root / 'compose.lock.yaml').write_text('{}')
        (self.root / 'compose.https.yaml').write_text('{}')
        with patch.object(stack, 'run', return_value=SimpleNamespace(stdout='')) as run:
            stack.compose('config')
        command = run.call_args.args[0]
        self.assertGreater(command.index('compose.lock.yaml'), command.index('compose.https.yaml'))


if __name__ == '__main__':
    unittest.main()
