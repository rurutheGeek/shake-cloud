"""Guard the KHInsider album downloader (music-tools on media-01).

khinsider.py turns one album URL into music/Khinsider/<album>/. MeTube cannot do
this because a KHInsider album wraps many tracks behind an album page and a
per-song page. It can also restore Japanese track names through iTunes JP and a
manual dictionary. The service runs behind the same Forward Auth as MeTube.
These are source-text and in-memory assertions; nothing here contacts the site.
"""
import ast
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import yaml

from support import load_module, read

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/music-tools'
SOURCE = STACK / 'khinsider.py'
DICTIONARY = STACK / 'khinsider-ja.json'
PLAYBOOK = ROOT / 'platform/ansible/music-tools.yml'
IDENTITY = ROOT / 'stacks/identity/configure.py'

khinsider = load_module(SOURCE, 'khinsider')


ALBUM_PAGE = '''<html><body>
<h2>Kirby Super Star</h2>
<p class="albuminfoAlternativeTitles">Kirby&#039;s Fun Pak<br />
Hoshi no Kirby Super Deluxe<br />
星のカービィスーパーデラックス</p>
<table id="songlist"><tr><th>#</th></tr>
<tr><td><a href="/game-soundtracks/album/kirby-super-star/1-01.%2520Grand%2520Opening.mp3">Grand Opening</a></td>
<td><a href="/game-soundtracks/album/kirby-super-star/1-01.%2520Grand%2520Opening.mp3">0:14</a></td>
<td><a href="/game-soundtracks/album/kirby-super-star/1-01.%2520Grand%2520Opening.mp3">0.61 MB</a></td></tr>
<tr><td><a href="/game-soundtracks/album/kirby-super-star/1-02.%2520Dreamland%2520Selection.mp3">Dreamland Selection</a></td></tr>
</table><h2>Description</h2></body></html>'''

SONG_PAGE = ('<html><audio id="audio" controls '
             'src="https://nu.vgmtreasurechest.com/soundtracks/kirby-super-star/'
             'eyfeibks/1-01.%20Grand%20Opening.mp3"></audio></html>')


class ParseTests(unittest.TestCase):
    def test_the_album_title_tracks_and_durations_are_read(self):
        album, tracks = khinsider.parse_album(ALBUM_PAGE)
        self.assertEqual(album, 'Kirby Super Star')
        self.assertEqual(tracks, [
            ('/game-soundtracks/album/kirby-super-star/1-01.%2520Grand%2520Opening.mp3',
             'Grand Opening', '0:14'),
            ('/game-soundtracks/album/kirby-super-star/1-02.%2520Dreamland%2520Selection.mp3',
             'Dreamland Selection', None),
        ])

    def test_the_album_alternative_titles_are_read(self):
        self.assertEqual(khinsider.parse_alt_titles(ALBUM_PAGE),
                         ['Kirby\'s Fun Pak', 'Hoshi no Kirby Super Deluxe',
                          '星のカービィスーパーデラックス'])

    def test_the_direct_mp3_url_is_read_from_the_song_page(self):
        self.assertEqual(
            khinsider.parse_mp3_url(SONG_PAGE),
            'https://nu.vgmtreasurechest.com/soundtracks/kirby-super-star/'
            'eyfeibks/1-01.%20Grand%20Opening.mp3')

    def test_the_player_source_wins_over_a_plain_link(self):
        markup = ('<a href="https://downloads.khinsider.com/game-soundtracks/album/'
                  'kirby-super-star/1-01.%2520Grand%2520Opening.mp3">link</a>'
                  '<audio src="https://nu.vgmtreasurechest.com/soundtracks/'
                  'kirby-super-star/eyfeibks/1-01.%20Grand%20Opening.mp3"></audio>')
        self.assertEqual(
            khinsider.parse_mp3_url(markup),
            'https://nu.vgmtreasurechest.com/soundtracks/kirby-super-star/'
            'eyfeibks/1-01.%20Grand%20Opening.mp3')

    def test_a_page_without_tracks_reports_nothing(self):
        self.assertEqual(khinsider.parse_album('<h2>Empty</h2>'), ('Empty', []))


