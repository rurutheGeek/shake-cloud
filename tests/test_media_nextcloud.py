"""Guard the media Nextcloud unit for media-01 (W03).

The unit shares the data disk with the other media apps and is deployed by
Ansible, so a wrong project name, a LAN-bound port, a missing digest, or a
constraint that lets the container write the shared originals would only show
up after deployment. These are source-text and YAML assertions in the same
spirit as test_media_vm.py and test_media_kavita.py. Nothing here connects to
media-01 or runs Docker.
"""
import ast
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / 'stacks/media/nextcloud'
COMPOSE = yaml.safe_load((UNIT / 'compose.yaml').read_text(encoding='utf-8'))
LOCK = yaml.safe_load((UNIT / 'compose.lock.yaml').read_text(encoding='utf-8'))
ROOT_LOCK = yaml.safe_load((ROOT / 'stacks/compose.lock.yaml').read_text(encoding='utf-8'))
PLAYBOOK = ROOT / 'platform/ansible/media-nextcloud.yml'
SHARED_IMAGES = ('cron', 'nextcloud', 'postgres', 'redis')
SPEC = importlib.util.spec_from_file_location('nextcloud_manage', UNIT / 'manage.py')
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)

EXPORT = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
BEGIN:VEVENT
DTSTAMP:20260919T095209Z
DTSTART:20230411T105000
DTEND:19700101T090000
SUMMARY:SA
TZID:Asia/Tokyo
UID:2d780652-66fc-47c9-ac59-021d2b512907@kfsoft.info
RRULE:FREQ=WEEKLY;UNTIL=20230605T145959Z;INTERVAL=1
END:VEVENT
BEGIN:VEVENT
DTSTAMP:20260919T095209Z
DTSTART;VALUE=DATE:20260101
DTEND;VALUE=DATE:20260102
SUMMARY:元日
UID:allday-1@example.com
END:VEVENT
END:VCALENDAR
"""
EMPTY_MULTISTATUS = '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"/>'
OBJECT_MULTISTATUS = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
<d:response>
<d:href>/remote.php/dav/calendars/user1/slug/2d780652-66fc-47c9-ac59-021d2b512907%40kfsoft.info.ics</d:href>
<d:propstat><d:prop><d:getetag>"x"</d:getetag></d:prop></d:propstat>
</d:response>
</d:multistatus>"""


def example_env():
    """Return the literal KEY=value pairs of .env.example."""
    values = {}
    for line in (UNIT / '.env.example').read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            values[key] = value
    return values


