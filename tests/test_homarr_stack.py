"""Guard the Homarr stack's reconcile rules and its separation from the old hub.

The stack is Homarr alone on services-01. A test that let the old media-hub
services (Authentik, docs, other storage) creep back in, or that let a reapply
duplicate tiles, would be worse than no test.
"""
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/homarr'
SPEC = importlib.util.spec_from_file_location('homarr_configure', STACK / 'configure.py')
configure = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(configure)

# configure-integrations.py imports its sibling as `configure`.
import sys as _sys  # noqa: E402
_sys.modules['configure'] = configure
INT_SPEC = importlib.util.spec_from_file_location(
    'homarr_integrations', STACK / 'configure-integrations.py')
integrations = importlib.util.module_from_spec(INT_SPEC)
INT_SPEC.loader.exec_module(integrations)


class FakeHomarr:
    """In-memory stand-in that records calls, enough for configure()."""

    def __init__(self):
        self.calls = []
        self.onboarded = False
        self.logged_in = False
        self.boards = []
        self.apps = []
        self.items = []
        self.groups = [{'id': 'everyone', 'name': 'everyone'}]
        self.integrations = []
        self.next_id = 0

    def _id(self, prefix):
        self.next_id += 1
        return f'{prefix}{self.next_id}'

    def onboard(self, username, password):
        self.calls.append(('onboard', username))
        self.onboarded = True

    def login(self, username, password):
        self.calls.append(('login', username))
        self.logged_in = True

    def trpc(self, path, data=None, post=False):
        self.calls.append((path, data))
        if path == 'board.getAllBoards':
            return self.boards
        if path == 'board.createBoard':
            board = {'id': self._id('board'), 'name': data['name']}
            self.boards.append(board)
            return {'boardId': board['id']}
        if path == 'board.getBoardByName':
            board = next(row for row in self.boards if row['name'] == data['name'])
            return {**board, 'items': [item for item in self.items if item['boardId'] == board['id']]}
        if path == 'app.all':
            return self.apps
        if path == 'app.create':
            app = {'id': self._id('app'), 'name': data['name'], 'href': data.get('href')}
            self.apps.append(app)
            return {'appId': app['id']}
        if path == 'app.update':
            app = next(row for row in self.apps if row['id'] == data['id'])
            app.update(data)
            return {}
        if path == 'board.addItem':
            if data.get('kind') == 'app':
                self.items.append({'boardId': data['boardId'], 'kind': 'app',
                                   'options': {'json': {'appId': data['options']['appId']}},
                                   'integrationIds': []})
            else:
                self.items.append({'boardId': data['boardId'], 'kind': data['kind'],
                                   'options': data.get('options', {}),
                                   'integrationIds': data.get('integrationIds', [])})
            return {}
        if path == 'integration.all':
            return self.integrations
        if path == 'integration.create':
            row = {'id': self._id('integration'), 'name': data['name'],
                   'kind': data['kind'], 'url': data['url']}
            self.integrations.append(row)
            return {}
        if path == 'integration.update':
            row = next(item for item in self.integrations if item['id'] == data['id'])
            row.update({key: data[key] for key in ('name', 'url')})
            return {}
        if path == 'integration.saveGroupIntegrationPermissions':
            return {}
        if path == 'group.getAll':
            return self.groups
        if path == 'group.createGroup':
            self.groups.append({'id': self._id('group'), 'name': data['name']})
            return {}
        return {}

    def calls_to(self, path):
        return [data for name, data in self.calls if name == path]


def options(apps):
    directory = Path(tempfile.mkdtemp(prefix='homarr-test-'))
    path = directory / 'apps.json'
    path.write_text(json.dumps(apps), encoding='utf-8')
    return {
        'username': 'admin', 'password': 'secret',
        'board': 'home', 'apps_file': str(path),
        'admin_group': 'admins', 'locale': 'ja', 'title': 'ハブ',
    }


APPS = [
    {'name': 'Docs', 'href': 'https://docs.example', 'iconText': 'DOC'},
    {'name': 'NetBox', 'href': 'https://netbox.example'},
]


