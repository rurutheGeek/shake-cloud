"""Guard the batch organizer for the shared music library (music-tools).

The organizer plans moves and tags from MusicBrainz + existing tags, and only
applies a reviewed manifest. These tests cover the offline logic; network
lookups are injected through a fake MusicBrainz client.
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'stacks/music-tools/organize.py'

spec = importlib.util.spec_from_file_location('organize', SOURCE)
organize = importlib.util.module_from_spec(spec)
spec.loader.exec_module(organize)


class TextTests(unittest.TestCase):
    def test_bracket_prefixes_are_stripped_for_matching(self):
        self.assertEqual(organize.strip_title_prefix('時闇空「やみのかこう」'),
                         'やみのかこう')
        self.assertEqual(organize.strip_title_prefix('ポケマス「戦闘！ N」'),
                         '戦闘！ N')
        self.assertEqual(organize.strip_title_prefix('【MV】p.h. _ SEVENTHLINKS'),
                         'p.h. _ SEVENTHLINKS')
        self.assertEqual(organize.strip_title_prefix('ASGORE'), 'ASGORE')

    def test_filename_album_hint_parses_youtube_suffix(self):
        title, album = organize.filename_album_hint(
            'Arven & Mabostiff – Pokémon Scarlet & Violet_ Original Soundtrack OST')
        self.assertEqual(title, 'Arven & Mabostiff')
        self.assertEqual(album, 'Pokémon Scarlet & Violet')

    def test_filename_album_hint_ignores_normal_dash_titles(self):
        title, album = organize.filename_album_hint('Dr. Mario - Fever')
        self.assertEqual((title, album), ('Dr. Mario - Fever', ''))

    def test_search_cleanup_removes_video_decorations(self):
        cleaned = organize.clean_for_search(
            'ナイト・オブ・ナイツ　高音質再生可能&fmt=18')
        self.assertNotIn('&fmt=18', cleaned)
        self.assertNotIn('高音質', cleaned)
        self.assertTrue(cleaned.startswith('ナイト・オブ・ナイツ'))

    def test_sanitize_component_avoids_path_separators(self):
        self.assertEqual(organize.sanitize_component('AC/DC'), 'AC／DC')
        self.assertEqual(organize.sanitize_component(' .. '), '_')

    def test_track_number_from_filename(self):
        self.assertEqual(organize.filename_track_number('07 song'), 7)
        self.assertEqual(organize.filename_track_number('song'), None)


class MusicBrainzQueryTests(unittest.TestCase):
    def test_recording_query_uses_artist_when_known(self):
        self.assertEqual(organize.recording_query('Song', 'Artist'),
                         'recording:"Song" AND artist:"Artist"')
        self.assertEqual(organize.recording_query('Song', ''),
                         'recording:"Song"')

    def test_release_queries_start_strict_and_loosen_for_long_titles(self):
        queries = organize.release_queries('ポケモン不思議のダンジョン 時・闇・空の探検隊', '')
        self.assertEqual(queries[0], 'release:"ポケモン不思議のダンジョン 時・闇・空の探検隊"')
        self.assertTrue(len(queries) > 1)
        self.assertEqual(organize.release_queries('Album', 'A'),
                         ['release:"Album" AND artist:"A"',
                          'release:Album AND artist:"A"'])


def track(source, **kwargs):
    folder = str(Path(source).parent)
    folder = '' if folder == '.' else folder
    values = dict(source=source, folder=folder, size=100, length=180)
    values.update(kwargs)
    item = organize.Track(**values)
    if not item.title:
        item.title = organize.filename_to_title(Path(source).stem)
    if not item.search_title:
        item.search_title = organize.clean_for_search(item.title)
    return item


def release_summary(mbid, title, tracks, artist='Artist'):
    return {
        'id': mbid, 'title': title, 'date': '2001-05-05',
        'artist-credit': [{'name': artist}],
        'release-group': {'id': 'rg-' + mbid, 'primary-type': 'Album'},
        'track-count': tracks,
    }


def release_detail(mbid, title, titles, artist='Artist', disc=1):
    return {
        'id': mbid, 'title': title, 'date': '2001-05-05',
        'artist-credit': [{'name': artist}],
        'release-group': {'id': 'rg-' + mbid, 'primary-type': 'Album'},
        'media': [{'position': disc, 'tracks': [
            {'title': name, 'position': index, 'length': 180000,
             'recording': f'{mbid}-rec-{index}'}
            for index, name in enumerate(titles, start=1)]}],
    }


class FakeMusicBrainz:
    def __init__(self, searches=None, details=None, recordings=None):
        self.searches = searches or {}
        self.details = details or {}
        self.recordings = recordings or {}

    def release_search(self, album, artist, limit=8):
        return self.searches.get(album, [])

    def release(self, mbid):
        return self.details[mbid]

    def recording_search(self, title, artist, limit=6):
        return self.recordings.get(title, [])


class MatchTests(unittest.TestCase):
    def test_track_matching_prefers_same_title_and_duration(self):
        tracks = [track('a.mp3', title='ASGORE', length=200),
                  track('b.mp3', title='Finale', length=180)]
        mb_tracks = [{'title': 'Finale', 'disc': 1, 'position': 2,
                      'length': 181, 'recording': 'r2'},
                     {'title': 'ASGORE', 'disc': 1, 'position': 1,
                      'length': 199, 'recording': 'r1'}]
        matches = organize.match_tracks(tracks, mb_tracks)
        self.assertEqual(matches['a.mp3']['recording'], 'r1')
        self.assertEqual(matches['b.mp3']['recording'], 'r2')


class PlanTests(unittest.TestCase):
    def test_release_match_sets_album_and_track_numbers(self):
        mb = FakeMusicBrainz(
            searches={'Album A': [release_summary('rel-1', 'Album A', 2)]},
            details={'rel-1': release_detail('rel-1', 'Album A',
                                             ['First', 'Second'])})
        tracks = [track('old/First.mp3', album='Album A', albumartist='Artist'),
                  track('old/Second.mp3', album='Album A', albumartist='Artist')]
        stats = {}
        albums, unresolved = organize.plan_tracks(mb, tracks, {}, stats)
        self.assertEqual(unresolved, [])
        self.assertEqual(albums[0].album, 'Album A')
        self.assertEqual(stats.get('mb_release'), 1)
        reasons = sorted(t.reason for t in tracks)
        self.assertEqual(reasons, ['mb-release', 'mb-release'])
        self.assertEqual(sorted(t.position for t in tracks), [1, 2])

    def test_recording_match_resolves_orphan_single(self):
        recording = {
            'id': 'rel-9-rec-1', 'title': 'Song B',
            'artist-credit': [{'name': 'Artist B'}],
            'releases': [{'id': 'rel-9', 'title': 'Single B', 'date': '2010',
                          'artist-credit': [{'name': 'Artist B'}],
                          'release-group': {'primary-type': 'Single'}}],
        }
        mb = FakeMusicBrainz(
            recordings={'Song B': [recording]},
            details={'rel-9': release_detail('rel-9', 'Single B', ['Song B'],
                                             artist='Artist B')})
        tracks = [track('old/jpop/Song B.mp3', artist='Artist B')]
        albums, unresolved = organize.plan_tracks(mb, tracks, {}, {})
        self.assertEqual(unresolved, [])
        self.assertEqual(albums[0].album, 'Single B')
        self.assertEqual(albums[0].albumartist, 'Artist B')
        # 録音一致でも選んだリリースを控え、カバー取得に使う。
        self.assertEqual(albums[0].mb_release, 'rel-9')
        self.assertEqual(tracks[0].reason, 'mb-recording')
        self.assertEqual(tracks[0].position, 1)

    def test_skip_lookup_uses_the_alias_without_network_calls(self):
        mb = mock.Mock()
        aliases = {'folders': {'youtube': {
            'album': 'Album X', 'albumartist': 'Artist X', 'skip_lookup': True}}}
        tracks = [track('youtube/a.mp3', title='Song')]
        albums, unresolved = organize.plan_tracks(mb, tracks, aliases, {})
        mb.release_search.assert_not_called()
        mb.recording_search.assert_not_called()
        self.assertEqual(unresolved, [])
        self.assertEqual(albums[0].album, 'Album X')
        self.assertEqual(tracks[0].reason, 'fallback')

    def test_disabled_lookup_reorganizes_by_existing_tags_only(self):
        # 手でタグを直したあとの再整理（plan --no-lookup）はMBで上書きしない。
        mb = mock.Mock()
        mb.disabled = True
        tracks = [track('old/a.mp3', album='Album A', albumartist='Artist A')]
        albums, unresolved = organize.plan_tracks(mb, tracks, {}, {})
        mb.release_search.assert_not_called()
        mb.recording_search.assert_not_called()
        self.assertEqual(unresolved, [])
        self.assertEqual(albums[0].album, 'Album A')
        self.assertEqual(tracks[0].reason, 'fallback')

    def test_per_file_corrections_override_tags_before_planning(self):
        tracks = [track('現在のパス/a.mp3', title='old', album='Wrong',
                        albumartist='Someone')]
        corrections = {'現在のパス/a.mp3': {
            'title': '正しい曲名', 'album': '正しいアルバム',
            'albumartist': '正しい人', 'comment': '出典: https://example.com'}}
        organize.apply_corrections(tracks, corrections)
        self.assertEqual(tracks[0].title, '正しい曲名')
        self.assertEqual(tracks[0].album, '正しいアルバム')
        self.assertEqual(tracks[0].albumartist, '正しい人')
        self.assertEqual(tracks[0].comment, '出典: https://example.com')
        mb = mock.Mock()
        mb.disabled = True
        albums, _ = organize.plan_tracks(mb, tracks, {}, {})
        self.assertEqual(albums[0].album, '正しいアルバム')

    def test_unresolved_files_are_left_in_place(self):
        mb = FakeMusicBrainz()
        tracks = [track('misc/random junk.mp3')]
        albums, unresolved = organize.plan_tracks(mb, tracks, {}, {})
        self.assertEqual(albums, [])
        self.assertEqual(len(unresolved), 1)
        organize.assign_targets(Path('/tmp/does-not-matter'),
                                [organize.Album(album='_未解決',
                                                albumartist='_未解決',
                                                tracks=unresolved)])
        self.assertEqual(tracks[0].action, 'keep')
        self.assertEqual(tracks[0].target, tracks[0].source)

    def test_fallback_keeps_existing_album_and_artist(self):
        mb = FakeMusicBrainz()
        tracks = [track('old/game/01 Battle.mp3', album='Game OST',
                        albumartist='Composer')]
        albums, unresolved = organize.plan_tracks(mb, tracks, {}, {})
        self.assertEqual(unresolved, [])
        self.assertEqual(albums[0].album, 'Game OST')
        self.assertEqual(albums[0].albumartist, 'Composer')
        self.assertEqual(tracks[0].reason, 'fallback')


class TargetTests(unittest.TestCase):
    def build(self, tracks):
        album = organize.Album(album='Album', albumartist='Artist', tracks=tracks)
        organize.assign_targets(Path('/music'), [album])
        return album

    def test_targets_use_artist_album_track_title(self):
        album = self.build([track('old/a.mp3', title='Song', position=3)])
        self.assertEqual(album.tracks[0].target, 'Artist/Album/03 - Song.mp3')

    def test_multi_disc_albums_get_disc_folders(self):
        album = self.build([
            track('old/a.mp3', title='One', position=1, disc=1),
            track('old/b.mp3', title='Two', position=2, disc=2)])
        self.assertEqual(album.tracks[1].target, 'Artist/Album/Disc 2/02 - Two.mp3')

    def test_wide_albums_use_three_digit_numbers(self):
        tracks = [track(f'old/{index}.mp3', title=f'Song {index}', position=index)
                  for index in range(1, 102)]
        album = self.build(tracks)
        self.assertTrue(album.tracks[0].target.endswith('/001 - Song 1.mp3'))

    def test_duplicate_titles_do_not_overwrite(self):
        album = self.build([track('old/a.mp3', title='Same', position=1),
                            track('old/b.mp3', title='Same', position=2)])
        self.assertEqual(album.tracks[0].target, 'Artist/Album/01 - Same.mp3')
        self.assertEqual(album.tracks[1].target, 'Artist/Album/02 - Same.mp3')

    def test_merged_tracks_get_unique_track_numbers(self):
        # 別リリースから合流した曲のトラック番号重複は後ろへ回す。
        album = self.build([
            track('old/a.mp3', title='One', position=3),
            track('old/b.mp3', title='Two', position=3),
            track('old/c.mp3', title='Three', position=0)])
        numbers = sorted(t.position for t in album.tracks)
        self.assertEqual(numbers, [3, 4, 5])


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'music'
        self.state = Path(self.tmp.name) / 'state'
        (self.root / 'old').mkdir(parents=True)
        (self.state / 'tag-backups').mkdir(parents=True)
        self.manifest = {
            'root': str(self.root),
            'albums': [{
                'album': 'Album', 'albumartist': 'Artist',
                'cover': {'status': 'missing', 'staged': '', 'source': ''},
                'tracks': [{
                    'source': 'old/a.mp3', 'target': 'Artist/Album/01 - Song.mp3',
                    'action': 'move', 'title': 'Song', 'artist': 'Artist',
                    'album': 'Album', 'albumartist': 'Artist', 'date': '',
                    'genre': '', 'tracknumber': '1', 'discnumber': '1',
                    'reason': 'fallback', 'mb_recording': '', 'release': '',
                }],
            }],
        }
        self.manifest_path = Path(self.tmp.name) / 'manifest.json'
        self.manifest_path.write_text(json.dumps(self.manifest))

    def tearDown(self):
        self.tmp.cleanup()

    def test_apply_moves_files_and_undo_restores_them(self):
        (self.root / 'old/a.mp3').write_bytes(b'audio')
        with mock.patch.object(organize, 'write_tags', return_value=False):
            organize.command_apply(type('Args', (), {
                'manifest': str(self.manifest_path), 'state': str(self.state),
                'cleanup': True})())
        moved = self.root / 'Artist/Album/01 - Song.mp3'
        self.assertTrue(moved.exists())
        journals = list(self.state.glob('journal-*.json'))
        self.assertEqual(len(journals), 1)
        organize.command_undo(type('Args', (), {
            'journal': str(journals[0]), 'root': str(self.root),
            'state': str(self.state)})())
        self.assertTrue((self.root / 'old/a.mp3').exists())
        self.assertFalse(moved.exists())

    def test_apply_never_overwrites_an_existing_target(self):
        occupied = self.root / 'Artist/Album/01 - Song.mp3'
        occupied.parent.mkdir(parents=True)
        occupied.write_bytes(b'other')
        (self.root / 'old/a.mp3').write_bytes(b'audio')
        with mock.patch.object(organize, 'write_tags', return_value=False):
            organize.command_apply(type('Args', (), {
                'manifest': str(self.manifest_path), 'state': str(self.state),
                'cleanup': False})())
        self.assertEqual(occupied.read_bytes(), b'other')
        self.assertTrue((self.root / 'Artist/Album/01 - Song (2).mp3').exists())

    def test_apply_reuses_a_legacy_folder_image_as_cover(self):
        (self.root / 'old/a.mp3').write_bytes(b'audio')
        (self.root / 'old/Folder.jpg').write_bytes(b'\xff\xd8' + b'x' * 9000)
        with mock.patch.object(organize, 'write_tags', return_value=False):
            organize.command_apply(type('Args', (), {
                'manifest': str(self.manifest_path), 'state': str(self.state),
                'cleanup': False})())
        cover = self.root / 'Artist/Album/cover.jpg'
        self.assertTrue(cover.exists())
        self.assertTrue(cover.read_bytes().startswith(b'\xff\xd8'))

    def test_apply_moves_sidecar_lyrics_and_undo_restores_them(self):
        (self.root / 'old/a.mp3').write_bytes(b'audio')
        (self.root / 'old/a.lrc').write_text('[00:01.00] line')
        with mock.patch.object(organize, 'write_tags', return_value=False):
            organize.command_apply(type('Args', (), {
                'manifest': str(self.manifest_path), 'state': str(self.state),
                'cleanup': True})())
        moved = self.root / 'Artist/Album/01 - Song.lrc'
        self.assertEqual(moved.read_text(), '[00:01.00] line')
        self.assertFalse((self.root / 'old/a.lrc').exists())
        journals = list(self.state.glob('journal-*.json'))
        organize.command_undo(type('Args', (), {
            'journal': str(journals[0]), 'root': str(self.root),
            'state': str(self.state)})())
        self.assertEqual((self.root / 'old/a.lrc').read_text(), '[00:01.00] line')
        self.assertFalse(moved.exists())


if __name__ == '__main__':
    unittest.main()
