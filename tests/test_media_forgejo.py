"""Guard the Forgejo unit for media-01 (the repository archive).

The archive only earns its place if it keeps what it took: data on the HDD
volume, mirrors that are never deleted by the reconciler, nothing visible
without signing in, and a memory cap so a sync cannot take the other units down.
These are source-text, YAML and JSON assertions plus manage.py's pure helpers;
nothing here connects to media-01 or runs Docker.
"""
import json
from pathlib import Path
import unittest
from unittest import mock

import yaml

from support import compose_stack_vars, load_module, scratch_dir

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / 'stacks/media/forgejo'
COMPOSE = yaml.safe_load((UNIT / 'compose.yaml').read_text(encoding='utf-8'))
LOCK = yaml.safe_load((UNIT / 'compose.lock.yaml').read_text(encoding='utf-8'))
DNS = yaml.safe_load((ROOT / 'platform/terraform/dns.yaml').read_text(encoding='utf-8'))
GROUP_VARS = yaml.safe_load((ROOT / 'platform/ansible/group_vars/media.yml').read_text(encoding='utf-8'))
PLAYBOOK = ROOT / 'platform/ansible/media-forgejo.yml'
SSO_PLAYBOOK = ROOT / 'platform/ansible/media-forgejo-sso.yml'
SERVICE = COMPOSE['services']['forgejo']
ENVIRONMENT = SERVICE['environment']


class ComposeTests(unittest.TestCase):
    def test_it_is_an_independent_project(self):
        self.assertEqual(COMPOSE['name'], 'media-forgejo')
        self.assertEqual(list(COMPOSE['services']), ['forgejo'])

    def test_the_port_is_loopback_only_and_ssh_is_off(self):
        self.assertEqual(SERVICE['ports'], ['127.0.0.1:${FORGEJO_PORT:-8083}:3000'])
        self.assertEqual(ENVIRONMENT['FORGEJO__server__DISABLE_SSH'], 'true')

    def test_memory_is_capped(self):
        self.assertEqual(SERVICE['mem_limit'], '${FORGEJO_MEMORY_LIMIT:-512m}')

    def test_nothing_is_visible_without_signing_in(self):
        self.assertEqual(ENVIRONMENT['FORGEJO__service__REQUIRE_SIGNIN_VIEW'], 'true')
        self.assertEqual(ENVIRONMENT['FORGEJO__service__ALLOW_ONLY_EXTERNAL_REGISTRATION'], 'true')
        self.assertEqual(ENVIRONMENT['FORGEJO__openid__ENABLE_OPENID_SIGNUP'], 'false')

    def test_secrets_come_from_manage_py(self):
        for key in ('FORGEJO__security__SECRET_KEY', 'FORGEJO__security__INTERNAL_TOKEN',
                    'FORGEJO__oauth2__JWT_SECRET'):
            self.assertTrue(ENVIRONMENT[key].endswith(':?run manage.py up}'), key)

    def test_data_lives_under_the_storage_root(self):
        self.assertEqual(SERVICE['volumes'], ['${STORAGE_ROOT:-/srv/media-stack/storage}/forgejo:/data'])

    def test_the_image_is_pinned_by_digest(self):
        self.assertRegex(LOCK['services']['forgejo']['image'],
                         r'^codeberg\.org/forgejo/forgejo@sha256:[0-9a-f]{64}$')

    def test_mirrors_json_is_a_list(self):
        self.assertIsInstance(json.loads((UNIT / 'mirrors.json').read_text()), list)


class PlacementTests(unittest.TestCase):
    def test_the_data_directory_is_on_the_hdd_volume(self):
        binds = {item['source']: item for item in GROUP_VARS['media_bulk_binds']}
        self.assertEqual(binds['forgejo']['target'], '{{ storage_root }}/forgejo')
        self.assertEqual(binds['forgejo']['uid'], 1000)

    def test_dns_points_at_the_loopback_port(self):
        record = DNS['records']['forgejo']
        self.assertEqual(record['host'], 'media-01')
        self.assertEqual(record['upstream'], '127.0.0.1:8083')
        # Native OIDC: the proxy must not add Forward Auth in front.
        self.assertNotIn('auth', record)

    def test_identity_registers_the_callback(self):
        configure = load_module(ROOT / 'stacks/identity/configure.py', 'identity_configure_forgejo')
        self.assertEqual(configure.media_redirect('forgejo', 'example.org'),
                         'https://forgejo.example.org/user/oauth2/authentik/callback')
        self.assertIn('forgejo', configure.MEDIA_APPLICATIONS)


