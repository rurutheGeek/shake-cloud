"""Pokémon-aware translator: dictionary, term protection and deployment checks."""

import importlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/poke-translate'
sys.path.insert(0, str(STACK))
dictionary = importlib.import_module('dictionary')

TABLES = {
    'pokemon_species_names': 'pokemon_species_id,local_language_id,name,genus\n'
                             '445,11,ガブリアス,\n445,1,ガブリアス,マッハポケモン\n445,9,Garchomp,Mach Pokémon\n'
                             '6,1,リザードン,\n6,9,Charizard,\n',
    'move_names': 'move_id,local_language_id,name\n89,1,じしん\n89,9,Earthquake\n'
                  '94,1,サイコキネシス\n94,9,Psychic\n',
    'ability_names': 'ability_id,local_language_id,name\n24,1,さめはだ\n24,9,Rough Skin\n',
    'item_names': 'item_id,local_language_id,name\n264,1,こだわりスカーフ\n264,9,Choice Scarf\n',
    'type_names': 'type_id,local_language_id,name\n12,1,くさ\n12,9,Grass\n14,1,エスパー\n14,9,Psychic\n',
    'nature_names': 'nature_id,local_language_id,name\n2,1,ずぶとい\n2,9,Bold\n',
    'location_names': 'location_id,local_language_id,name\n',
    'pokemon_form_names': 'pokemon_form_id,local_language_id,form_name,pokemon_name\n'
                          '10134,1,メガリザードンＸ,\n10134,9,Mega Charizard X,Mega Charizard X\n'
                          '10193,1,アローラのすがた,\n10081,1,れいじゅうフォルム,\n',
    'stat_names': 'stat_id,local_language_id,name\n6,1,すばやさ\n6,9,Speed\n7,1,めいちゅう\n7,9,accuracy\n',
    'pokemon_forms': 'id,identifier,form_identifier,pokemon_id\n'
                     '10134,charizard-mega-x,mega-x,10034\n10081,landorus-therian,therian,10021\n'
                     '6,charizard,,6\n',
    'pokemon': 'id,identifier,species_id\n6,charizard,6\n10034,charizard-mega-x,6\n'
               '10021,landorus-therian,645\n',
}
TABLES['pokemon_species_names'] += '645,1,ランドロス,\n645,9,Landorus,\n'