class NamingTests(unittest.TestCase):
    def test_the_site_filename_is_decoded_once_per_encode(self):
        self.assertEqual(
            khinsider.track_filename(
                '/game-soundtracks/album/kirby-super-star/1-01.%2520Grand%2520Opening.mp3',
                1),
            '1-01. Grand Opening.mp3')

    def test_unsafe_names_stay_inside_one_component(self):
        for name in ('../../etc/passwd', 'a/b\\c:d*e?f"g<h>i|j'):
            component = khinsider.safe_component(name)
            self.assertNotIn('/', component)
            self.assertNotIn('\\', component)
            self.assertFalse(component.startswith('.'))

    def test_a_filename_always_ends_in_mp3(self):
        self.assertTrue(khinsider.track_filename('/x/song', 2).endswith('.mp3'))

    def test_the_file_name_is_only_the_song_title(self):
        self.assertEqual(khinsider.title_filename('オープニング', 1), 'オープニング.mp3')
        self.assertEqual(khinsider.title_filename('Green Greens.mp3', 5),
                         'Green Greens.mp3')

    def test_the_track_position_comes_from_the_site_prefix(self):
        self.assertEqual(
            khinsider.track_position(
                '/game-soundtracks/album/kirby-super-star/1-01.%2520Grand%2520Opening.mp3',
                1),
            (1, 1))
        self.assertEqual(
            khinsider.track_position('/game-soundtracks/album/x/2-17%20Song.mp3', 9),
            (2, 17))
        self.assertEqual(khinsider.track_position('/game-soundtracks/album/x/song.mp3', 9),
                         (1, 9))


