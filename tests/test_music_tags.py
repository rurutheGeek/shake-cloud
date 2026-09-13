"""Guard the music tag API and its deployment (music-tools on media-01).

The shake_tags Nextcloud app edits audio tags through this API; MusicBrainz
fills the candidate list for the Picard-style lookup.
"""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock
import urllib.error

import yaml

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/music-tools'
SOURCE = STACK / 'tag_api.py'
PLAYBOOK = ROOT / 'platform/ansible/music-tools.yml'
SOPS_EXAMPLE = ROOT / 'platform/sops/music-tags.sops.yaml.example'

spec = importlib.util.spec_from_file_location('tag_api', SOURCE)
tag_api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tag_api)


def read(path):
    return path.read_text(encoding='utf-8')


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class PathTests(unittest.TestCase):
    def test_nextcloud_paths_are_reduced_to_the_library_root(self):
        for raw in ('/music/YouTube/song.mp3', '/library/music/YouTube/song.mp3',
                    'YouTube/song.mp3', '%2Fmusic%2FYouTube%2Fsong.mp3'):
            self.assertEqual(tag_api.normalize_path(raw, '/music'),
                             Path('YouTube/song.mp3'), raw)

    def test_a_path_music_root_is_accepted(self):
        # 実機の server.music は Path。rstrip を直接呼ぶと落ちる（2026-09-13実測）。
        self.assertEqual(tag_api.normalize_path('/music/a.mp3', Path('/music')),
                         Path('a.mp3'))

    def test_traversal_and_other_extensions_are_refused(self):
        for raw in ('../secret.mp3', '/library/books/book.mp3',
                    '/music/song.flac', '/music/../etc/passwd.mp3', ''):
            with self.assertRaises(ValueError, msg=raw):
                tag_api.normalize_path(raw, '/music')


class TagValueTests(unittest.TestCase):
    def test_values_are_flattened_to_string_lists(self):
        clean = tag_api.clean_tags({'title': 'Song', 'artist': ['A', 'B'],
                                    'tracknumber': '3', 'album': ''})
        self.assertEqual(clean, {'title': ['Song'], 'artist': ['A', 'B'],
                                 'tracknumber': ['3']})

    def test_unsupported_fields_are_refused(self):
        with self.assertRaises(ValueError):
            tag_api.clean_tags({'comment': 'nope'})
        with self.assertRaises(ValueError):
            tag_api.clean_tags('not a dict')


class MusicBrainzTests(unittest.TestCase):
    def test_the_query_uses_the_fields_that_are_known(self):
        self.assertEqual(tag_api.mb_query('A', 'Song', 'Album'),
                         'recording:"Song" AND artist:"A" AND release:"Album"')
        self.assertEqual(tag_api.mb_query('', 'Song', ''),
                         'recording:"Song"')
        self.assertEqual(tag_api.mb_query('', '', ''), '')

    def test_candidates_are_read_from_the_search_response(self):
        fixture = {'recordings': [{
            'id': 'rec-1',
            'title': 'Song',
            'artist-credit': [{'name': 'A', 'artist': {'name': 'A'}}, ' & ',
                              {'name': 'B', 'artist': {'name': 'B'}}],
            'releases': [{'title': 'Album', 'date': '2020-03-01'}],
        }]}
        with mock.patch.object(tag_api.urllib.request, 'urlopen',
                               return_value=FakeResponse(fixture)):
            candidates = tag_api.mb_candidates('A', 'Song', 'Album')
        self.assertEqual(candidates, [{'title': 'Song', 'artist': 'A & B',
                                      'album': 'Album', 'date': '2020',
                                      'musicbrainzId': 'rec-1'}])

    def test_a_lookup_failure_is_reported(self):
        with mock.patch.object(tag_api.urllib.request, 'urlopen',
                              side_effect=urllib.error.URLError('down')):
            with self.assertRaises(RuntimeError):
                tag_api.mb_candidates('A', 'Song', 'Album')


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.compose = yaml.safe_load(read(STACK / 'compose.yaml'))
        self.lock = yaml.safe_load(read(STACK / 'compose.lock.yaml'))
        self.play = yaml.safe_load(read(PLAYBOOK))[0]

    def test_the_service_requires_the_token_and_listens_with_it(self):
        service = self.compose['services']['tag-api']
        self.assertEqual(service['environment']['TAG_API_TOKEN'],
                         '${TAG_API_TOKEN:-}')
        self.assertEqual(service['environment']['TAG_API_PORT'], '5810')
        self.assertIn('5810', service['ports'][0])
        self.assertIn('/tools/tag_api.py', service['entrypoint'])

    def test_the_image_is_pinned_in_the_lock(self):
        image = self.lock['services']['tag-api']['image']
        self.assertIn('@sha256:', image)
        self.assertEqual(image, self.lock['services']['metube']['image'])

    def test_the_playbook_ships_the_api_and_its_token(self):
        services = self.play['vars']['music_tools_services']
        self.assertIn('tag-api', services)
        copy_task = [task for task in self.play['tasks']
                     if task['name'] == 'Copy tool definitions'][0]
        self.assertIn('tag_api.py', str(copy_task['loop']))
        text = read(PLAYBOOK)
        self.assertIn('music-tags.sops.yaml', text)
        self.assertIn("'tag-api' in music_tools_services", text)
        self.assertIn('TAG_API_TOKEN=', text)

    def test_the_storage_directory_is_prepared(self):
        self.assertIn("'tags'", read(STACK / 'manage.py'))

    def test_the_code_hash_forces_a_recreate(self):
        # バインドマウントのコードは up では入れ替わらない。convert と同じく
        # ハッシュをラベルに載せて再作成させる。
        labels = self.compose['services']['tag-api']['labels']
        self.assertEqual(labels['media-stack.tag-api-code'],
                         '${TAG_API_CODE_SHA:-unmanaged}')
        self.assertIn('TAG_API_CODE_SHA', read(STACK / 'manage.py'))

    def test_the_sops_example_documents_the_token(self):
        example = read(SOPS_EXAMPLE)
        self.assertIn('TAG_API_TOKEN:', example)
        self.assertIn('REPLACE_WITH_A_RANDOM_TOKEN', example)