class ComposeTests(unittest.TestCase):
    def test_it_is_an_independent_project(self):
        self.assertEqual(COMPOSE['name'], 'media-nextcloud')

    def test_the_expected_services_are_defined(self):
        self.assertEqual(list(COMPOSE['services']),
                         ['postgres', 'redis', 'nextcloud', 'cron'])

    def test_vaultwarden_moved_to_services_01(self):
        self.assertNotIn('vaultwarden', (UNIT / 'compose.yaml').read_text(encoding='utf-8'))
        self.assertNotIn('vaultwarden', LOCK['services'])

    def test_the_port_is_loopback_only(self):
        ports = COMPOSE['services']['nextcloud']['ports']
        self.assertEqual(ports, ['${BIND_ADDRESS:-127.0.0.1}:${NEXTCLOUD_PORT:-8080}:80'])
        self.assertNotIn('0.0.0.0', ''.join(ports))

    def test_the_database_and_redis_are_not_published(self):
        for name in ('postgres', 'redis'):
            self.assertNotIn('ports', COMPOSE['services'][name], name)

    def test_the_backend_network_is_internal(self):
        self.assertTrue(COMPOSE['networks']['backend']['internal'])
        for name in ('postgres', 'redis'):
            self.assertEqual(COMPOSE['services'][name]['networks'], ['backend'], name)

    def test_state_lives_on_the_media_data_disk(self):
        volumes = COMPOSE['services']['nextcloud']['volumes']
        self.assertIn('${STORAGE_ROOT:-/srv/media-stack/storage}/nextcloud/config:/var/www/html/config',
                      volumes)
        self.assertIn('${STORAGE_ROOT:-/srv/media-stack/storage}/nextcloud/data:/var/www/data',
                      volumes)
        self.assertIn('${STORAGE_ROOT:-/srv/media-stack/storage}/postgres:/var/lib/postgresql/data',
                      COMPOSE['services']['postgres']['volumes'])

    def test_shared_libraries_are_mounted_for_nextcloud(self):
        volumes = COMPOSE['services']['nextcloud']['volumes']
        self.assertIn('${LIBRARY_ROOT:-/srv/media-stack/library}/books:/library/books', volumes)
        self.assertIn('${LIBRARY_ROOT:-/srv/media-stack/library}/music:/library/music', volumes)
        self.assertIn('${LIBRARY_ROOT:-/srv/media-stack/library}/docs:/docs', volumes)
        # setup() が登録する /inbox の実体。無いと Files ページが
        # StorageNotAvailableException を吐き続ける（2026-09-13修正）。
        self.assertIn('${LIBRARY_ROOT:-/srv/media-stack/library}/inbox:/library/inbox', volumes)

    def test_dependencies_wait_for_health(self):
        depends = COMPOSE['services']['nextcloud']['depends_on']
        self.assertEqual(depends['postgres']['condition'], 'service_healthy')
        self.assertEqual(depends['redis']['condition'], 'service_healthy')
        self.assertEqual(COMPOSE['services']['cron']['depends_on']['nextcloud']['condition'],
                         'service_healthy')

    def test_the_cron_worker_reuses_the_nextcloud_definition(self):
        cron = COMPOSE['services']['cron']
        nextcloud = COMPOSE['services']['nextcloud']
        self.assertEqual(cron['image'], nextcloud['image'])
        self.assertEqual(cron['environment'], nextcloud['environment'])
        self.assertEqual(cron['entrypoint'], '/cron.sh')

    def test_healthchecks_are_preserved(self):
        for name in ('postgres', 'redis', 'nextcloud'):
            self.assertIn('healthcheck', COMPOSE['services'][name], name)


class LockTests(unittest.TestCase):
    def test_every_service_is_pinned_to_a_digest(self):
        self.assertEqual(set(LOCK['services']), set(COMPOSE['services']))
        for name, service in LOCK['services'].items():
            self.assertRegex(service['image'], r'@sha256:[0-9a-f]{64}$', name)

    def test_shared_images_reuse_the_reviewed_digests(self):
        for name in SHARED_IMAGES:
            self.assertEqual(LOCK['services'][name], ROOT_LOCK['services'][name], name)


class EnvironmentExampleTests(unittest.TestCase):
    def test_default_paths_live_on_the_media_data_disk(self):
        values = example_env()
        self.assertEqual(values['STORAGE_ROOT'], '/srv/media-stack/storage')
        self.assertEqual(values['LIBRARY_ROOT'], '/srv/media-stack/library')

    def test_the_loopback_bind_and_timezone_are_explicit(self):
        values = example_env()
        self.assertEqual(values['BIND_ADDRESS'], '127.0.0.1')
        self.assertEqual(values['TZ'], 'Asia/Tokyo')

    def test_the_admin_and_trusted_domains_are_set(self):
        values = example_env()
        self.assertEqual(values['NEXTCLOUD_ADMIN_USER'], 'admin')
        self.assertIn('127.0.0.1', values['NEXTCLOUD_TRUSTED_DOMAINS'])

    def test_no_credential_is_shipped_in_the_example(self):
        text = (UNIT / '.env.example').read_text(encoding='utf-8')
        self.assertNotRegex(text, r'(?im)^(POSTGRES_PASSWORD|NEXTCLOUD_ADMIN_PASSWORD|TOKEN|SECRET|API_KEY)=')


