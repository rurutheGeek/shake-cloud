"""Guard the UrBackup unit for media-01 (W08).

The web UI must stay on the loopback behind Caddy, while the client port and
the discovery broadcast are the only things the LAN may reach; the backup data
must live on the bulk HDD and the server state on the data disk. These are
source-text and YAML assertions in the same spirit as test_media_navidrome.py.
Nothing here connects to media-01 or runs Docker.
"""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

import yaml

from support import read, syntax_check

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / 'stacks/media/urbackup'
COMPOSE = yaml.safe_load((UNIT / 'compose.yaml').read_text(encoding='utf-8'))
LOCK = yaml.safe_load((UNIT / 'compose.lock.yaml').read_text(encoding='utf-8'))
SETTINGS = json.loads((UNIT / 'settings.json').read_text(encoding='utf-8'))
PLAYBOOK = ROOT / 'platform/ansible/media-urbackup.yml'
VERIFY = ROOT / 'platform/ansible/media-verify.yml'


class ComposeTests(unittest.TestCase):
    def test_it_is_an_independent_project(self):
        self.assertEqual(COMPOSE['name'], 'media-urbackup')

    def test_the_stack_runs_urbackup_and_the_portal(self):
        self.assertEqual(list(COMPOSE['services']), ['urbackup', 'portal'])

    def test_the_web_ui_is_loopback_only(self):
        ports = COMPOSE['services']['urbackup']['ports']
        self.assertIn('127.0.0.1:${URBACKUP_WEB_PORT:-55414}:55414', ports)

    def test_the_portal_is_loopback_only_and_read_only(self):
        service = COMPOSE['services']['portal']
        self.assertEqual(service['ports'], ['127.0.0.1:${PORTAL_PORT:-55416}:8080'])
        self.assertTrue(service['read_only'])
        self.assertEqual(service['cap_drop'], ['ALL'])
        self.assertIn('./portal.py:/app/portal.py:ro', service['volumes'])
        self.assertIn('./portal-backup.js:/app/portal-backup.js:ro', service['volumes'])
        # 管理パスワードは urbackup スタックの secrets を読み取り専用で借りる。
        self.assertIn('./secrets/urbackup_admin_password:/run/secrets/urbackup_admin_password:ro',
                      service['volumes'])
        self.assertEqual(service['environment']['URBACKUP_API'], 'http://urbackup:55414/x')
        # Android のアップロード先は HDD の client-backups/android（書き込み可）。
        self.assertIn('${CLIENT_BACKUP_ROOT:-/srv/media-stack/client-backups}/android:/data/android-backups',
                      service['volumes'])
        self.assertEqual(service['environment']['ANDROID_BACKUP_ROOT'], '/data/android-backups')

    def test_the_client_and_discovery_ports_are_the_only_lan_entries(self):
        ports = COMPOSE['services']['urbackup']['ports']
        self.assertIn('${BIND_ADDRESS}:${URBACKUP_CLIENT_PORT:-55413}:55413', ports)
        self.assertIn('${URBACKUP_BROADCAST_PORT:-35623}:35623/udp', ports)
        # 55415（インターネットモード）は使わない。internet_mode_enabled=false。
        self.assertNotIn('55415', ''.join(ports))

    def test_the_container_user_matches_the_export_uid(self):
        environment = COMPOSE['services']['urbackup']['environment']
        self.assertEqual(environment['PUID'], '${URBACKUP_UID:-101}')
        self.assertEqual(environment['PGID'], '${URBACKUP_GID:-101}')

    def test_state_and_backup_data_live_on_their_own_disks(self):
        volumes = COMPOSE['services']['urbackup']['volumes']
        self.assertIn('${STORAGE_ROOT:-/srv/media-stack/storage}/urbackup:/var/urbackup',
                      volumes)
        self.assertIn('${CLIENT_BACKUP_ROOT:-/srv/media-stack/client-backups}/urbackup:/backups',
                      volumes)

    def test_the_healthcheck_avoids_tools_missing_from_the_image(self):
        healthcheck = COMPOSE['services']['urbackup']['healthcheck']
        self.assertEqual(healthcheck['test'],
                         ['CMD', 'bash', '-c', 'exec 3<>/dev/tcp/127.0.0.1/55414'])


