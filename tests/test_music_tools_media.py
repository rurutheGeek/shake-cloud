"""Static checks for the music-tools stack and its Ansible playbook (W06).

The first Picard rollout was done by hand over SSH. platform/ansible/music-tools.yml
is now the reproducible path, so these tests read the checked-in files: nothing
here contacts media-01 or Docker.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/music-tools'
PLAYBOOK = ROOT / 'platform/ansible/music-tools.yml'


def read(path):
    return path.read_text(encoding='utf-8')


class ComposeTests(unittest.TestCase):
    """Picard must stay loopback-only and able to tag the shared music tree."""

    def setUp(self):
        self.compose = yaml.safe_load(read(STACK / 'compose.yaml'))
        self.lock = yaml.safe_load(read(STACK / 'compose.lock.yaml'))

    def test_picard_is_declared_with_a_pinned_digest(self):
        self.assertIn('picard', self.compose['services'])
        self.assertIn('picard', self.lock['services'])
        self.assertRegex(self.lock['services']['picard']['image'],
                         r'^jlesage/musicbrainz-picard@sha256:[0-9a-f]{64}$')

    def test_the_web_gui_is_closed_to_localhost(self):
        self.assertEqual(self.compose['services']['picard']['ports'],
                         ['127.0.0.1:${PICARD_PORT:-5800}:5800'])

    def test_the_shared_music_tree_is_mounted_read_write_for_tagging(self):
        volumes = self.compose['services']['picard']['volumes']
        self.assertIn('${LIBRARY_ROOT:-../library}/music:/storage', volumes)
        self.assertNotIn('${LIBRARY_ROOT:-../library}/music:/storage:ro', volumes)
        self.assertIn('./storage/picard:/config', volumes)


class ManageTests(unittest.TestCase):
    """manage.py creates the Picard config dir and supports staged `up`."""

    def setUp(self):
        self.source = read(STACK / 'manage.py')

    def test_init_creates_the_picard_config_directory(self):
        line = next(line for line in self.source.splitlines()
                    if "'storage'/x for x in" in line)
        self.assertIn("'picard'", line)

    def test_up_can_be_limited_to_selected_services(self):
        self.assertIn("'--services'", self.source)
        self.assertIn('*services', self.source)

    def test_backup_is_available_with_a_default_destination(self):
        self.assertIn("'backup'", self.source)
        self.assertIn("default=str(ROOT/'backups')", self.source)

    def test_backup_requires_root_and_marks_incomplete_runs(self):
        section = self.source.split('def backup', 1)[1].split('def main', 1)[0]
        self.assertIn('os.geteuid()!=0', section)
        self.assertIn('PermissionError', section)
        self.assertIn('.incomplete', section)
        self.assertIn("target.rename(complete)", section)
        self.assertIn("'-C',str(state),'.'", section)
        self.assertNotIn('LIBRARY_ROOT', section)


def load_manage():
    spec = importlib.util.spec_from_file_location('music_tools_manage', STACK / 'manage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BackupTests(unittest.TestCase):
    """Run the cold backup with Docker and tar mocked out."""

    def setUp(self):
        self.manage = load_manage()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.root_patch = patch.object(self.manage, 'ROOT', self.root)
        self.root_patch.start()
        self.state = self.root / 'storage'
        (self.state / 'convert').mkdir(parents=True)
        self.library = self.root / 'library' / 'music'
        (self.library / 'YouTube').mkdir(parents=True)
        for name in ('compose.yaml', 'compose.lock.yaml', '.env', '.env.example', 'manage.py'):
            (self.root / name).write_text('x')

    def tearDown(self):
        self.root_patch.stop()
        self.tmp.cleanup()

    def test_backup_archives_state_without_the_music_library(self):
        calls = []
        tars = []

        def compose(*args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(stdout='metube\nconvert\n' if args[0] == 'ps' else '')

        with patch.object(self.manage.os, 'geteuid', return_value=0), \
             patch.object(self.manage, 'compose', side_effect=compose), \
             patch.object(self.manage, 'run', side_effect=lambda args: tars.append(args)):
            self.manage.backup(self.root / 'backups')
        self.assertEqual(calls[0][0], ('ps', '--services', '--status', 'running'))
        self.assertTrue(calls[0][1].get('capture_output'))
        self.assertIn(('stop', '--timeout', '120'), [args for args, _ in calls])
        self.assertEqual(calls[-1][0], ('start', 'metube', 'convert'))
        self.assertEqual(tars[0][:1], ['tar'])
        self.assertEqual(tars[0][tars[0].index('-C') + 1], str(self.state))
        self.assertFalse(any(str(self.library) in str(arg) for args in tars for arg in args))
        self.assertIn('compose.yaml', tars[1])
        self.assertIn('manage.py', tars[1])
        runs = [path for path in (self.root / 'backups').iterdir()
                if not path.name.endswith('.incomplete')]
        self.assertEqual(len(runs), 1)
        manifest = json.loads((runs[0] / 'manifest.json').read_text())
        self.assertEqual(manifest['storage_root'], str(self.state))
        self.assertEqual(manifest['format'], 1)
        self.assertIn('music library', manifest['notes'])
        self.assertFalse(list((self.root / 'backups').glob('*.incomplete')))

    def test_backup_failure_restarts_original_services(self):
        def compose(*args, **kwargs):
            return SimpleNamespace(stdout='metube\nconvert\n' if args[0] == 'ps' else '')

        with patch.object(self.manage.os, 'geteuid', return_value=0), \
             patch.object(self.manage, 'compose', side_effect=compose) as cp, \
             patch.object(self.manage, 'run',
                          side_effect=subprocess.CalledProcessError(2, 'tar')):
            with self.assertRaises(subprocess.CalledProcessError):
                self.manage.backup(self.root / 'backups')
        self.assertEqual(cp.call_args_list[-1].args, ('start', 'metube', 'convert'))
        self.assertEqual(len(list((self.root / 'backups').glob('*.incomplete'))), 1)

    def test_backup_requires_root(self):
        with patch.object(self.manage.os, 'geteuid', return_value=1000):
            with self.assertRaises(PermissionError):
                self.manage.backup(self.root / 'backups')

    def test_backup_refuses_a_destination_inside_the_state(self):
        with patch.object(self.manage.os, 'geteuid', return_value=0):
            with self.assertRaises(ValueError):
                self.manage.backup(self.state / 'backups')


class EnvironmentTests(unittest.TestCase):
    """The example is the no-secret reference for the generated host `.env`."""

    def setUp(self):
        self.text = read(STACK / '.env.example')

    def test_it_documents_the_keys_compose_and_manage_read(self):
        for key in ('LIBRARY_ROOT', 'PICARD_PORT', 'TZ'):
            self.assertRegex(self.text, rf'(?m)^{key}=')

    def test_it_has_no_secret_assignments(self):
        for key in ('COOKIE', 'PASSWORD', 'SECRET', 'TOKEN'):
            self.assertNotRegex(self.text, rf'(?im)^{key}[A-Z_]*\s*=\s*\S')

    def test_no_generated_env_is_left_in_the_checkout(self):
        # .env is generated on the host with mode 0600; only the example is tracked.
        self.assertFalse((STACK / '.env').exists())


class PlaybookTests(unittest.TestCase):
    """The playbook must reproduce the manual rollout and stay reversible."""

    def setUp(self):
        play = yaml.safe_load(read(PLAYBOOK))[0]
        self.vars = play['vars']
        self.tasks = {task['name']: task for task in play['tasks']}

    def test_the_default_is_still_every_service(self):
        self.assertEqual(self.vars['music_tools_services'],
                         ['metube', 'picard', 'convert'])

    def test_picard_alone_can_be_selected(self):
        argv = self.tasks['Deploy selected music tools']['ansible.builtin.command']['argv']
        self.assertIn('--services', argv)
        self.assertTrue(any('music_tools_services' in str(part) for part in argv))

    def test_the_generated_env_carries_tz_and_the_picard_port(self):
        content = self.tasks['Configure environment']['ansible.builtin.copy']['content']
        self.assertIn('LIBRARY_ROOT={{ library_root }}', content)
        self.assertIn('TZ={{ music_tools_tz }}', content)
        self.assertIn('PICARD_PORT={{ music_tools_picard_port }}', content)

    def test_the_sync_timer_is_on_by_default_and_can_be_disabled(self):
        self.assertIs(self.vars['music_tools_sync_enabled'], True)
        systemd = self.tasks['Configure music synchronization']['ansible.builtin.systemd']
        self.assertIn('music_tools_sync_enabled', systemd['enabled'])
        self.assertIn('music_tools_sync_enabled', systemd['state'])

    def test_the_sync_code_directory_is_created_before_the_copy(self):
        # A fresh cloud VM has no /opt/media-stack/scripts; copying into it
        # failed on media-01 (2026-09-12) until this task was added.
        created = self.tasks['Create synchronization code directory']['ansible.builtin.file']
        self.assertEqual(created['path'], '{{ project_dir }}/scripts')
        self.assertEqual(created['state'], 'directory')
        copied = self.tasks['Copy cache synchronization code']
        self.assertIn('sync-music.py', copied['ansible.builtin.copy']['dest'])


if __name__ == '__main__':
    unittest.main()