class ManageTests(unittest.TestCase):
    def setUp(self):
        self.text = (UNIT / 'manage.py').read_text(encoding='utf-8')

    def test_the_required_actions_are_available(self):
        for action in ('init', 'lock', 'up', 'upgrade', 'setup', 'apps',
                       'config-notes', 'config-print', 'config-localsend',
                       'config-tags', 'import-calendar', 'status', 'down'):
            self.assertIn(f"'{action}'", self.text)

    def test_it_uses_only_the_standard_library(self):
        modules = set()
        for node in ast.walk(ast.parse(self.text)):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add((node.module or '').split('.')[0])
        self.assertLessEqual(modules, set(sys.stdlib_module_names))
        self.assertIn('subprocess', modules)

    def test_the_private_env_is_created_from_the_example(self):
        self.assertIn(".env.example", self.text)
        self.assertIn("chmod(0o600)", self.text)

    def test_directories_are_given_to_the_container_user(self):
        self.assertIn('CONTAINER_UID = 33', self.text)
        self.assertIn('CONTAINER_GID = 33', self.text)
        self.assertIn("for name in ('books', 'music', 'docs')", self.text)
        self.assertIn('os.chown(path, *owner)', self.text)
        self.assertIn('0o2750', self.text)

    def test_it_refuses_to_change_ownership_without_root(self):
        self.assertIn("os.geteuid() != 0", self.text)
        self.assertIn('PermissionError', self.text)

    def test_missing_secrets_are_generated_read_only_and_never_overwritten(self):
        self.assertIn("directory.chmod(0o700)", self.text)
        self.assertIn("with path.open('x')", self.text)
        self.assertIn('chmod(0o444)', self.text)
        self.assertIn('if not path.exists()', self.text)

    def test_lock_pins_digests_with_docker_image_inspect(self):
        self.assertIn("'docker', 'image', 'inspect'", self.text)
        self.assertIn("'RepoDigests'", self.text)

    def test_up_requires_the_lock_and_waits_for_health(self):
        self.assertIn('def lock()', self.text)
        self.assertIn('compose.lock.yaml', self.text)
        self.assertIn("'--wait'", self.text)
        commands = ast.parse(self.text)
        self.assertTrue(any(isinstance(node, ast.FunctionDef) and node.name == 'up'
                            for node in ast.walk(commands)))

    def test_occ_runs_inside_the_nextcloud_service_as_the_web_user(self):
        self.assertIn('def occ(', self.text)
        self.assertIn("'exec', '-T', '--user', '33:33', 'nextcloud', 'php', 'occ'",
                      self.text)

    def test_setup_enables_files_external_and_background_cron(self):
        self.assertIn("occ('app:enable', 'files_external')", self.text)
        self.assertIn("occ('background:cron')", self.text)

    def test_external_storage_paths_match_the_compose_mounts(self):
        for name, datadir in (('books', '/library/books'),
                              ('music', '/library/music'),
                              ('docs', '/docs'),
                              ('inbox', '/library/inbox')):
            self.assertIn(f"('{name}', '{datadir}')", self.text, name)
        self.assertIn("occ('files_external:create', '/' + name, 'local', 'null::null'",
                      self.text)

    def test_the_library_is_open_to_every_user(self):
        # 適用先を指定しない = ログインできる全員（招待したAuthentikユーザーを含む）。
        self.assertNotIn("'--applicable-user'", self.text)
        self.assertIn('--remove-user=', self.text)
        self.assertIn('--remove-group=', self.text)
        self.assertIn('external storage available to every user', self.text)
        self.assertIn('external storage opened to every user', self.text)

    def test_existing_mounts_are_preserved_and_conflicts_are_rejected(self):
        self.assertIn('files_external:list', self.text)
        self.assertIn("matching[0]['configuration'].get('datadir') != datadir", self.text)
        self.assertIn('Conflicting external storage mount', self.text)
        self.assertIn('RuntimeError', self.text)

    def test_apps_install_enable_or_keep_apps(self):
        self.assertIn("occ('app:install', name)", self.text)
        self.assertIn("occ('app:enable', name)", self.text)
        self.assertIn('CHANGED: Nextcloud app installed', self.text)
        self.assertIn('CHANGED: Nextcloud app enabled', self.text)
        self.assertIn('OK: Nextcloud app already enabled', self.text)

    def test_apps_require_the_comma_separated_option(self):
        self.assertIn("parser.add_argument('--apps'", self.text)
        self.assertIn('Use --apps app1,app2 with the apps action', self.text)

    def test_notes_default_to_the_plain_markdown_editor(self):
        self.assertIn("config_app('notes', (('noteMode', 'edit'),))", self.text)

    def test_setup_and_apps_do_not_handle_credentials(self):
        functions = {node.name: ast.get_source_segment(self.text, node)
                     for node in ast.walk(ast.parse(self.text))
                     if isinstance(node, ast.FunctionDef)}
        for name in ('occ', 'setup', 'apps'):
            self.assertNotRegex(functions[name], r'(?i)password|token|secret')


