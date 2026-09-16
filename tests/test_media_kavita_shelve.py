"""Guard the Kavita loose-book shelver (media-01 systemd timer).

Kavita treats each folder as a series and ignores files at the library root,
so the timer folds loose books into a folder named after the file.
"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/media/kavita'
SOURCE = STACK / 'shelve-loose-books.py'
PLAYBOOK = ROOT / 'platform/ansible/media-kavita.yml'

spec = importlib.util.spec_from_file_location('shelve_loose_books', SOURCE)
shelver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shelver)


def read(path):
    return path.read_text(encoding='utf-8')


class ShelveTests(unittest.TestCase):
    def run_shelver(self, root, settle=0, kavita_dir=None, scan=None):
        argv = ['shelve-loose-books', '--books', str(root),
                '--settle-seconds', str(settle)]
        if kavita_dir is not None:
            argv += ['--kavita-dir', str(kavita_dir)]
        patcher = mock.patch.object(sys, 'argv', argv)
        if scan is None:
            patcher.start()
            self.addCleanup(patcher.stop)
            return shelver.main()
        with patcher, mock.patch.object(shelver, 'trigger_scan', scan):
            return shelver.main()

    def test_a_loose_pdf_moves_into_its_own_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            book = root / 'My Book.pdf'
            book.write_bytes(b'%PDF-1.4')
            self.assertEqual(self.run_shelver(root), 0)
            self.assertTrue((root / 'My Book' / 'My Book.pdf').exists())
            self.assertFalse(book.exists())

    def test_a_file_that_is_still_uploading_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            book = root / 'new.pdf'
            book.write_bytes(b'%PDF')
            self.assertEqual(self.run_shelver(root, settle=3600), 0)
            self.assertTrue(book.exists())

    def test_other_extensions_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            note = root / 'notes.txt'
            note.write_text('keep')
            self.assertEqual(self.run_shelver(root), 0)
            self.assertTrue(note.exists())

    def test_an_existing_folder_receives_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'My Book').mkdir()
            (root / 'My Book.pdf').write_bytes(b'%PDF')
            self.assertEqual(self.run_shelver(root), 0)
            self.assertTrue((root / 'My Book' / 'My Book.pdf').exists())

    def test_a_duplicate_destination_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'My Book'
            folder.mkdir()
            (folder / 'My Book.pdf').write_bytes(b'original')
            (root / 'My Book.pdf').write_bytes(b'new')
            self.assertEqual(self.run_shelver(root), 0)
            self.assertEqual((folder / 'My Book.pdf').read_bytes(), b'original')

    def test_a_missing_directory_reports_an_error(self):
        self.assertEqual(self.run_shelver(Path('/nonexistent-books-dir')), 1)

    def test_a_move_triggers_the_kavita_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'Book.pdf').write_bytes(b'%PDF')
            calls = []
            code = self.run_shelver(root, kavita_dir=root,
                                    scan=lambda path: calls.append(path))
            self.assertEqual(code, 0)
            self.assertEqual(calls, [str(root)])

    def test_no_move_means_no_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []
            self.run_shelver(root, kavita_dir=root, scan=lambda path: calls.append(path))
            self.assertEqual(calls, [])

    def test_a_scan_without_credentials_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            import contextlib
            import io
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                shelver.trigger_scan(tmp)
            self.assertIn('SCAN: skipped', out.getvalue())


class PlaybookTests(unittest.TestCase):
    def setUp(self):
        self.play = yaml.safe_load(read(PLAYBOOK))[0]
        self.names = [task['name'] for task in self.play['tasks']]

    def test_the_shelver_is_installed_and_started(self):
        for name in ('Copy the loose-book shelver',
                     'Install the loose-book shelver service',
                     'Install the loose-book shelver timer',
                     'Enable the loose-book shelver',
                     'Shelve loose books now'):
            self.assertIn(name, self.names)

    def test_the_service_points_at_the_books_tree(self):
        unit = read(STACK / 'media-stack-kavita-shelve.service.j2')
        self.assertIn('ExecStart=/usr/bin/python3 '
                      '{{ project_dir }}/scripts/shelve-loose-books.py', unit)
        self.assertIn('--books {{ library_root }}/books', unit)
        self.assertIn('--kavita-dir {{ project_dir }}/media/kavita', unit)

    def test_the_timer_runs_hourly(self):
        # 手動整理とぶつからないよう、毎分から1時間ごとへ下げた（2026-09-16）。
        timer = read(STACK / 'media-stack-kavita-shelve.timer')
        self.assertIn('OnUnitInactiveSec=1h', timer)
        self.assertIn('WantedBy=timers.target', timer)


if __name__ == '__main__':
    unittest.main()