class LockTests(unittest.TestCase):
    def test_every_service_is_pinned_to_a_digest(self):
        self.assertEqual(set(LOCK['services']), set(COMPOSE['services']))
        for name, service in LOCK['services'].items():
            self.assertRegex(service['image'], r'@sha256:[0-9a-f]{64}$', name)

    def test_the_lock_keeps_the_compose_name(self):
        self.assertEqual(LOCK['services']['urbackup']['image'].split('@')[0],
                         'uroni/urbackup-server')

    def test_the_portal_reuses_the_reviewed_python_digest(self):
        mail_view = yaml.safe_load(
            (ROOT / 'stacks/mail-view/compose.lock.yaml').read_text(encoding='utf-8'))
        self.assertEqual(LOCK['services']['portal']['image'],
                         mail_view['services']['mail-view']['image'])


class SettingsTests(unittest.TestCase):
    def test_the_server_url_is_the_https_entry(self):
        self.assertEqual(SETTINGS['server_url'], 'https://backup.apextox.dpdns.org/')

    def test_file_backups_default_to_the_user_profiles(self):
        self.assertEqual(SETTINGS['default_dirs'], 'C:\\Users|Users')

    def test_image_backups_cover_the_system_drive(self):
        self.assertEqual(SETTINGS['image_letters'], 'C')

    def test_internet_mode_is_off_so_clients_use_the_lan_port(self):
        self.assertIs(SETTINGS['internet_mode_enabled'], False)