class CalendarImportTests(unittest.TestCase):
    def test_normalize_fixes_timezone_and_broken_end(self):
        events = dict(manage.normalize_ics(EXPORT))
        ics = events['2d780652-66fc-47c9-ac59-021d2b512907@kfsoft.info']
        self.assertIn('DTSTART;TZID=Asia/Tokyo:20230411T105000', ics)
        self.assertIn('DTEND;TZID=Asia/Tokyo:20230411T115000', ics)
        self.assertNotIn('TZID:Asia/Tokyo', ics)
        self.assertNotIn('19700101T090000', ics)
        self.assertIn('BEGIN:VEVENT', ics)
        self.assertIn('END:VEVENT', ics)
        self.assertIn('UID:2d780652-66fc-47c9-ac59-021d2b512907@kfsoft.info', ics)

    def test_normalize_keeps_all_day_events(self):
        events = dict(manage.normalize_ics(EXPORT))
        ics = events['allday-1@example.com']
        self.assertIn('DTSTART;VALUE=DATE:20260101', ics)
        self.assertIn('DTEND;VALUE=DATE:20260102', ics)
        self.assertNotIn('TZID=', ics)

    def test_share_values(self):
        self.assertEqual(manage.parse_share('abc'), ('abc', False))
        self.assertEqual(manage.parse_share('abc:read'), ('abc', True))
        self.assertEqual(manage.parse_share('abc:read-write'), ('abc', False))
        with self.assertRaises(ValueError):
            manage.parse_share('abc:owner')

    def test_import_creates_calendar_puts_missing_events_and_shares(self):
        calls = []

        def dav(config, user, token, method, path, body=None, headers=None, **kwargs):
            calls.append((method, path, body))
            if method == 'PROPFIND' and path.endswith('user1/'):
                return 207, EMPTY_MULTISTATUS
            if method == 'PROPFIND':
                return 207, OBJECT_MULTISTATUS
            return 201, ''

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sample.ics'
            path.write_text(EXPORT, encoding='utf-8')
            with patch.object(manage, 'settings', return_value={}), \
                 patch.object(manage, 'create_app_password', return_value=('token', '7')), \
                 patch.object(manage, 'dav_request', side_effect=dav), \
                 patch.object(manage, 'occ') as occ:
                manage.import_calendar('user1', str(path), 'テスト', [('user2', False)], 60)

        puts = [call for call in calls if call[0] == 'PUT']
        self.assertEqual(len(puts), 1)
        self.assertTrue(puts[0][1].endswith('allday-1%40example.com.ics'))
        self.assertIn('BEGIN:VEVENT', puts[0][2])
        self.assertIn('END:VEVENT', puts[0][2])
        shares = [call for call in calls if call[0] == 'POST']
        self.assertEqual(len(shares), 1)
        self.assertIn('<oc:share', shares[0][2])
        self.assertIn('<oc:read-write/>', shares[0][2])
        self.assertEqual(occ.call_args_list[-1].args[:2],
                         ('user:auth-tokens:delete', 'user1'))