class DictionaryTests(unittest.TestCase):
    def test_kana_names_are_canonical_and_kanji_names_are_aliases(self):
        entries = dictionary.parse_csvs(TABLES)
        self.assertEqual(entries['species:445']['ja'][0], 'ガブリアス')
        self.assertEqual(entries['move:89']['en'], ['Earthquake'])

    def test_forms_keep_only_full_names_and_add_halfwidth_variants(self):
        entries = dictionary.parse_csvs(TABLES)
        self.assertEqual(entries['form:10134']['ja'], ['メガリザードンＸ', 'メガリザードンX'])
        self.assertNotIn('form:10193', entries)

    def test_type_words_are_generated_for_explicit_type_mentions(self):
        typed = dictionary.parse_csvs(TABLES)['type:12:typed']
        self.assertEqual(typed['ja'], ['くさタイプ'])
        self.assertEqual(typed['en'], ['Grass-type', 'Grass-types', 'Grass type', 'Grass types'])

    def test_stats_skip_accuracy_and_evasion(self):
        entries = dictionary.parse_csvs(TABLES)
        self.assertEqual(entries['stat:6']['ja'], ['すばやさ'])
        self.assertNotIn('stat:7', entries)

    def test_overseas_form_names_map_to_japanese_names(self):
        entries = dictionary.parse_csvs(TABLES)
        self.assertEqual(entries['form:10081']['ja'][0], 'ランドロス（れいじゅうフォルム）')
        self.assertEqual(entries['form:10081']['en'], ['Landorus-Therian'])
        self.assertIn('Charizard-Mega-X', entries['form:10134']['en'])
        self.assertEqual(entries['form:10134']['ja'][0], 'メガリザードンＸ')

    def test_type_phrases_and_showdown_nature_lines_are_generated(self):
        entries = dictionary.parse_csvs(TABLES)
        self.assertEqual(entries['type:14:無効'], {'ja': ['エスパー無効'],
                                                  'en': ['Psychic immunity', 'Psychic immunities']})
        self.assertEqual(entries['type:12:tera'], {'ja': ['くさテラス'], 'en': ['Tera Grass']})
        self.assertEqual(entries['nature:2:line'], {'ja': ['性格: ずぶとい'], 'en': ['Bold Nature']})

    def test_custom_terms_extend_or_add_and_unknown_refs_fail(self):
        base = {'entries': dictionary.parse_csvs(TABLES)}
        built = dictionary.build(base, {'terms': [{'ref': 'species:445', 'ja': ['ガブ']},
                                                  {'ja': ['S振り'], 'en': 'Speed investment'}],
                                        'ambiguous': {'en': ['Bold']}})
        self.assertIn('ガブ', built['entries']['species:445']['ja'])
        self.assertEqual(built['entries']['custom:1'],
                         {'ja': ['S振り'], 'en': ['Speed investment'], '_custom': True})
        self.assertEqual(built['ambiguous'], {'en': ['Bold']})
        with self.assertRaises(ValueError):
            dictionary.build(base, {'terms': [{'ref': 'species:99999', 'ja': ['x']}]})

    def test_the_committed_custom_terms_are_well_formed(self):
        custom = json.loads((STACK / 'custom-terms.json').read_text(encoding='utf-8'))
        for term in custom['terms']:
            if 'ref' in term:
                self.assertRegex(term['ref'], r'^[a-z]+:\d+$')
            else:
                self.assertIn('ja', term)
                self.assertIn('en', term)
        languages = set(dictionary.LANGUAGES.values())
        self.assertLessEqual(set(custom['exclude']) | set(custom['ambiguous']), languages)

    def test_pokeapi_is_fetched_at_the_requested_ref(self):
        seen = []

        def opener(url, timeout):
            seen.append(url)
            return io.BytesIO(TABLES[url.rsplit('/', 1)[1][:-4]].encode('utf-8'))

        built = dictionary.fetch_pokeapi('abc123', opener)
        self.assertEqual(built['source'], 'PokeAPI/pokeapi@abc123')
        self.assertTrue(all('/abc123/data/v2/csv/' in url for url in seen))


FIXTURE_CUSTOM = {
    'terms': [{'ref': 'species:445', 'ja': ['ガブ']}, {'ja': ['タイプ一致'], 'en': ['STAB']}],
    'ambiguous': {}, 'exclude': {},
}