class JapaneseTests(unittest.TestCase):
    def test_durations_are_parsed(self):
        self.assertEqual(khinsider.seconds('1:23'), 83)
        self.assertEqual(khinsider.seconds('0:14'), 14)
        self.assertIsNone(khinsider.seconds(''))
        self.assertIsNone(khinsider.seconds('n/a'))

    def test_matching_handles_a_reordered_official_release(self):
        kh = [('/a/1.mp3', 'A', '0:30'), ('/a/2.mp3', 'B', '0:10')]
        official = [{'number': 1, 'title': 'いち', 'seconds': 10.0},
                    {'number': 2, 'title': 'に', 'seconds': 30.0}]
        self.assertEqual(khinsider.match_tracks(kh, official), [1, 0])

    def test_matching_uses_positions_when_lengths_and_durations_align(self):
        kh = [('/a/1.mp3', 'A', '0:10'), ('/a/2.mp3', 'B', '0:20')]
        official = [{'number': 1, 'title': 'いち', 'seconds': 10.2},
                    {'number': 2, 'title': 'に', 'seconds': 20.1}]
        self.assertEqual(khinsider.match_tracks(kh, official), [0, 1])

    def test_itunes_match_picks_the_close_release(self):
        kh = [('/a/1.mp3', 'One', '0:10'), ('/a/2.mp3', 'Two', '0:20'),
              ('/a/3.mp3', 'Three', '0:30')]
        albums = [{'collectionId': 1, 'collectionName': '別の盤', 'trackCount': 40},
                  {'collectionId': 2, 'collectionName': '公式盤', 'trackCount': 3}]
        tracks = {2: [{'number': 1, 'title': '一', 'seconds': 10.0},
                      {'number': 2, 'title': '二', 'seconds': 20.0},
                      {'number': 3, 'title': '三', 'seconds': 30.0}]}
        with mock.patch.object(khinsider, 'itunes_albums', return_value=albums), \
                mock.patch.object(khinsider, 'itunes_tracks',
                                  side_effect=lambda cid: tracks[cid]):
            album, titles = khinsider.itunes_match(['公式盤'], kh)
        self.assertEqual(album, '公式盤')
        self.assertEqual(titles, {1: '一', 2: '二', 3: '三'})

    def test_itunes_match_gives_up_when_nothing_aligns(self):
        kh = [('/a/1.mp3', 'A', '0:10'), ('/a/2.mp3', 'B', '0:11'),
              ('/a/3.mp3', 'C', '0:12')]
        albums = [{'collectionId': 1, 'collectionName': '無関係', 'trackCount': 3}]
        tracks = {1: [{'number': 1, 'title': 'x', 'seconds': 300.0},
                      {'number': 2, 'title': 'y', 'seconds': 300.0},
                      {'number': 3, 'title': 'z', 'seconds': 300.0}]}
        with mock.patch.object(khinsider, 'itunes_albums', return_value=albums), \
                mock.patch.object(khinsider, 'itunes_tracks',
                                  side_effect=lambda cid: tracks[cid]):
            self.assertEqual(khinsider.itunes_match(['x'], kh), ('', {}))

    def test_musicbrainz_match_reads_japanese_titles(self):
        kh = [('/a/1.mp3', 'One', '0:10'), ('/a/2.mp3', 'Two', '0:20'),
              ('/a/3.mp3', 'Three', '0:30')]
        releases = [{'id': 'rel-1', 'title': '公式盤'}]
        tracks = {'rel-1': [{'number': 1, 'title': '一', 'seconds': 10.0},
                            {'number': 2, 'title': '二', 'seconds': 20.0},
                            {'number': 3, 'title': '三', 'seconds': 30.0}]}
        with mock.patch.object(khinsider, 'musicbrainz_releases', return_value=releases), \
                mock.patch.object(khinsider, 'musicbrainz_tracks',
                                  side_effect=lambda rid: tracks[rid]):
            album, titles = khinsider.musicbrainz_match(['公式盤'], kh)
        self.assertEqual(album, '公式盤')
        self.assertEqual(titles, {1: '一', 2: '二', 3: '三'})

    def test_musicbrainz_rejects_an_english_only_release(self):
        kh = [('/a/1.mp3', 'One', '0:10'), ('/a/2.mp3', 'Two', '0:20'),
              ('/a/3.mp3', 'Three', '0:30')]
        releases = [{'id': 'rel-en', 'title': 'English Release'}]
        tracks = {'rel-en': [{'number': 1, 'title': 'One', 'seconds': 10.0},
                             {'number': 2, 'title': 'Two', 'seconds': 20.0},
                             {'number': 3, 'title': 'Three', 'seconds': 30.0}]}
        with mock.patch.object(khinsider, 'musicbrainz_releases', return_value=releases), \
                mock.patch.object(khinsider, 'musicbrainz_tracks',
                                  side_effect=lambda rid: tracks[rid]):
            self.assertEqual(khinsider.musicbrainz_match(['x'], kh), ('', {}))

    def test_musicbrainz_is_tried_before_itunes(self):
        with mock.patch.object(khinsider, 'musicbrainz_match',
                               return_value=('MB盤', {1: '一'})), \
                mock.patch.object(khinsider, 'itunes_match',
                                  return_value=('iTunes盤', {1: '二'})):
            album, titles = khinsider.resolve_japanese(
                'https://downloads.khinsider.com/game-soundtracks/album/x',
                'Album', [], [('/a/1.mp3', 'One', '0:10')], {})
        # A matched release only supplies track names; the album keeps the
        # page's name (here the English album, since the page has no Japanese).
        self.assertEqual(album, '')
        self.assertEqual(titles, {1: '一'})

    def test_a_matched_release_never_renames_the_album(self):
        # The page has no Japanese alternative title, so the album must stay
        # the page's own name even though a release matched the track list.
        with mock.patch.object(khinsider, 'musicbrainz_match',
                               return_value=('別の盤', {1: '一'})), \
                mock.patch.object(khinsider, 'itunes_match', return_value=('', {})):
            album, titles = khinsider.resolve_japanese(
                'https://downloads.khinsider.com/game-soundtracks/album/x',
                'Original Album', [], [('/a/1.mp3', 'One', '0:10')], {})
        self.assertEqual(album, '')
        self.assertEqual(titles, {1: '一'})

    def test_the_japanese_alternative_title_names_the_album(self):
        # A gamerip must keep the game's Japanese name, never the title of some
        # other album that happened to match the track list.
        with mock.patch.object(khinsider, 'musicbrainz_match',
                               return_value=('別の盤', {1: '一'})), \
                mock.patch.object(khinsider, 'itunes_match', return_value=('', {})):
            album, titles = khinsider.resolve_japanese(
                'https://downloads.khinsider.com/game-soundtracks/album/kirby-super-star',
                'Kirby Super Star',
                ["Kirby's Fun Pak", '星のカービィスーパーデラックス'],
                [('/a/1.mp3', 'Grand Opening', '0:14')], {})
        self.assertEqual(album, '星のカービィスーパーデラックス')
        self.assertEqual(titles, {1: '一'})

    def test_a_gamerip_keeps_the_game_title_when_no_track_matches(self):
        with mock.patch.object(khinsider, 'musicbrainz_match', return_value=('', {})), \
                mock.patch.object(khinsider, 'itunes_match', return_value=('', {})):
            album, titles = khinsider.resolve_japanese(
                'https://downloads.khinsider.com/game-soundtracks/album/kirby-super-star',
                'Kirby Super Star',
                ["Kirby's Fun Pak", '星のカービィスーパーデラックス'],
                [('/a/1-01.%2520Grand%2520Opening.mp3', 'Grand Opening', '0:14')], {})
        self.assertEqual(album, '星のカービィスーパーデラックス')
        self.assertEqual(titles, {})

    def test_the_manual_dictionary_wins_over_itunes(self):
        kh = [('/a/1-01.%2520Grand%2520Opening.mp3', 'Grand Opening', '0:14')]
        dictionary = {'albums': {'kirby-super-star': {
            'album': '手動アルバム', 'tracks': {'Grand Opening': '手動名'}}}}
        with mock.patch.object(khinsider, 'musicbrainz_match', return_value=('', {})), \
                mock.patch.object(khinsider, 'itunes_match',
                                  return_value=('iTunesアルバム', {1: '自動名'})):
            album, titles = khinsider.resolve_japanese(
                'https://downloads.khinsider.com/game-soundtracks/album/kirby-super-star',
                'Kirby Super Star', [], kh, dictionary)
        self.assertEqual(album, '手動アルバム')
        self.assertEqual(titles, {1: '手動名'})

    def test_the_manual_dictionary_can_be_keyed_by_number(self):
        kh = [('/a/1-01.%2520Grand%2520Opening.mp3', 'Grand Opening', '0:14')]
        dictionary = {'albums': {'kirby-super-star': {'tracks': {'1': '一番'}}}}
        with mock.patch.object(khinsider, 'musicbrainz_match', return_value=('', {})), \
                mock.patch.object(khinsider, 'itunes_match', return_value=('', {})):
            _, titles = khinsider.resolve_japanese(
                'https://downloads.khinsider.com/game-soundtracks/album/kirby-super-star',
                'Kirby Super Star', [], kh, dictionary)
        self.assertEqual(titles, {1: '一番'})

    def test_a_broken_dictionary_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            broken = Path(directory) / 'khinsider-ja.json'
            broken.write_text('{not json')
            self.assertEqual(khinsider.load_dictionary(broken), {})
            missing = Path(directory) / 'missing.json'
            self.assertEqual(khinsider.load_dictionary(missing), {})

    def test_the_shipped_dictionary_is_valid(self):
        data = json.loads(read(DICTIONARY))
        self.assertIn('albums', data)