class ReconcileTests(unittest.TestCase):
    def test_the_first_run_creates_the_board_apps_and_items(self):
        homarr = FakeHomarr()
        configure.configure(homarr, options(APPS))
        self.assertTrue(homarr.onboarded)
        self.assertTrue(homarr.logged_in)
        self.assertEqual([board['name'] for board in homarr.boards], ['home'])
        self.assertEqual([app['name'] for app in homarr.apps], ['Docs', 'NetBox'])
        self.assertEqual(len(homarr.items), 2)

    def test_reapplying_adds_nothing_and_keeps_the_layout(self):
        homarr = FakeHomarr()
        configure.configure(homarr, options(APPS))
        configure.configure(homarr, options(APPS))
        self.assertEqual(len(homarr.items), 2)
        self.assertEqual(len(homarr.apps), 2)

    def test_an_existing_item_is_not_added_again(self):
        homarr = FakeHomarr()
        homarr.boards.append({'id': 'board1', 'name': 'home'})
        homarr.apps.append({'id': 'app1', 'name': 'Docs'})
        homarr.items.append({'boardId': 'board1', 'options': {'json': {'appId': 'app1'}}})
        configure.configure(homarr, options([APPS[0]]))
        self.assertEqual(len(homarr.items), 1)

    def test_a_renamed_app_is_updated_in_place(self):
        # Matching by href, not name, keeps a rename from leaving two tiles.
        homarr = FakeHomarr()
        homarr.boards.append({'id': 'board1', 'name': 'home'})
        homarr.apps.append({'id': 'app1', 'name': '日本語の手順書', 'href': 'https://docs.example'})
        homarr.items.append({'boardId': 'board1', 'options': {'json': {'appId': 'app1'}}})
        configure.configure(homarr, options([{'name': 'Shake Lab Docs', 'href': 'https://docs.example'}]))
        self.assertEqual(len(homarr.apps), 1)
        self.assertEqual(homarr.apps[0]['name'], 'Shake Lab Docs')
        self.assertEqual(len(homarr.items), 1)

    def test_a_declared_icon_url_is_used(self):
        homarr = FakeHomarr()
        configure.configure(homarr, options([{
            'name': 'Docs', 'href': 'https://docs.example',
            'iconUrl': 'https://icons.example/docs.svg'}]))
        self.assertEqual(homarr.calls_to('app.create')[-1]['iconUrl'],
                         'https://icons.example/docs.svg')

    def test_the_admin_group_is_created_once_and_gets_admin(self):
        homarr = FakeHomarr()
        configure.configure(homarr, options(APPS))
        configure.configure(homarr, options(APPS))
        self.assertEqual([group['name'] for group in homarr.groups].count('admins'), 1)
        permissions = homarr.calls_to('group.savePermissions')
        self.assertEqual(permissions[-1]['permissions'], ['admin'])

    def test_everyone_can_view_the_home_board(self):
        homarr = FakeHomarr()
        configure.configure(homarr, options(APPS))
        permission = homarr.calls_to('board.saveGroupBoardPermissions')[-1]
        self.assertEqual(permission['permissions'],
                         [{'principalId': 'everyone', 'permission': 'view'}])

    def test_the_culture_is_set(self):
        homarr = FakeHomarr()
        configure.configure(homarr, options(APPS))
        culture = homarr.calls_to('serverSettings.saveSettings')[-1]
        self.assertEqual(culture['value'], {'defaultLocale': 'ja'})

    def test_the_board_shows_the_reachability_status(self):
        homarr = FakeHomarr()
        configure.configure(homarr, options(APPS))
        settings = homarr.calls_to('board.savePartialBoardSettings')[-1]
        self.assertFalse(settings['disableStatus'])

    def test_a_declared_ping_url_is_used_and_defaults_to_href(self):
        homarr = FakeHomarr()
        configure.configure(homarr, options([
            {'name': 'A', 'href': 'https://a.example', 'pingUrl': 'https://a.example/healthz'},
            {'name': 'B', 'href': 'https://b.example'},
        ]))
        created = {row['name']: row for row in homarr.calls_to('app.create')}
        self.assertEqual(created['A']['pingUrl'], 'https://a.example/healthz')
        self.assertEqual(created['B']['pingUrl'], 'https://b.example')


class InputTests(unittest.TestCase):
    def test_an_absolute_url_is_required(self):
        self.assertEqual(configure.base_url('http://host:7575/'), 'http://host:7575')
        with self.assertRaises(ValueError):
            configure.base_url('host:7575')

    def test_a_relative_href_is_rejected(self):
        directory = Path(tempfile.mkdtemp(prefix='homarr-test-'))
        path = directory / 'apps.json'
        path.write_text(json.dumps([{'name': 'x', 'href': '/local'}]), encoding='utf-8')
        with self.assertRaises(ValueError):
            configure.load_apps(path)

    def test_a_nameless_entry_is_rejected(self):
        directory = Path(tempfile.mkdtemp(prefix='homarr-test-'))
        path = directory / 'apps.json'
        path.write_text(json.dumps([{'href': 'https://x.example'}]), encoding='utf-8')
        with self.assertRaises(ValueError):
            configure.load_apps(path)

    def test_item_options_arrive_as_dict_or_json_string(self):
        self.assertEqual(configure.item_app_id({'options': {'json': {'appId': 'a'}}}), 'a')
        self.assertEqual(configure.item_app_id({'options': '{"appId": "b"}'}), 'b')

    def test_the_icon_escapes_markup(self):
        uri = configure.icon_data_uri('<X>', '#000000')
        self.assertNotIn('<X>', uri)
        self.assertIn('%3C', uri)

    def test_trpc_input_is_encoded(self):
        path = configure.trpc_path('board.getBoardByName', {'name': 'home'})
        self.assertTrue(path.startswith('/api/trpc/board.getBoardByName?input='))
        self.assertIn('%22home%22', path)


