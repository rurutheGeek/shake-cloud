"""Unit checks for the all-tracks review board (stacks/music-tools/review.py).

The board runs behind the navidrome /review/ Forward Auth entry on media-01.
Nothing here touches the real library: MUSIC/STATE are pointed at a temp dir.
"""
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'stacks/music-tools/review.py'


def load_review():
    spec = importlib.util.spec_from_file_location('music_review', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.review = load_review()
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.review.MUSIC = root / 'music'
        self.review.STATE = root / 'state'
        self.review.MUSIC.mkdir()
        self.review.STATE.mkdir()
        self.review.EVENTS_FILE = self.review.STATE / 'events.jsonl'
        self.review.INDEX_FILE = self.review.STATE / 'index.json'
        self.review.INDEX[:] = []
        self.review.VOTES.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def test_safe_media_refuses_paths_outside_the_library(self):
        (self.review.MUSIC / 'a.mp3').write_bytes(b'x')
        self.assertEqual(self.review.safe_media('a.mp3'), self.review.MUSIC / 'a.mp3')
        self.assertIsNone(self.review.safe_media('../etc/passwd'))
        self.assertIsNone(self.review.safe_media('/etc/passwd'))
        self.assertIsNone(self.review.safe_media('a.txt'))

    def test_read_navidrome_maps_rows_and_composers(self):
        # 索引は Navidrome の media_file 表から作る。composer は
        # participants JSON の composer ロール、missing の行は落とす。
        db = self.review.STATE / 'navidrome.db'
        con = sqlite3.connect(db)
        con.execute('CREATE TABLE media_file (path TEXT, title TEXT, album TEXT,'
                    ' artist TEXT, album_artist TEXT, track_number INTEGER,'
                    ' disc_number INTEGER, genre TEXT, duration REAL,'
                    ' participants TEXT, missing INTEGER)')
        insert = 'INSERT INTO media_file VALUES (?,?,?,?,?,?,?,?,?,?,?)'
        con.execute(insert, (
            'a/b.mp3', 'B', 'Album', 'Artist', 'AlbumArtist', 3, 1, 'Pop', 12.34,
            json.dumps({'composer': [{'id': 'x', 'name': '作曲 太郎'},
                                     {'id': 'y', 'name': '作曲 次郎'}]}), 0))
        con.execute(insert, ('gone.mp3', 'Gone', '', '', '', None, None, '', 0,
                             '{}', 1))
        con.commit()
        con.close()
        rows = self.review.read_navidrome(db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['path'], 'a/b.mp3')
        self.assertEqual(rows[0]['composer'], '作曲 太郎, 作曲 次郎')
        self.assertEqual(rows[0]['track'], '3')
        self.assertEqual(rows[0]['disc'], '1')
        self.assertEqual(rows[0]['length'], 12.3)

    def test_summarize_marks_checked_and_complete(self):
        self.review.INDEX[:] = [
            {'path': 'a.mp3', 'title': 'A', 'artist': 'P', 'albumartist': 'P', 'album': 'Album'},
            {'path': 'b.mp3', 'title': 'B', 'artist': 'P', 'albumartist': 'P', 'album': 'Album'},
        ]
        _, artists, albums, checked = self.review.summarize('ruru')
        self.assertEqual(checked, 0)
        self.assertFalse(artists['P']['complete'])
        self.assertFalse(albums[('P', 'Album')]['complete'])
        self.review.VOTES[('ruru', 'a.mp3')] = {'vote': 'like'}
        _, artists, _, checked = self.review.summarize('ruru')
        self.assertEqual(checked, 1)
        self.assertFalse(artists['P']['complete'])
        self.review.VOTES[('ruru', 'b.mp3')] = {'vote': 'flag', 'note': 'wrong'}
        _, artists, albums, checked = self.review.summarize('ruru')
        self.assertEqual(checked, 2)
        self.assertTrue(artists['P']['complete'])
        self.assertTrue(albums[('P', 'Album')]['complete'])

    def test_votes_are_append_only_and_the_latest_wins(self):
        self.review.append_event({'user': 'ruru', 'path': 'a.mp3', 'vote': 'like'})
        self.review.append_event({'user': 'ruru', 'path': 'a.mp3', 'vote': 'flag', 'note': 'wrong'})
        self.review.VOTES.clear()
        self.review.load_events()
        self.assertEqual(self.review.VOTES[('ruru', 'a.mp3')]['vote'], 'flag')
        self.assertEqual(self.review.VOTES[('ruru', 'a.mp3')]['note'], 'wrong')
        self.assertEqual(len(self.review.EVENTS_FILE.read_text().splitlines()), 2)

    def test_current_user_reads_the_forward_auth_headers(self):
        self.assertEqual(self.review.current_user({'Remote-User': 'sso_ruru'}), 'ruru')
        self.assertEqual(self.review.current_user({'X-Authentik-Username': 'ruru'}), 'ruru')
        self.assertEqual(self.review.current_user({}), 'local')

    def test_corrections_accept_several_fields_per_flag(self):
        clean = self.review.clean_corrections
        self.assertEqual(
            clean({'corrections': [{'field': 'title', 'value': 'A'},
                                   {'field': 'artist', 'value': 'B'}]}),
            [{'field': 'title', 'value': 'A'}, {'field': 'artist', 'value': 'B'}])
        # 旧クライアントの field/value も1件として受ける。
        self.assertEqual(clean({'field': 'album', 'value': 'C'}),
                         [{'field': 'album', 'value': 'C'}])
        self.assertEqual(clean({}), [])
        self.assertEqual(clean({'corrections': [{'field': '', 'value': ''}]}), [])
        with self.assertRaises(ValueError):
            clean({'corrections': [{'field': 'nope', 'value': 'x'}]})
        with self.assertRaises(ValueError):
            clean({'corrections': 'x'})


if __name__ == '__main__':
    unittest.main()