class UrlTests(unittest.TestCase):
    def test_an_album_url_is_canonicalised(self):
        self.assertEqual(
            khinsider.validate_album_url(
                'https://downloads.khinsider.com/game-soundtracks/album/kirby-super-star/'),
            'https://downloads.khinsider.com/game-soundtracks/album/kirby-super-star')

    def test_anything_but_a_khinsider_album_is_refused(self):
        for url in ('http://downloads.khinsider.com/game-soundtracks/album/x',
                    'https://evil.example/game-soundtracks/album/x',
                    'https://downloads.khinsider.com/game-soundtracks/',
                    'https://downloads.khinsider.com/game-soundtracks/album/',
                    'file:///etc/passwd', ''):
            with self.assertRaises(ValueError, msg=url):
                khinsider.validate_album_url(url)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.music = Path(self.tmp.name) / 'music'
        self.album = 'https://downloads.khinsider.com/game-soundtracks/album/kirby-super-star'

    def run_download(self, downloads, japanese=False):
        def http_get(url, timeout=60):
            return (ALBUM_PAGE if url == self.album else SONG_PAGE).encode()

        def http_download(url, destination, timeout=600):
            downloads.append(url)
            Path(destination).write_bytes(b'id3' * 100)

        patches = [mock.patch.object(khinsider, 'http_get', side_effect=http_get),
                   mock.patch.object(khinsider, 'http_download', side_effect=http_download),
                   mock.patch.object(khinsider, 'write_tags', return_value=True)]
        if japanese:
            patches.append(mock.patch.object(
                khinsider, 'resolve_japanese',
                return_value=('日本語アルバム', {1: 'いち', 2: 'に'})))
        for item in patches:
            item.start()
        try:
            khinsider.download_album(self.album, self.music, lambda *args: None,
                                     japanese=japanese)
        finally:
            for item in reversed(patches):
                item.stop()

    def test_tracks_land_under_khinsider_album(self):
        downloads = []
        self.run_download(downloads)
        folder = self.music / 'Khinsider' / 'Kirby Super Star'
        self.assertEqual(sorted(path.name for path in folder.iterdir()),
                         ['Dreamland Selection.mp3', 'Grand Opening.mp3'])
        self.assertEqual(len(downloads), 2)
        self.assertFalse(list(folder.glob('*.part')))

    def test_a_second_run_keeps_the_files_and_fetches_nothing(self):
        self.run_download([])
        downloads = []
        self.run_download(downloads)
        self.assertEqual(downloads, [])

    def test_japanese_titles_rename_files_and_write_tags(self):
        tagged = []

        def write_tags(path, title='', album='', disc=None, track=None):
            tagged.append((title, album, disc, track))
            return True

        def http_get(url, timeout=60):
            return (ALBUM_PAGE if url == self.album else SONG_PAGE).encode()

        def http_download(url, destination, timeout=600):
            Path(destination).write_bytes(b'id3' * 100)

        with mock.patch.object(khinsider, 'http_get', side_effect=http_get), \
                mock.patch.object(khinsider, 'http_download', side_effect=http_download), \
                mock.patch.object(khinsider, 'write_tags', side_effect=write_tags), \
                mock.patch.object(khinsider, 'resolve_japanese',
                                  return_value=('日本語アルバム', {1: 'いち', 2: 'に'})):
            khinsider.download_album(self.album, self.music, lambda *args: None,
                                     japanese=True)
        folder = self.music / 'Khinsider' / '日本語アルバム'
        self.assertEqual(sorted(path.name for path in folder.iterdir()),
                         ['いち.mp3', 'に.mp3'])
        self.assertEqual(sorted(title for title, _, _, _ in tagged), ['いち', 'に'])
        self.assertTrue(all(album == '日本語アルバム' for _, album, _, _ in tagged))
        # The track number is written to the tags, never to the file name.
        self.assertEqual([(disc, track) for _, _, disc, track in tagged], [(1, 1), (1, 2)])

    def test_the_japanese_album_is_applied_without_track_matches(self):
        tagged = []

        def write_tags(path, title='', album='', disc=None, track=None):
            tagged.append((title, album, disc, track))
            return True

        def http_get(url, timeout=60):
            return (ALBUM_PAGE if url == self.album else SONG_PAGE).encode()

        def http_download(url, destination, timeout=600):
            Path(destination).write_bytes(b'id3' * 100)

        with mock.patch.object(khinsider, 'http_get', side_effect=http_get), \
                mock.patch.object(khinsider, 'http_download', side_effect=http_download), \
                mock.patch.object(khinsider, 'write_tags', side_effect=write_tags), \
                mock.patch.object(khinsider, 'resolve_japanese',
                                  return_value=('星のカービィスーパーデラックス', {})):
            khinsider.download_album(self.album, self.music, lambda *args: None,
                                     japanese=True)
        folder = self.music / 'Khinsider' / '星のカービィスーパーデラックス'
        self.assertEqual(sorted(path.name for path in folder.iterdir()),
                         ['Dreamland Selection.mp3', 'Grand Opening.mp3'])
        self.assertEqual([title for title, _, _, _ in tagged], ['', ''])

    def test_a_duplicate_title_gets_a_deterministic_counter(self):
        page = ('<html><body><h2>Dup</h2><table id="songlist">'
                '<tr><td><a href="/game-soundtracks/album/dup/1-01.%2520Song.mp3">Song</a></td></tr>'
                '<tr><td><a href="/game-soundtracks/album/dup/1-02.%2520Song.mp3">Song</a></td></tr>'
                '</table></body></html>')

        def http_get(url, timeout=60):
            return page.encode()

        def http_download(url, destination, timeout=600):
            Path(destination).write_bytes(b'id3' * 100)

        with mock.patch.object(khinsider, 'http_get', side_effect=http_get), \
                mock.patch.object(khinsider, 'http_download', side_effect=http_download), \
                mock.patch.object(khinsider, 'write_tags', return_value=True):
            khinsider.download_album(
                'https://downloads.khinsider.com/game-soundtracks/album/dup',
                self.music, lambda *args: None)
        folder = self.music / 'Khinsider' / 'Dup'
        self.assertEqual(sorted(path.name for path in folder.iterdir()),
                         ['Song (2).mp3', 'Song.mp3'])


