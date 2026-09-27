"""Deployment checks for the poke-translate site on services-01.

The implementation and its tests live in rurutheGeek/poke-translate; this
repository pins a release and serves it.
"""

import importlib.util
import io
import json
from pathlib import Path
import re
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/poke-translate'
ROLE = ROOT / 'platform/ansible/roles/poke_translate'


def load_manage():
    spec = importlib.util.spec_from_file_location('poke_translate_manage', STACK / 'manage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def release(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


SITE = {name: name.encode() for name in
        ['index.html', 'poketr.js', 'dictionary.json', 'poke-translate-extension.zip']}


class PinTests(unittest.TestCase):
    def setUp(self):
        self.defaults = yaml.safe_load((ROLE / 'defaults/main.yml').read_text(encoding='utf-8'))
        self.tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text(encoding='utf-8'))

    def test_the_release_is_pinned_by_version_and_sha256(self):
        self.assertRegex(str(self.defaults['poke_translate_version']), r'^\d+\.\d+\.\d+$')
        self.assertRegex(self.defaults['poke_translate_sha256'], r'^[0-9a-f]{64}$')
        self.assertTrue(self.defaults['poke_translate_release_url'].startswith(
            'https://github.com/rurutheGeek/poke-translate/releases/download/v'))

    def test_the_download_is_verified_before_install(self):
        names = [task['name'] for task in self.tasks]
        download = next(task for task in self.tasks if 'ansible.builtin.get_url' in task)
        self.assertEqual(download['ansible.builtin.get_url']['checksum'],
                         'sha256:{{ poke_translate_sha256 }}')
        install = next(task for task in self.tasks
                       if 'install' in task.get('ansible.builtin.command', {}).get('argv', []))
        self.assertLess(names.index(download['name']), names.index(install['name']))

    def test_only_the_deployment_files_are_copied(self):
        copy = next(task for task in self.tasks if task['name'] == 'Copy the translator stack')
        tracked = {path.name for path in STACK.iterdir() if path.is_file()} - {'README.md'}
        self.assertEqual(set(copy['loop']), tracked)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.manage = load_manage()
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.state = root / 'state'
        project = root / 'project'
        project.mkdir()
        (project / '.env').write_text(f'STORAGE_ROOT={self.state}\n', encoding='utf-8')
        self.patch = patch.object(self.manage, 'ROOT', project)
        self.patch.start()
        self.archive = root / 'site.tar.gz'

    def tearDown(self):
        self.patch.stop()
        self.directory.cleanup()

    def install(self, files):
        self.archive.write_bytes(release(files))
        with patch('builtins.print') as printed:
            self.manage.install(self.archive)
        return printed.call_args[0][0]

    def test_install_replaces_changed_files_and_removes_stale_ones(self):
        self.assertTrue(self.install(SITE).startswith('CHANGED'))
        self.assertTrue(self.install(SITE).startswith('OK'))
        (self.state / 'site/old.js').write_text('stale')
        self.assertTrue(self.install({**SITE, 'poketr.js': b'new'}).startswith('CHANGED'))
        site = self.state / 'site'
        self.assertEqual(sorted(path.name for path in site.iterdir()), sorted(SITE))
        self.assertEqual((site / 'poketr.js').read_bytes(), b'new')
        self.assertEqual((site / 'index.html').stat().st_mode & 0o777, 0o644)

    def test_archives_with_paths_or_missing_files_are_refused(self):
        for files in [{**SITE, '../escape': b'x'}, {**SITE, 'dir/file': b'x'},
                      {name: data for name, data in SITE.items() if name != 'dictionary.json'}]:
            self.archive.write_bytes(release(files))
            with self.assertRaises(ValueError):
                self.manage.install(self.archive)

    def test_state_inside_the_project_is_refused(self):
        (self.manage.ROOT / '.env').write_text(f'STORAGE_ROOT={self.manage.ROOT / "state"}\n')
        with self.assertRaises(ValueError):
            self.manage.storage()


class DeploymentTests(unittest.TestCase):
    def test_the_site_is_static_loopback_only_and_read_only(self):
        service = yaml.safe_load((STACK / 'compose.yaml').read_text())['services']['site']
        self.assertEqual(service['ports'], ['127.0.0.1:${POKE_TRANSLATE_PORT:-8320}:8080'])
        self.assertTrue(service['read_only'])
        self.assertEqual(service['cap_drop'], ['ALL'])
        self.assertEqual(service['volumes'], ['${STORAGE_ROOT:-/srv/services/poke-translate}/site:/srv:ro'])

    def test_the_image_is_pinned_by_digest(self):
        lock = json.loads((STACK / 'compose.lock.yaml').read_text())
        self.assertRegex(lock['services']['site']['image'], r'^python@sha256:[0-9a-f]{64}$')

    def test_the_implementation_is_not_vendored_here(self):
        for name in ['core', 'extension', 'site', 'dictionary.py', 'custom-terms.json']:
            self.assertFalse((STACK / name).exists(), name)
        self.assertTrue(re.search(r'rurutheGeek/poke-translate', (STACK / 'README.md').read_text()))


if __name__ == '__main__':
    unittest.main()
