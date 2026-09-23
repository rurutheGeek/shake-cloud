"""Guard the LocalSend receiver unit on media-01.

The receiver is an unofficial headless implementation of the LocalSend
protocol. These are source-text and YAML assertions: nothing here reaches the
host or the network.
"""
import subprocess
from pathlib import Path
import unittest

import yaml

from support import read

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/media/localsend'
PLAYBOOK = ROOT / 'platform/ansible/media-localsend.yml'
ENTRY = ROOT / 'platform/ansible/media.yml'




class UnitTests(unittest.TestCase):
    def compose(self):
        return yaml.safe_load(read(STACK / 'compose.yaml'))

    def service(self):
        return self.compose()['services']['localsend']

    def test_it_is_its_own_compose_project(self):
        self.assertEqual(self.compose()['name'], 'media-localsend')

    def test_it_uses_host_networking_for_multicast(self):
        self.assertEqual(self.service()['network_mode'], 'host')

    def test_received_files_land_in_the_shared_inbox(self):
        volumes = self.service()['volumes']
        self.assertTrue(any('library}/inbox:/inbox' in volume for volume in volumes), volumes)

    def test_it_runs_as_the_nextcloud_uid(self):
        self.assertEqual(self.service()['user'],
                         '${MEDIA_UID:-33}:${MEDIA_GID:-33}')

    def test_the_image_is_pinned_by_digest(self):
        lock = yaml.safe_load(read(STACK / 'compose.lock.yaml'))
        image = lock['services']['localsend']['image']
        self.assertTrue(image.startswith('ghcr.io/linychuo/localsend-hub@sha256:'), image)

    def test_the_pin_secret_is_not_committed(self):
        result = subprocess.run(
            ['git', 'check-ignore', '-q', str(STACK / 'secrets' / 'localsend_pin')],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_env_example_carries_no_secret(self):
        text = read(STACK / '.env.example')
        for key in ('STORAGE_ROOT=', 'LIBRARY_ROOT=', 'LOCALSEND_PORT='):
            self.assertIn(key, text, key)
        self.assertNotIn('localsend_pin=', text)

    def test_manage_creates_the_inbox_and_the_pin(self):
        text = read(STACK / 'manage.py')
        self.assertIn("library / 'inbox'", text)
        self.assertIn("'localsend_pin'", text)
        self.assertIn("'init', 'lock', 'up', 'status'", text)

    def test_the_playbook_targets_media_and_waits_for_info(self):
        play = yaml.safe_load(read(PLAYBOOK))[0]
        self.assertEqual(play['hosts'], 'media')
        self.assertIn('/api/localsend/v2/info', read(PLAYBOOK))

    def test_the_entry_point_imports_it(self):
        self.assertIn('media-localsend.yml', read(ENTRY))


if __name__ == '__main__':
    unittest.main()