class StackTests(unittest.TestCase):
    def compose(self):
        return yaml.safe_load((STACK / 'compose.yaml').read_text(encoding='utf-8'))

    def test_the_project_is_homarr_alone(self):
        compose = self.compose()
        self.assertEqual(compose['name'], 'homarr')
        self.assertEqual(list(compose['services']), ['homarr'])

    def test_the_old_hub_services_are_not_copied_in(self):
        services = set(self.compose()['services'])
        for name in ('postgresql', 'server', 'worker', 'docs'):
            self.assertNotIn(name, services, name)

    def test_the_lock_pins_the_same_repository_as_compose(self):
        lock = yaml.safe_load((STACK / 'compose.lock.yaml').read_text(encoding='utf-8'))
        image = self.compose()['services']['homarr']['image']
        default = re.search(r'\$\{[A-Z_]+:-([^}]+)\}', image)
        repository = default.group(1) if default else image.rsplit(':', 1)[0]
        self.assertTrue(lock['services']['homarr']['image'].startswith(repository + '@sha256:'))

    def test_the_secret_encryption_key_is_not_in_env_example(self):
        text = (STACK / '.env.example').read_text(encoding='utf-8')
        self.assertNotIn('SECRET_ENCRYPTION_KEY=', text)
        for key in ('BASE_URL=', 'BOARD_NAME=', 'ADMIN_GROUP=', 'APPS_FILE='):
            self.assertIn(key, text, key)

    def test_the_scripts_use_the_standard_library_only(self):
        for name in ('manage.py', 'configure.py', 'configure-integrations.py'):
            text = (STACK / name).read_text(encoding='utf-8')
            self.assertNotIn('import requests', text, name)

    def test_the_declared_apps_are_valid_and_unique(self):
        apps = configure.load_apps(STACK / 'apps.json')
        self.assertGreaterEqual(len(apps), 8)
        self.assertEqual(len(apps), len({row['name'] for row in apps}))
        self.assertEqual(len(apps), len({row['href'] for row in apps}))
        for row in apps:
            self.assertTrue(row['href'].startswith('https://'), row['href'])
            if 'pingUrl' in row:
                self.assertTrue(row['pingUrl'].startswith('https://'), row['pingUrl'])