class CoreTests(unittest.TestCase):
    """core/poketr.js の照合・翻訳を node --test で確かめる。"""

    def test_javascript_core(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node is not installed')
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / 'dictionary.json'
            built = dictionary.build({'entries': dictionary.parse_csvs(TABLES)}, FIXTURE_CUSTOM)
            fixture.write_text(json.dumps(built, ensure_ascii=False), encoding='utf-8')
            result = subprocess.run(
                [node, '--test', str(STACK / 'core/poketr.test.js')],
                env={**os.environ, 'POKETR_FIXTURE': str(fixture)},
                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.extension = STACK / 'extension'
        self.manifest = json.loads((self.extension / 'manifest.json').read_text(encoding='utf-8'))

    def test_manifest_v3_references_existing_files(self):
        self.assertEqual(self.manifest['manifest_version'], 3)
        for name in [self.manifest['background']['service_worker'],
                     self.manifest['options_ui']['page'], 'content.js', 'content.css', 'options.js']:
            self.assertTrue((self.extension / name).is_file(), name)

    def test_translation_runs_in_the_service_worker_without_a_server(self):
        # ページ側から fetch すると閲覧中サイトの CORS・CSP を受ける。
        self.assertNotIn('fetch(', (self.extension / 'content.js').read_text(encoding='utf-8'))
        background = (self.extension / 'background.js').read_text(encoding='utf-8')
        self.assertIn("importScripts('poketr.js')", background)
        self.assertEqual(self.manifest['host_permissions'], ['https://translate.googleapis.com/*'])

    def test_bundled_core_and_dictionary_are_generated_not_committed(self):
        for name in ['poketr.js', 'dictionary.json']:
            ignored = subprocess.run(['git', 'check-ignore', '-q', str(self.extension / name)], cwd=ROOT)
            self.assertEqual(ignored.returncode, 0, name)

    def test_code_blocks_and_inputs_are_not_translated(self):
        content = (self.extension / 'content.js').read_text(encoding='utf-8')
        for tag in ['PRE', 'CODE', 'TEXTAREA', 'INPUT', 'SCRIPT', 'STYLE', 'POKE-TR']:
            self.assertIn(f"'{tag}'", content)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.service = yaml.safe_load((STACK / 'compose.yaml').read_text())['services']['site']

    def test_the_site_is_static_loopback_only_and_read_only(self):
        self.assertEqual(self.service['ports'], ['127.0.0.1:${POKE_TRANSLATE_PORT:-8320}:8080'])
        self.assertTrue(self.service['read_only'])
        self.assertEqual(self.service['cap_drop'], ['ALL'])
        self.assertEqual(self.service['volumes'], ['${STORAGE_ROOT:-/srv/services/poke-translate}/site:/srv:ro'])

    def test_the_role_copies_every_tracked_stack_file(self):
        tasks = (ROOT / 'platform/ansible/roles/poke_translate/tasks/main.yml').read_text(encoding='utf-8')
        tracked = subprocess.run(['git', 'ls-files', '--others', '--cached', '--exclude-standard'],
                                 cwd=STACK, capture_output=True, text=True, check=True).stdout.split()
        for name in tracked:
            if name not in {'README.md', 'core/poketr.test.js'}:
                self.assertIn(f'- {name}', tasks)

    def test_build_writes_the_site_extension_and_zip_from_one_core(self):
        manage = importlib.import_module('manage')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(STACK, root / 'stack', ignore=shutil.ignore_patterns('storage', '__pycache__'))
            for name in ['poketr.js', 'dictionary.json']:
                (root / 'stack/extension' / name).unlink(missing_ok=True)
            (root / 'stack/custom-terms.json').write_text(json.dumps(FIXTURE_CUSTOM), encoding='utf-8')
            base = {'source': 'test', 'entries': dictionary.parse_csvs(TABLES)}
            (root / 'stack/storage').mkdir()
            (root / 'stack/storage/pokeapi.json').write_text(json.dumps(base), encoding='utf-8')
            with patch.multiple(manage, ROOT=root / 'stack', EXTENSION=root / 'stack/extension'), \
                    patch.object(dictionary, 'fetch_pokeapi', side_effect=AssertionError('no fetch')):
                manage.build()
                self.assertEqual(manage.write(root / 'stack/storage/site/poketr.js',
                                              (STACK / 'core/poketr.js').read_bytes()), False)
                first = manage.extension_zip()
                self.assertEqual(manage.extension_zip(), first)
            site = root / 'stack/storage/site'
            core = (STACK / 'core/poketr.js').read_bytes()
            self.assertEqual((site / 'poketr.js').read_bytes(), core)
            self.assertEqual((root / 'stack/extension/poketr.js').read_bytes(), core)
            with zipfile.ZipFile(site / 'poke-translate-extension.zip') as archive:
                self.assertLessEqual({'manifest.json', 'background.js', 'poketr.js', 'dictionary.json'},
                                     set(archive.namelist()))
            built = json.loads((site / 'dictionary.json').read_text(encoding='utf-8'))
            self.assertIn('ガブ', built['entries']['species:445']['ja'])


if __name__ == '__main__':
    unittest.main()