APP = ROOT / 'stacks/media/nextcloud/apps/shake_tags'
NC_PLAYBOOK = ROOT / 'platform/ansible/media-nextcloud.yml'
GROUP_VARS = ROOT / 'platform/ansible/group_vars/media.yml'


class AppTests(unittest.TestCase):
    def test_info_declares_the_app_and_the_namespace(self):
        info = read(APP / 'appinfo/info.xml')
        application = read(APP / 'lib/AppInfo/Application.php')
        self.assertIn('<id>shake_tags</id>', info)
        self.assertIn('<namespace>ShakeTags</namespace>', info)
        self.assertIn('namespace OCA\\ShakeTags\\AppInfo;', application)

    def test_the_files_script_is_registered(self):
        listener = read(APP / 'lib/Listener/LoadAdditionalScripts.php')
        self.assertIn("Util::addInitScript('shake_tags', 'tags')", listener)

    def test_the_controller_relays_tags_and_musicbrainz(self):
        controller = read(APP / 'lib/Controller/TagsController.php')
        self.assertIn("#[FrontpageRoute(verb: 'GET', url: '/tags')]", controller)
        self.assertIn("#[FrontpageRoute(verb: 'POST', url: '/tags')]", controller)
        self.assertIn("#[FrontpageRoute(verb: 'GET', url: '/search')]", controller)
        self.assertIn("getAppValue('shake_tags', 'tags_api_url'", controller)
        self.assertIn("getAppValue('shake_tags', 'tags_api_token'", controller)
        self.assertIn('/musicbrainz', controller)

    def test_non_admins_may_use_the_tag_routes(self):
        # AppFramework は既定で管理者のみ。付けないと一般ユーザーは403になる（実測）。
        controller = read(APP / 'lib/Controller/TagsController.php')
        self.assertIn('use OCP\\AppFramework\\Http\\Attribute\\NoAdminRequired;', controller)
        self.assertEqual(controller.count('#[NoAdminRequired]'), 3)

    def test_the_action_uses_the_files_context_signature(self):
        source = read(APP / 'src/tags.js')
        self.assertIn('enabled: ({ nodes })', source)
        self.assertIn('exec: ({ nodes })', source)

    def test_the_bundle_registers_the_tag_action(self):
        bundle = read(APP / 'js/tags.js')
        self.assertIn('registerFileAction', bundle)
        self.assertIn('/apps/shake_tags/tags', bundle)
        self.assertIn('/apps/shake_tags/search', bundle)
        self.assertIn('MusicBrainz', bundle)
        # NC33のFilesアプリは @nextcloud/files v4 のグローバルレジストリ
        # （window._nc_files_scope）を共有し、register:action で更新する。
        # v3系をバンドルすると別インスタンスになりメニューに出ない（実測）。
        self.assertIn('_nc_files_scope', bundle)
        self.assertIn('register:action', bundle)

    def test_the_action_matches_the_v4_dotted_extension(self):
        source = read(APP / 'src/tags.js')
        self.assertIn("replace(/^\\./, '')", source)
        package = json.loads(read(APP / 'package.json'))
        self.assertEqual(package['dependencies']['@nextcloud/files'], '^4.0.0')


class NextcloudDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.play = yaml.safe_load(read(NC_PLAYBOOK))[0]
        self.tasks = self.play['tasks']

    def task(self, name):
        return next(task for task in self.tasks if task['name'] == name)

    def test_the_app_is_copied_into_the_nextcloud_html_volume(self):
        task = self.task('Copy the tag editor app')
        self.assertIn('apps/shake_tags/', task['ansible.builtin.copy']['src'])
        self.assertIn('custom_apps/shake_tags', task['ansible.builtin.copy']['dest'])

    def test_the_api_url_and_token_are_configured(self):
        task = self.task('Point the tag editor app at the music-tools tag API')
        self.assertIn('TAGS_API_URL', task['environment'])
        self.assertIn('TAGS_API_TOKEN', task['environment'])
        self.assertTrue(task['no_log'])

    def test_the_play_reads_the_token_from_sops(self):
        readers = [task for task in self.tasks
                   if 'ansible.builtin.command' in task
                   and 'music-tags.sops.yaml'
                   in str(task['ansible.builtin.command']['argv'])]
        self.assertEqual(len(readers), 1)
        self.assertTrue(readers[0]['no_log'])

    def test_the_group_var_matches_the_service_port(self):
        group = yaml.safe_load(read(GROUP_VARS))
        self.assertEqual(group['nextcloud_tags_api_url'],
                         'http://192.168.10.101:5810')


if __name__ == '__main__':
    unittest.main()