class BrowserFetchTests(unittest.TestCase):
    """KHInsider is behind Cloudflare; the fetcher must look like a browser.

    A plain urllib request with a bot User-Agent gets ``cf-mitigated: challenge``
    (403). The service reuses the curl_cffi that ships with the MeTube image for
    a Chrome TLS/HTTP2 fingerprint, keeps one session for the cf_clearance
    cookie, and retries the challenge codes before giving up.
    """

    def setUp(self):
        self.addCleanup(khinsider.reset_sessions)
        khinsider.reset_sessions()

    def fake_session(self, status, content=b'ok'):
        response = mock.Mock()
        response.status_code = status
        response.content = content
        response.raise_for_status = mock.Mock()
        session = mock.Mock()
        session.get.return_value = response
        requests_module = mock.Mock()
        requests_module.Session.return_value = session
        return session, requests_module

    def test_the_fallback_user_agent_is_a_browser(self):
        self.assertIn('Mozilla/5.0', khinsider.FALLBACK_USER_AGENT)
        self.assertNotIn('shake-cloud-khinsider', khinsider.FALLBACK_USER_AGENT)

    def test_musicbrainz_keeps_the_identifying_user_agent(self):
        self.assertIn('shake-cloud-khinsider', khinsider.API_USER_AGENT)

    def test_it_uses_the_browser_session_when_available(self):
        session, requests_module = self.fake_session(200, b'<html>ok</html>')
        khinsider.reset_sessions()
        with mock.patch.object(khinsider, 'curl_requests', requests_module):
            self.assertEqual(khinsider.http_get('https://downloads.khinsider.com/x'),
                             b'<html>ok</html>')
        requests_module.Session.assert_called_once_with(impersonate='chrome')
        self.assertEqual(session.get.call_args.kwargs['headers']['Referer'],
                         'https://downloads.khinsider.com/')

    def test_a_challenge_is_retried_then_reported(self):
        session, requests_module = self.fake_session(403)
        khinsider.reset_sessions()
        with mock.patch.object(khinsider, 'curl_requests', requests_module), \
                mock.patch.object(khinsider.time, 'sleep'):
            with self.assertRaises(RuntimeError) as caught:
                khinsider.http_get('https://downloads.khinsider.com/x')
        self.assertIn('403', str(caught.exception))
        self.assertEqual(session.get.call_count, 1 + len(khinsider.CHALLENGE_WAITS))

    def test_it_downloads_through_the_session(self):
        response = mock.Mock()
        response.status_code = 200
        response.raise_for_status = mock.Mock()
        response.iter_content.return_value = [b'id3', b'data']
        session = mock.Mock()
        session.get.return_value = response
        requests_module = mock.Mock()
        requests_module.Session.return_value = session
        khinsider.reset_sessions()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'song.mp3'
            with mock.patch.object(khinsider, 'curl_requests', requests_module):
                khinsider.http_download('https://example.test/song.mp3', target)
            self.assertEqual(target.read_bytes(), b'id3data')
        self.assertTrue(session.get.call_args.kwargs['stream'])

    def test_a_challenged_download_writes_nothing(self):
        session, requests_module = self.fake_session(403)
        khinsider.reset_sessions()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'song.mp3'
            with mock.patch.object(khinsider, 'curl_requests', requests_module), \
                    mock.patch.object(khinsider.time, 'sleep'):
                with self.assertRaises(RuntimeError):
                    khinsider.http_download('https://example.test/song.mp3', target)
            self.assertFalse(target.exists())