class IntegrationTests(unittest.TestCase):
    def test_proxmox_uses_the_read_only_token_secret_kinds(self):
        secrets = integrations.proxmox_secrets({
            'PVE_USERNAME': 'monitoring', 'PVE_REALM': 'pve',
            'PVE_TOKEN_ID': 'monitoring', 'PVE_TOKEN_SECRET': 'secret'})
        self.assertEqual([secret['kind'] for secret in secrets],
                         ['username', 'realm', 'tokenId', 'apiKey'])

    def test_the_widget_options_match_the_widgets(self):
        health = integrations.widget_options('healthMonitoring')
        self.assertTrue(health['cpu'] and health['memory'])
        ups = integrations.widget_options('ups')
        self.assertTrue(ups['showBattery'])

    def test_has_widget_matches_the_kind_and_integrations(self):
        items = [{'kind': 'ups', 'integrationIds': ['a']}]
        self.assertTrue(integrations.has_widget(items, 'ups', ['a']))
        self.assertFalse(integrations.has_widget(items, 'ups', ['b']))
        self.assertFalse(integrations.has_widget(items, 'healthMonitoring', ['a']))

    def test_pack_layouts_places_widgets_then_apps(self):
        items = [
            {'kind': 'app', 'id': 'a1', 'layouts': [{'layoutId': 'l', 'sectionId': 's'}]},
            {'kind': 'healthMonitoring', 'id': 'h', 'layouts': [{'layoutId': 'l', 'sectionId': 's'}]},
            {'kind': 'ups', 'id': 'u', 'layouts': [{'layoutId': 'l', 'sectionId': 's'}]},
            {'kind': 'app', 'id': 'a2', 'layouts': [{'layoutId': 'l', 'sectionId': 's'}]},
        ]
        packed = integrations.pack_layouts(items, 8)
        by_id = {item['id']: item['layouts'][0] for item in packed}
        self.assertEqual((by_id['h']['xOffset'], by_id['h']['width'], by_id['h']['height']), (0, 8, 5))
        self.assertEqual((by_id['u']['xOffset'], by_id['u']['yOffset'], by_id['u']['width']), (0, 5, 4))
        self.assertEqual((by_id['a1']['width'], by_id['a1']['height']), (2, 2))
        self.assertEqual(by_id['a1']['xOffset'], 4)
        self.assertEqual(by_id['a2']['xOffset'], 6)
        cells = []
        for layout in by_id.values():
            cells += [(layout['xOffset'] + dx, layout['yOffset'] + dy)
                      for dx in range(layout['width']) for dy in range(layout['height'])]
        self.assertEqual(len(cells), len(set(cells)), 'layouts overlap')

    def test_creating_an_integration_grants_everyone_use(self):
        homarr = FakeHomarr()
        integration_id = integrations.ensure_integration(
            homarr, 'everyone', 'Proxmox', 'proxmox', 'https://pve.example:8006',
            integrations.proxmox_secrets({'PVE_USERNAME': 'monitoring', 'PVE_REALM': 'pve',
                                          'PVE_TOKEN_ID': 'monitoring', 'PVE_TOKEN_SECRET': 'x'}))
        self.assertEqual(len(homarr.integrations), 1)
        self.assertEqual(integration_id, homarr.integrations[0]['id'])
        permissions = homarr.calls_to('integration.saveGroupIntegrationPermissions')[-1]
        self.assertEqual(permissions['permissions'],
                         [{'principalId': 'everyone', 'permission': 'use'}])

    def test_widgets_are_added_once(self):
        homarr = FakeHomarr()
        homarr.boards.append({'id': 'board1', 'name': 'home'})
        board = homarr.trpc('board.getBoardByName', {'name': 'home'})
        self.assertTrue(integrations.ensure_widget(homarr, board, 'ups', ['i1']))
        board = homarr.trpc('board.getBoardByName', {'name': 'home'})
        self.assertFalse(integrations.ensure_widget(homarr, board, 'ups', ['i1']))
        self.assertEqual(len(homarr.items), 1)


class IacTests(unittest.TestCase):
    def test_the_playbook_deploys_homarr_behind_tls(self):
        play = yaml.safe_load((ROOT / 'platform/ansible/homarr.yml').read_text(encoding='utf-8'))
        self.assertEqual(play[0]['hosts'], 'netbox_bootstrap')
        roles = play[0]['roles']
        # tls_proxy first: configure logs in through the public name, where
        # NextAuth's cookies are Secure and only HTTPS carries them.
        self.assertLess(roles.index('tls_proxy'), roles.index('homarr'))

    def test_the_configure_step_uses_the_public_url(self):
        manage = (STACK / 'manage.py').read_text(encoding='utf-8')
        self.assertIn("values.get('BASE_URL')", manage)

    def test_the_role_reads_the_identity_client_and_manages_the_stack(self):
        defaults = yaml.safe_load(
            (ROOT / 'platform/ansible/roles/homarr/defaults/main.yml').read_text(encoding='utf-8'))
        self.assertEqual(defaults['homarr_project_dir'], '/opt/homarr-stack')
        self.assertEqual(defaults['homarr_oidc_credentials_path'],
                         '/opt/identity-stack/secrets/oidc-homarr.json')
        tasks = (ROOT / 'platform/ansible/roles/homarr/tasks/main.yml').read_text(encoding='utf-8')
        for token in ('compose.yaml', 'compose.lock.yaml', 'manage.py', 'configure.py',
                      'configure-integrations.py', 'integration_values.json', 'apps.json',
                      'oidc_client.json', 'manage.py, init', 'manage.py, lock',
                      'manage.py, up', 'manage.py, configure'):
            self.assertIn(token, tasks, token)

    def test_dns_declares_the_entry_point_on_services_01(self):
        dns = yaml.safe_load((ROOT / 'platform/terraform/dns.yaml').read_text(encoding='utf-8'))
        record = dns['records']['homarr']
        self.assertEqual(record['host'], 'services-01')
        self.assertEqual(record['upstream'], '127.0.0.1:7575')

    def test_identity_offers_the_homarr_client(self):
        spec = importlib.util.spec_from_file_location(
            'identity_configure', ROOT / 'stacks/identity/configure.py')
        identity = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(identity)
        self.assertEqual(identity.HOMARR, 'homarr')
        self.assertEqual(identity.homarr_redirect('apextox.dpdns.org'),
                         'https://homarr.apextox.dpdns.org/api/auth/callback/oidc')


if __name__ == '__main__':
    unittest.main()