def load_manage():
    spec = importlib.util.spec_from_file_location('urbackup_manage', UNIT / 'manage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ManageTests(unittest.TestCase):
    def setUp(self):
        self.text = (UNIT / 'manage.py').read_text(encoding='utf-8')

    def test_the_required_actions_are_available(self):
        self.assertIn(
            "choices=['init', 'lock', 'up', 'configure',\n"
            "                                           'status', 'down', 'backup']",
            self.text)

    def test_it_uses_only_the_standard_library(self):
        import ast
        modules = set()
        for node in ast.walk(ast.parse(self.text)):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add((node.module or '').split('.')[0])
        self.assertLessEqual(modules, set(sys.stdlib_module_names))
        self.assertIn('urllib', modules)
        self.assertIn('secrets', modules)

    def test_the_private_env_is_created_from_the_example(self):
        self.assertIn('.env.example', self.text)
        self.assertIn('chmod(0o600)', self.text)

    def test_directories_follow_the_container_user(self):
        self.assertIn("config.get('URBACKUP_UID', 101)", self.text)
        self.assertIn("config.get('URBACKUP_GID', 101)", self.text)
        self.assertIn('os.chown(path, uid, gid)', self.text)

    def test_init_creates_the_android_upload_directory(self):
        # NFS 上で Docker に chown させないよう、init が先に作る。
        self.assertIn(") / 'android'", self.text)

    def test_the_admin_password_is_generated_into_secrets(self):
        self.assertIn("'secrets'", self.text)
        self.assertIn('urbackup_admin_password', self.text)
        self.assertIn('secrets.token_urlsafe', self.text)
        self.assertIn('chmod(0o400)', self.text)

    def test_configure_resets_the_password_only_when_login_fails(self):
        section = self.text.split('def configure', 1)[1].split('def backup', 1)[0]
        self.assertIn('wait_for_api(api)', section)
        self.assertIn('if not wait_for_login(api):', section)
        self.assertIn("'reset-admin-pw'", section)
        self.assertIn("'-p', password", section)
        # リセットはDBへ書いてから見えるまで少し遅れる。1回で諦めない。
        self.assertIn('def wait_for_login', self.text)
        self.assertIn('time.sleep(3)', self.text)

    def test_configure_applies_settings_json_idempotently(self):
        self.assertIn("'settings.json'", self.text)
        self.assertIn("'sa': 'general_save'", self.text)
        self.assertIn('current.get(key) != value', self.text)

    def test_general_settings_tolerates_plain_values(self):
        # UrBackup は {'value': ...} のものと素の文字列・真偽値を混ぜて返す。
        module = load_manage()

        class FakeApi:
            def call(self, action, params=None, method='POST'):
                return {'settings': {'server_url': {'value': ''}, 'autoshutdown': False}}

        self.assertEqual(module.general_settings(FakeApi()),
                         {'server_url': '', 'autoshutdown': False})

    def test_the_login_follows_the_server_handshake(self):
        section = self.text.split('def login', 1)[1].split('def general_settings', 1)[0]
        self.assertIn("'salt'", section)
        self.assertIn('pbkdf2_rounds', section)
        self.assertIn('pbkdf2_hmac', section)
        self.assertIn("'sha256'", section)

    def test_the_api_base_keeps_the_x_path_without_a_trailing_slash(self):
        # /x/ だと "Unknown action []" になる（2026-10-02 実測）。
        self.assertIn("self.base = base.rstrip('/')", self.text)
        self.assertNotIn("rstrip('/') + '/'", self.text)

    def test_backup_is_cold_and_excludes_the_device_data(self):
        section = self.text.split('def backup', 1)[1].split('def main', 1)[0]
        self.assertIn('os.geteuid() != 0', section)
        self.assertIn('PermissionError', section)
        self.assertIn("compose('stop'", section)
        self.assertIn('.incomplete', section)
        self.assertIn("target.rename(complete)", section)
        self.assertIn("'-C', str(storage), '.'", section)
        # 端末のバックアップ本体は HDD 側。状態の tar に含めない。
        self.assertNotIn('/srv/media-stack/client-backups', section)


class PlaybookTests(unittest.TestCase):
    def setUp(self):
        self.play = yaml.safe_load(read(PLAYBOOK))[0]
        self.text = read(PLAYBOOK)

    def test_it_targets_the_media_host_as_root(self):
        self.assertEqual(self.play['hosts'], 'media')
        self.assertTrue(self.play['become'])

    def test_it_copies_the_settings_and_the_lock(self):
        copies = [task['loop'] for task in self.play['tasks']
                  if 'ansible.builtin.copy' in task and 'loop' in task]
        self.assertEqual(copies,
                         [['compose.yaml', 'compose.lock.yaml', 'manage.py',
                           'portal.py', 'portal-backup.js', '.env.example',
                           'settings.json']])

    def test_the_env_binds_the_client_port_to_the_ansible_host(self):
        content = [task['ansible.builtin.copy']['content'] for task in self.play['tasks']
                   if 'ansible.builtin.copy' in task
                   and 'content' in task['ansible.builtin.copy']][0]
        self.assertIn('BIND_ADDRESS={{ ansible_host }}', content)
        self.assertIn('CLIENT_BACKUP_ROOT={{ client_backup_root }}', content)
        self.assertIn('STORAGE_ROOT={{ storage_root }}', content)

    def test_it_runs_init_up_and_configure(self):
        commands = [task['ansible.builtin.command']['argv']
                    for task in self.play['tasks'] if 'ansible.builtin.command' in task]
        manage = [argv for argv in commands if argv[0] == 'python3']
        self.assertEqual([argv[-1] for argv in manage], ['init', 'up', 'configure'])
        for argv in manage:
            self.assertTrue(argv[1].startswith('{{ project_dir }}/media/urbackup/'))
        # 単一ファイルのバインドマウントは置き換えても古い inode を見続けるため、
        # 内容が変わったときだけ portal を作り直す。
        recreate = [argv for argv in commands if argv[0] == 'docker']
        self.assertEqual(len(recreate), 1)
        self.assertIn('--force-recreate', recreate[0])
        self.assertEqual(recreate[0][-1], 'portal')
        task = [task for task in self.play['tasks']
                if 'ansible.builtin.command' in task
                and task['ansible.builtin.command']['argv'][0] == 'docker'][0]
        self.assertEqual(task['when'], 'urbackup_definitions is changed')

    def test_the_verifier_checks_the_web_ui_on_loopback(self):
        play = yaml.safe_load(read(VERIFY))[0]
        uris = [task['ansible.builtin.uri']['url'] for task in play['tasks']
                if 'ansible.builtin.uri' in task]
        self.assertTrue(any('urbackup_web_port' in url for url in uris))
        self.assertTrue(any('urbackup_portal_port' in url for url in uris))
        self.assertTrue(all(url.startswith('http://127.0.0.1:') for url in uris))
        self.assertIn('urbackup', play['vars']['media_units'])
        self.assertEqual(play['vars']['media_unit_services']['urbackup'],
                         ['urbackup', 'portal'])
        self.assertEqual(play['vars']['media_unit_healthy']['urbackup'], 2)

    def test_the_playbook_parses(self):
        result = syntax_check(PLAYBOOK)
        self.assertEqual(result.returncode, 0,
                         f'{PLAYBOOK.name} did not parse:\n{result.stdout}\n{result.stderr}')


def load_portal():
    spec = importlib.util.spec_from_file_location('urbackup_portal', UNIT / 'portal.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.portal = load_portal()

    def test_the_page_lists_the_devices(self):
        page = self.portal.render_page(None)
        self.assertIn('バックアップポータル', page)
        self.assertIn('Windows PC', page)
        self.assertIn('Galaxy', page)
        self.assertIn('Smart Switch', page)
        self.assertNotIn('Pixel', page)

    def test_the_status_table_uses_the_urbackup_fields(self):
        status = {'status': [{'name': 'desktop', 'online': True,
                              'lastbackup': '2026-10-02 03:00',
                              'lastbackup_image': '-'}]}
        table = self.portal.render_status(status)
        self.assertIn('desktop', table)
        self.assertIn('オンライン', table)
        self.assertIn('2026-10-02 03:00', table)
        self.assertIn('未取得', table)

    def test_an_unreachable_server_is_shown_instead_of_an_error(self):
        self.assertIn('UrBackup に接続できません', self.portal.render_status(None))
        self.assertIn('UrBackup に接続できません', self.portal.render_page(None))

    def test_client_names_are_escaped(self):
        status = {'status': [{'name': '<script>alert(1)</script>', 'online': False}]}
        self.assertNotIn('<script>', self.portal.render_status(status))

    def test_it_reads_the_password_only_for_the_api_login(self):
        text = (UNIT / 'portal.py').read_text(encoding='utf-8')
        self.assertIn('/run/secrets/urbackup_admin_password', text)
        self.assertNotIn('render_page(api', text)

    def test_the_page_has_the_webusb_backup_button(self):
        page = self.portal.render_page(None)
        self.assertIn('id="android-connect"', page)
        self.assertIn('class="android-target"', page)
        self.assertIn('/static/portal-backup.js', page)
        self.assertIn('USBデバッグ', page)
        self.assertIn('Vivaldi', page)

    def test_the_bundle_is_committed_next_to_the_portal(self):
        bundle = UNIT / 'portal-backup.js'
        self.assertTrue(bundle.is_file(), 'run npm run build in portal-web/')
        text = bundle.read_text(encoding='utf-8')
        self.assertIn('shake-lab-backup', text)

    def test_safe_rel_rejects_traversal_and_absolute_paths(self):
        self.assertEqual(self.portal.safe_rel('DCIM/Camera/a.jpg'), ['DCIM', 'Camera', 'a.jpg'])
        for bad in ('/etc/passwd', '../x', 'a/../../b', 'a\\b', '', 'a//b'):
            with self.assertRaises(ValueError, msg=bad):
                self.portal.safe_rel(bad)

    def test_safe_device_rejects_odd_names(self):
        self.assertEqual(self.portal.safe_device('Galaxy_S23-abc'), 'Galaxy_S23-abc')
        for bad in ('', '../x', 'a b', 'a/b', 'x' * 65):
            with self.assertRaises(ValueError, msg=bad):
                self.portal.safe_device(bad)

    def test_the_android_upload_roundtrip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            self.portal.ANDROID_BACKUP_ROOT = Path(temporary)
            try:
                self.assertEqual(self.portal.android_index('phone'), {})
                self.assertEqual(
                    self.portal.android_chunk('phone', 'DCIM/a.jpg', 0, b'hello '), 6)
                self.assertEqual(
                    self.portal.android_chunk('phone', 'DCIM/a.jpg', 6, b'world'), 11)
                with self.assertRaises(ValueError):
                    self.portal.android_chunk('phone', 'DCIM/a.jpg', 3, b'x')
                self.portal.android_finish('phone', 'DCIM/a.jpg', 11, 1234)
                manifest = self.portal.android_manifest(
                    'phone', {'model': 'Galaxy', 'files': 1, 'bytes': 11})
                self.assertEqual(manifest['model'], 'Galaxy')
                self.assertEqual(self.portal.android_index('phone'),
                                 {'DCIM/a.jpg': {'size': 11, 'mtime': 1234}})
                self.assertEqual(
                    (Path(temporary) / 'phone' / 'files' / 'DCIM' / 'a.jpg').read_bytes(),
                    b'hello world')
                self.assertIn('Galaxy', self.portal.render_android_status())
            finally:
                self.portal.ANDROID_BACKUP_ROOT = Path('/data/android-backups')


class DnsTests(unittest.TestCase):
    def setUp(self):
        dns = yaml.safe_load(
            (ROOT / 'platform/terraform/dns.yaml').read_text(encoding='utf-8'))
        self.records = dns['records']

    def test_the_portal_and_the_ui_have_their_own_names(self):
        self.assertEqual(self.records['backup']['upstream'], '127.0.0.1:55416')
        self.assertEqual(self.records['urbackup']['upstream'], '127.0.0.1:55414')
        for name in ('backup', 'urbackup'):
            self.assertEqual(self.records[name]['host'], 'media-01')
            self.assertTrue(self.records[name]['auth'], name)


if __name__ == '__main__':
    unittest.main()