class PlaybookTests(unittest.TestCase):
    def setUp(self):
        self.play = yaml.safe_load(PLAYBOOK.read_text(encoding='utf-8'))[0]

    def test_it_refuses_to_write_to_the_ssd_when_the_bind_is_missing(self):
        first = self.play['tasks'][0]
        self.assertEqual(first['ansible.builtin.command']['argv'],
                         ['mountpoint', '-q', '{{ storage_root }}/forgejo'])

    def test_it_ships_the_mirror_list(self):
        stack = compose_stack_vars(self.play)
        self.assertIn('mirrors.json', stack['compose_stack_files'])
        self.assertIn('FORGEJO_ROOT_URL=https://forgejo.{{ media_forgejo_zone }}/', stack['compose_stack_env'])

    def test_the_sso_playbook_reads_the_forgejo_client_without_logging(self):
        text = SSO_PLAYBOOK.read_text(encoding='utf-8')
        self.assertIn('.forgejo.client_secret', text)
        self.assertIn('media/forgejo/secrets/oidc_client.json', text)
        self.assertNotIn('freshrss', text.lower())
        for task in yaml.safe_load(text)[0]['tasks']:
            if 'oidc' in task['name'].lower() or 'secret' in task['name'].lower() or 'credential' in task['name'].lower():
                self.assertTrue(task.get('no_log'), task['name'])


class ManageTests(unittest.TestCase):
    def setUp(self):
        self.manage = load_module(UNIT / 'manage.py', 'forgejo_manage')
        self.root = scratch_dir('forgejo-')
        (self.root / '.env').write_text('FORGEJO_MIRROR_INTERVAL=24h\nFORGEJO_ARCHIVE_ORG=archive\n')
        self.patch = mock.patch.object(self.manage, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def write_mirrors(self, entries):
        (self.root / 'mirrors.json').write_text(json.dumps(entries))

    def test_names_default_to_the_last_path_segment(self):
        self.write_mirrors([{'url': 'https://github.com/owner/repo.git'},
                            {'url': 'https://example.org/a/b/', 'name': 'kept'}])
        self.assertEqual([entry['name'] for entry in self.manage.mirror_list()], ['repo', 'kept'])

    def test_only_https_sources_and_unique_names_are_accepted(self):
        for entries in ([{'url': 'git@github.com:owner/repo.git'}],
                        [{'url': 'https://a.example/x/repo'}, {'url': 'https://b.example/y/repo'}]):
            self.write_mirrors(entries)
            with self.assertRaises(ValueError):
                self.manage.mirror_list()

    def test_existing_mirrors_are_left_alone_and_missing_ones_are_created(self):
        self.write_mirrors([{'url': 'https://github.com/owner/kept'},
                            {'url': 'https://github.com/owner/new', 'wiki': False}])
        calls = []

        def api(method, path, body=None):
            calls.append((method, path, body))
            if path == '/repos/archive/new':
                return 404, None
            return 200, {}
        with mock.patch.object(self.manage, 'api', api):
            self.manage.mirrors()
        posts = [call for call in calls if call[0] == 'POST']
        self.assertEqual(len(posts), 1)
        body = posts[0][2]
        self.assertEqual(posts[0][1], '/repos/migrate')
        self.assertTrue(body['mirror'])
        self.assertTrue(body['private'])
        self.assertFalse(body['wiki'])
        self.assertEqual((body['repo_owner'], body['repo_name'], body['mirror_interval']),
                         ('archive', 'new', '24h'))

    def test_the_reconciler_never_deletes(self):
        source = (UNIT / 'manage.py').read_text(encoding='utf-8')
        self.assertNotIn("'DELETE'", source)
        self.assertNotIn('"DELETE"', source)


if __name__ == '__main__':
    unittest.main()