class ParallelTests(unittest.TestCase):
    """Albums run up to three at a time; one album never runs twice at once."""

    def test_the_worker_count_is_capped_at_three(self):
        for value, expected in {'1': 1, '2': 2, '3': 3, '0': 1, '9': 3,
                                'x': 3, '': 3}.items():
            with mock.patch.dict(os.environ, {'KHINSIDER_WORKERS': value}):
                self.assertEqual(khinsider.worker_count(), expected, value)

    def test_the_same_album_shares_one_lock(self):
        first = khinsider.album_lock('https://downloads.khinsider.com/a')
        second = khinsider.album_lock('https://downloads.khinsider.com/a')
        other = khinsider.album_lock('https://downloads.khinsider.com/b')
        self.assertIs(first, second)
        self.assertIsNot(first, other)


class ConfirmTests(unittest.TestCase):
    """Before starting, show how far a previous run got (the log may be gone)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.music = Path(self.tmp.name)

    def test_the_folder_prefers_the_japanese_name(self):
        self.assertEqual(
            khinsider.album_folder(
                'https://downloads.khinsider.com/game-soundtracks/album/kirby-super-star',
                'Kirby Super Star', ["Kirby's Fun Pak", '星のカービィ スーパーデラックス'],
                True, {}),
            '星のカービィ スーパーデラックス')
        self.assertEqual(
            khinsider.album_folder(
                'https://downloads.khinsider.com/game-soundtracks/album/kirby-super-star',
                'Kirby Super Star', ['星のカービィ スーパーデラックス'], False, {}),
            'Kirby Super Star')
        self.assertEqual(
            khinsider.album_folder('https://downloads.khinsider.com/game-soundtracks/album/x',
                                   'Album', [], True, {'albums': {'x': {'album': '手動'}}}),
            '手動')

    def test_the_overview_counts_only_mp3_files(self):
        folder = self.music / 'Khinsider' / 'Kirby Super Star'
        folder.mkdir(parents=True)
        (folder / 'a.mp3').write_bytes(b'x')
        (folder / 'b.mp3').write_bytes(b'x')
        (folder / '.b.mp3.part').write_bytes(b'x')
        (folder / 'cover.jpg').write_bytes(b'x')
        with mock.patch.object(khinsider, 'MUSIC_ROOT', self.music), \
                mock.patch.object(khinsider, 'http_get', return_value=ALBUM_PAGE.encode()):
            name, total, names = khinsider.album_overview(
                'https://downloads.khinsider.com/game-soundtracks/album/kirby-super-star',
                False, {})
        self.assertEqual(name, 'Kirby Super Star')
        self.assertEqual(total, 2)
        self.assertEqual(names, ['a.mp3', 'b.mp3'])

    def test_the_confirmation_shows_counts_and_resumes(self):
        page = khinsider.confirm_page(
            'https://downloads.khinsider.com/game-soundtracks/album/x',
            True, 'アルバム', 10, ['a.mp3', 'b.mp3'])
        self.assertIn('2 / 10 曲', page)
        self.assertIn('続きからダウンロード', page)
        self.assertIn('name="confirm"', page)
        self.assertIn('name="japanese"', page)
        self.assertIn('アルバム', page)


class ProgressTests(unittest.TestCase):
    """The job list is a persisted, live dashboard so progress is visible."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        patches = [
            mock.patch.object(khinsider, 'STATE_DIR', self.state),
            mock.patch.object(khinsider, 'JOBS_FILE', self.state / 'jobs.json'),
            mock.patch.object(khinsider, 'JOBS', {}),
        ]
        for item in patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in reversed(patches)])

    def test_jobs_survive_a_restart(self):
        job = khinsider.Job(
            'https://downloads.khinsider.com/game-soundtracks/album/x', japanese=True)
        job.state, job.done, job.total, job.detail = 'running', 3, 70, 'song.mp3'
        khinsider.JOBS[job.id] = job
        khinsider.save_jobs()
        khinsider.JOBS.clear()
        khinsider.load_jobs()
        restored = khinsider.JOBS[job.id]
        self.assertEqual(restored.done, 3)
        self.assertEqual(restored.total, 70)
        self.assertTrue(restored.japanese)
        # A job interrupted by the restart is kept and can be retried.
        self.assertEqual(restored.state, 'failed')
        self.assertIn('再試行', restored.error)

    def test_index_page_is_a_live_dashboard(self):
        job = khinsider.Job('https://downloads.khinsider.com/game-soundtracks/album/x')
        job.state, job.done, job.total, job.detail = 'running', 2, 10, 'song.mp3'
        khinsider.JOBS[job.id] = job
        page = khinsider.index_page()
        self.assertIn('実行中', page)
        self.assertIn('http-equiv="refresh"', page)
        self.assertIn('2/10曲', page)

    def test_a_settled_history_does_not_refresh(self):
        job = khinsider.Job('https://downloads.khinsider.com/game-soundtracks/album/x')
        job.state, job.done, job.total = 'done', 1, 1
        khinsider.JOBS[job.id] = job
        self.assertNotIn('http-equiv="refresh"', khinsider.index_page())

    def test_index_page_shows_the_failure_reason(self):
        job = khinsider.Job('https://downloads.khinsider.com/game-soundtracks/album/x')
        job.state, job.error = 'failed', 'RuntimeError: HTTP 403'
        khinsider.JOBS[job.id] = job
        page = khinsider.index_page()
        self.assertIn('失敗', page)
        self.assertIn('HTTP 403', page)