class AnsibleTests(unittest.TestCase):
    def setUp(self):
        self.play = yaml.safe_load(PLAYBOOK.read_text(encoding='utf-8'))[0]

    def test_it_targets_the_media_group_as_root(self):
        self.assertEqual(self.play['hosts'], 'media')
        self.assertTrue(self.play['become'])

    def test_it_deploys_the_unit_under_the_project_directory(self):
        copies = [task['ansible.builtin.copy'] for task in self.play['tasks']
                  if 'ansible.builtin.copy' in task]
        self.assertTrue(any(copy['dest'].startswith('{{ project_dir }}/media/nextcloud/')
                            for copy in copies))

    def test_it_generates_a_private_env_from_group_vars(self):
        copies = [task['ansible.builtin.copy'] for task in self.play['tasks']
                  if 'ansible.builtin.copy' in task]
        env = [copy for copy in copies if copy['dest'].endswith('/.env')]
        self.assertEqual(len(env), 1)
        self.assertEqual(env[0]['mode'], '0600')
        self.assertIn('{{ storage_root }}', env[0]['content'])
        self.assertIn('{{ library_root }}', env[0]['content'])

    def test_it_prepares_and_starts_the_unit_with_manage_py(self):
        commands = [task['ansible.builtin.command']['argv'] for task in self.play['tasks']
                    if 'ansible.builtin.command' in task]
        self.assertTrue(any(argv[-1] == 'init' and argv[-2].endswith('manage.py')
                            for argv in commands))
        self.assertTrue(any(argv[-1] == 'up' and argv[-2].endswith('manage.py')
                            for argv in commands))

    def test_it_runs_setup_and_apps_after_starting_the_unit(self):
        commands = [task['ansible.builtin.command']['argv'] for task in self.play['tasks']
                    if 'ansible.builtin.command' in task]
        actions = {argv[-1]: index for index, argv in enumerate(commands)
                   if len(argv) > 1 and argv[-2].endswith('manage.py')}
        self.assertIn('up', actions)
        self.assertIn('upgrade', actions)
        self.assertIn('setup', actions)
        self.assertGreater(actions['upgrade'], actions['up'])
        self.assertGreater(actions['setup'], actions['upgrade'])
        apps = [argv for argv in commands if '--apps' in argv]
        self.assertEqual(len(apps), 1)
        self.assertGreater(commands.index(apps[0]), actions['up'])

    def test_apps_use_the_group_var_and_always_add_the_custom_apps(self):
        text = PLAYBOOK.read_text(encoding='utf-8')
        self.assertIn(
            "nextcloud_apps | default([]) + ['shake_print', 'shake_localsend', 'shake_tags']",
            text)

    def test_notes_default_is_set_through_manage_py_after_apps(self):
        commands = [task['ansible.builtin.command']['argv'] for task in self.play['tasks']
                    if 'ansible.builtin.command' in task]
        notes = [argv for argv in commands if argv[-1] == 'config-notes']
        self.assertEqual(len(notes), 1)
        self.assertTrue(notes[0][-2].endswith('manage.py'))
        apps = [argv for argv in commands if '--apps' in argv]
        self.assertGreater(commands.index(notes[0]), commands.index(apps[0]))
        text = PLAYBOOK.read_text(encoding='utf-8')
        self.assertIn("'CHANGED:' in nextcloud_notes_config.stdout", text)

    def test_change_detection_uses_the_manage_py_status_lines(self):
        text = PLAYBOOK.read_text(encoding='utf-8')
        self.assertIn("'CHANGED:' in nextcloud_setup.stdout", text)
        self.assertIn("'CHANGED:' in nextcloud_apps_result.stdout", text)


class SecretTests(unittest.TestCase):
    def test_the_private_env_and_secret_directory_are_not_in_the_unit(self):
        self.assertFalse((UNIT / '.env').exists())
        self.assertFalse((UNIT / 'secrets').exists())
        self.assertTrue((UNIT / '.env.example').exists())

    def test_git_ignores_the_private_env_and_secrets(self):
        patterns = (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines()
        self.assertIn('.env', patterns)
        self.assertIn('secrets/', patterns)

    def test_no_credential_is_committed_in_the_unit(self):
        for name in ('compose.yaml', 'compose.lock.yaml', '.env.example', 'manage.py'):
            text = (UNIT / name).read_text(encoding='utf-8')
            self.assertNotIn('PRIVATE KEY', text, name)
            self.assertNotIn('AKIA', text, name)
            self.assertNotRegex(text, r'(?im)^(POSTGRES_PASSWORD|NEXTCLOUD_ADMIN_PASSWORD|TOKEN|SECRET|API_KEY)=', name)

    def test_the_playbook_never_carries_credentials(self):
        text = PLAYBOOK.read_text(encoding='utf-8')
        self.assertNotIn('PASSWORD', text)
        self.assertNotIn('PRIVATE KEY', text)
        # トークンは SOPS から register で受け取るだけで、値は書かない。
        self.assertNotRegex(text, r'(?im)^\s*(TOKEN|SECRET|API_KEY):\s*\S')
        self.assertIn('print-api.sops.yaml', text)

    def test_the_readme_links_the_work_item_and_the_source(self):
        readme = (UNIT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('../../../docs/development/W03-nextcloud.md', readme)
        self.assertIn('stacks/compose.lock.yaml', readme)


if __name__ == '__main__':
    unittest.main()