class JobPageTests(unittest.TestCase):
    def test_a_failed_job_offers_a_retry_form(self):
        job = khinsider.Job(
            'https://downloads.khinsider.com/game-soundtracks/album/x', japanese=True)
        job.state, job.error = 'failed', 'RuntimeError: HTTP 403'
        page = khinsider.job_page(job)
        self.assertIn('再試行', page)
        self.assertIn('action="/download"', page)
        self.assertIn('name="url"', page)
        self.assertIn('name="japanese"', page)
        self.assertIn(
            'value="https://downloads.khinsider.com/game-soundtracks/album/x"', page)

    def test_a_done_job_can_be_retried_without_the_japanese_option(self):
        job = khinsider.Job('https://downloads.khinsider.com/game-soundtracks/album/x')
        job.state = 'done'
        page = khinsider.job_page(job)
        self.assertIn('再試行', page)
        self.assertNotIn('name="japanese"', page)

    def test_a_running_job_has_no_retry_form(self):
        job = khinsider.Job('https://downloads.khinsider.com/game-soundtracks/album/x')
        job.state = 'running'
        self.assertNotIn('再試行', khinsider.job_page(job))


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.compose = yaml.safe_load(read(STACK / 'compose.yaml'))
        self.lock = yaml.safe_load(read(STACK / 'compose.lock.yaml'))
        self.play = yaml.safe_load(read(PLAYBOOK))[0]
        self.tasks = {task['name']: task for task in self.play['tasks']}

    def test_the_service_writes_the_shared_library_and_listens_on_loopback(self):
        service = self.compose['services']['khinsider']
        self.assertEqual(service['entrypoint'],
                         ['python3', '/tools/khinsider.py'])
        self.assertIn('${LIBRARY_ROOT:-../library}/music:/music', service['volumes'])
        self.assertIn('5820', service['ports'][0])
        self.assertTrue(service['ports'][0].startswith('127.0.0.1:'))
        self.assertEqual(service['environment']['KHINSIDER_MUSIC'], '/music')

    def test_the_manual_dictionary_is_mounted_and_read(self):
        service = self.compose['services']['khinsider']
        self.assertIn('./khinsider-ja.json:/tools/khinsider-ja.json:ro',
                      service['volumes'])
        self.assertEqual(service['environment']['KHINSIDER_JA'],
                         '/tools/khinsider-ja.json')

    def test_the_job_history_directory_is_mounted_and_created(self):
        service = self.compose['services']['khinsider']
        self.assertIn('./storage/khinsider:/state', service['volumes'])
        self.assertEqual(service['environment']['KHINSIDER_STATE'], '/state')
        self.assertIn("'khinsider'", read(STACK / 'manage.py'))

    def test_the_image_is_pinned_in_the_lock(self):
        image = self.lock['services']['khinsider']['image']
        self.assertIn('@sha256:', image)
        self.assertEqual(image, self.lock['services']['metube']['image'])

    def test_the_playbook_ships_the_code_and_the_port(self):
        self.assertIn('khinsider', self.play['vars']['music_tools_services'])
        self.assertEqual(self.play['vars']['music_tools_khinsider_port'], 5820)
        loop = self.tasks['Copy tool definitions']['loop']
        self.assertIn('khinsider.py', loop)
        self.assertIn('khinsider-ja.json', loop)
        content = self.tasks['Configure environment']['ansible.builtin.copy']['content']
        self.assertIn("'khinsider' in music_tools_services", content)
        self.assertIn('KHINSIDER_PORT=', content)

    def test_the_code_hash_forces_a_recreate(self):
        source = read(STACK / 'manage.py')
        self.assertIn('KHINSIDER_CODE_SHA', source)
        # The dictionary is a single-file bind mount: it only reaches a running
        # container when the container is recreated, so it must be hashed too.
        self.assertIn("khinsider-ja.json", source)
        self.assertIn('media-stack.khinsider-code',
                      self.compose['services']['khinsider']['labels'])

    def test_identity_serves_the_page_behind_forward_auth(self):
        configure = load_module(IDENTITY, 'identity_configure_khinsider')
        self.assertIn('khinsider', configure.MEDIA_PROXY_PROVIDERS)
        self.assertIn('khinsider', configure.MEDIA_APPLICATIONS)

    def test_the_service_only_needs_the_image_and_the_standard_library(self):
        # mutagen is used for the ID3 tags, and curl_cffi for the browser TLS
        # fingerprint against Cloudflare. Both are already in the MeTube image
        # (yt-dlp depends on curl_cffi; the tag API imports mutagen).
        modules = set()
        for node in ast.walk(ast.parse(read(SOURCE))):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add((node.module or '').split('.')[0])
        self.assertLessEqual(modules, set(sys.stdlib_module_names) | {'mutagen', 'curl_cffi'})


if __name__ == '__main__':
    unittest.main()
