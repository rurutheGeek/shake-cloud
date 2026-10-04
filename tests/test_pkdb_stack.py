"""Guard the pkdb PostgreSQL stack: version, exposure, secrets and restore safety.

The server was moved from another architecture by logical dump. The major
version must stay the one the dump was taken with, the superuser password must
never be regenerated or overwritten by the old server's, and a restore must not
touch a database that already holds data.
"""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/pkdb'
ROLE = ROOT / 'platform/ansible/roles/pkdb'
SPEC = importlib.util.spec_from_file_location('pkdb_manage', STACK / 'manage.py')
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)

GLOBALS = """\
CREATE ROLE pkdb_editor;
ALTER ROLE pkdb_editor WITH NOSUPERUSER LOGIN PASSWORD 'SCRAM-SHA-256$4096:editor';
CREATE ROLE pkdb_reader;
ALTER ROLE pkdb_reader WITH NOSUPERUSER LOGIN PASSWORD 'SCRAM-SHA-256$4096:reader';
CREATE ROLE postgres;
ALTER ROLE postgres WITH SUPERUSER LOGIN PASSWORD 'SCRAM-SHA-256$4096:old';
GRANT pkdb_reader TO pkdb_editor GRANTED BY postgres;
"""


class StackTests(unittest.TestCase):
    def compose(self):
        return yaml.safe_load((STACK / 'compose.yaml').read_text(encoding='utf-8'))

    def service(self):
        return self.compose()['services']['db']

    def test_the_project_is_postgresql_and_its_admin_ui(self):
        compose = self.compose()
        self.assertEqual(compose['name'], 'pkdb')
        self.assertEqual(list(compose['services']), ['db', 'adminer'])

    def test_the_admin_ui_is_loopback_only_and_pinned(self):
        adminer = self.compose()['services']['adminer']
        self.assertEqual(adminer['ports'], ['127.0.0.1:${PKDB_ADMINER_PORT:-8330}:8080'])
        self.assertRegex(adminer['image'], r'^adminer:\d+\.\d+\.\d+$')
        lock = json.loads((STACK / 'compose.lock.yaml').read_text(encoding='utf-8'))
        self.assertRegex(lock['services']['adminer']['image'], r'^adminer@sha256:[0-9a-f]{64}$')
        record = yaml.safe_load((ROOT / 'platform/terraform/dns.yaml').read_text(encoding='utf-8'))['records']['adminer']
        self.assertTrue(record['auth'])

    def test_the_major_version_and_libc_match_the_source(self):
        self.assertRegex(self.service()['image'], r'^postgres:15\.\d+-alpine$')

    def test_the_lock_pins_the_same_repository_as_compose(self):
        lock = json.loads((STACK / 'compose.lock.yaml').read_text(encoding='utf-8'))
        self.assertRegex(lock['services']['db']['image'], r'^postgres@sha256:[0-9a-f]{64}$')

    def test_the_port_is_loopback_unless_the_deployment_widens_it(self):
        self.assertEqual(self.service()['ports'],
                         ['${PKDB_BIND_ADDRESS:-127.0.0.1}:${PKDB_PORT:-5432}:5432'])

    def test_the_state_lives_outside_the_deployment_directory(self):
        self.assertEqual(self.service()['volumes'],
                         ['${STORAGE_ROOT:-/srv/pkdb}/data:/var/lib/postgresql/data'])

    def test_the_superuser_password_is_a_file_secret(self):
        environment = self.service()['environment']
        self.assertEqual(environment['POSTGRES_PASSWORD_FILE'], '/run/secrets/postgres_password')
        self.assertNotIn('POSTGRES_PASSWORD', environment)
        self.assertNotIn('POSTGRES_HOST_AUTH_METHOD', environment)
        self.assertEqual(self.compose()['secrets']['postgres_password']['file'],
                         './secrets/postgres_password')

    def test_the_healthcheck_ignores_the_socket_only_bootstrap_server(self):
        self.assertEqual(self.service()['healthcheck']['test'],
                         ['CMD', 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres'])

    def test_the_env_example_carries_no_secret(self):
        text = (STACK / '.env.example').read_text(encoding='utf-8')
        self.assertNotIn('PASSWORD', text)
        for key in ('STORAGE_ROOT=', 'PKDB_BIND_ADDRESS=127.0.0.1', 'PKDB_PORT='):
            self.assertIn(key, text, key)

    def test_the_secrets_and_backups_stay_out_of_git(self):
        for name in ('secrets/postgres_password', 'backups/20261003T000000Z/globals.sql'):
            result = subprocess.run(['git', 'check-ignore', '-q', str(STACK / name)], cwd=ROOT)
            self.assertEqual(result.returncode, 0, name)


class DeploymentTests(unittest.TestCase):
    def test_the_playbook_targets_apps_and_builds_the_entry_first(self):
        play = yaml.safe_load((ROOT / 'platform/ansible/pkdb.yml').read_text(encoding='utf-8'))[0]
        self.assertEqual(play['hosts'], 'apps')
        self.assertEqual(play['roles'], ['docker', 'tls_proxy', 'pkdb'])

    def test_the_role_uses_isolated_paths_and_the_declared_port(self):
        defaults = yaml.safe_load((ROLE / 'defaults/main.yml').read_text(encoding='utf-8'))
        self.assertEqual(defaults['pkdb_project_dir'], '/opt/pkdb')
        self.assertEqual(defaults['pkdb_storage_root'], '/srv/pkdb')
        self.assertEqual(defaults['pkdb_port'], 5432)
        env = (ROLE / 'templates/env.j2').read_text(encoding='utf-8')
        self.assertNotIn('PASSWORD', env)

    def test_the_security_group_opens_the_port_to_the_lan_only(self):
        text = (ROOT / 'platform/terraform/services/apps/main.tf').read_text(encoding='utf-8')
        rule = text.split('resource "shakecloud_security_group_rule" "pkdb"')[1].split('}')[0]
        self.assertIn('from_port   = 5432', rule)
        self.assertIn('to_port     = 5432', rule)
        self.assertIn('cidr        = local.lan_cidr', rule)

    def test_the_name_resolves_to_the_host_not_the_http_entry(self):
        dns = yaml.safe_load((ROOT / 'platform/terraform/dns.yaml').read_text(encoding='utf-8'))
        record = dns['records']['pkdb']
        self.assertEqual(record['host'], 'apps-01')
        self.assertNotIn('upstream', record)

    def test_the_rename_script_is_applied_on_every_deploy_and_only_renames(self):
        defaults = yaml.safe_load((ROLE / 'defaults/main.yml').read_text(encoding='utf-8'))
        self.assertEqual(defaults['pkdb_sql'], [
            {'database': 'sleepy_pkdb', 'file': 'lowercase.sql'},
            {'database': 'sleepy_pkdb', 'file': 'data_fixes.sql'},
            {'database': 'postgres', 'file': 'ubsleepy.sql'},
            {'database': 'ubsleepy', 'file': 'ubsleepy_tables.sql'},
            {'database': 'ubsleepy_test', 'file': 'ubsleepy_tables.sql'},
        ])
        text = (STACK / 'sql/lowercase.sql').read_text(encoding='utf-8')
        for forbidden in ('DROP ', 'DELETE ', 'TRUNCATE ', 'UPDATE '):
            self.assertNotIn(forbidden, text, forbidden)
        self.assertIn('RENAME COLUMN', text)
        self.assertIn('SET search_path = pokemondb, public', text)

    def test_the_ubsleepy_script_creates_only_and_never_touches_passwords(self):
        text = (STACK / 'sql/ubsleepy.sql').read_text(encoding='utf-8')
        self.assertIn(manage.NO_TRANSACTION_MARKER, text)
        self.assertIn('CREATE ROLE ubsleepy_writer', text)
        self.assertIn('CREATE ROLE ubsleepy_reader', text)
        self.assertIn('CREATE DATABASE', text)
        self.assertIn('\\gexec', text)
        self.assertNotIn('ALTER ROLE', text)
        self.assertNotIn('PASSWORD', text)
        for forbidden in ('DROP ', 'DELETE ', 'TRUNCATE ', 'UPDATE '):
            self.assertNotIn(forbidden, text, forbidden)

    def test_the_data_fixes_only_add_or_correct_and_refresh_the_views(self):
        text = (STACK / 'sql/data_fixes.sql').read_text(encoding='utf-8')
        for forbidden in ('DROP ', 'DELETE ', 'TRUNCATE '):
            self.assertNotIn(forbidden, text, forbidden)
        self.assertIn('ON CONFLICT DO NOTHING', text)
        self.assertIn('IS DISTINCT FROM', text)
        self.assertIn('REFRESH MATERIALIZED VIEW mv_latest_pokemon_status', text)

    def test_the_test_deployment_has_its_own_save_database(self):
        text = (STACK / 'sql/ubsleepy.sql').read_text(encoding='utf-8')
        self.assertIn("CREATE DATABASE ubsleepy_test OWNER ubsleepy_writer", text)
        self.assertNotIn('PASSWORD', text.replace('パスワード', ''))

    def test_the_ubsleepy_tables_script_grants_the_reader(self):
        text = (STACK / 'sql/ubsleepy_tables.sql').read_text(encoding='utf-8')
        self.assertIn('CREATE TABLE IF NOT EXISTS save_user', text)
        self.assertIn('CREATE TABLE IF NOT EXISTS save_value', text)
        self.assertIn('GRANT SELECT', text)
        self.assertIn('ubsleepy_reader', text)
        for forbidden in ('DROP ', 'DELETE FROM', 'TRUNCATE ', 'UPDATE '):
            self.assertNotIn(forbidden, text, forbidden)

    def test_the_backup_runs_daily_from_the_deployment_directory(self):
        service = (ROLE / 'templates/pkdb-backup.service.j2').read_text(encoding='utf-8')
        self.assertIn('manage.py backup --destination {{ pkdb_backup_dir }}', service)
        tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text(encoding='utf-8'))
        timer = next(task for task in tasks if 'ansible.builtin.systemd' in task)
        self.assertEqual(timer['ansible.builtin.systemd']['name'], 'pkdb-backup.timer')
        self.assertTrue(timer['ansible.builtin.systemd']['enabled'])


class ManageTests(unittest.TestCase):
    def project(self):
        directory = Path(tempfile.mkdtemp(prefix='pkdb-project-'))
        self.addCleanup(lambda: shutil.rmtree(directory, ignore_errors=True))
        state = directory.parent / (directory.name + '-state')
        self.addCleanup(lambda: shutil.rmtree(state, ignore_errors=True))
        patcher = patch.object(manage, 'ROOT', directory)
        patcher.start()
        self.addCleanup(patcher.stop)
        (directory / '.env.example').write_text(f'STORAGE_ROOT={state}\n', encoding='utf-8')
        return directory, state

    def client(self, names=('pkhack', 'sleepy_pkdb')):
        calls = []

        def run(program, *args, **kwargs):
            calls.append((program, args))
            if hasattr(kwargs.get('stdout'), 'write'):
                kwargs['stdout'].write(b'x' if 'b' in kwargs['stdout'].mode else 'x')
            if manage.LIST_DATABASES in args:
                return SimpleNamespace(stdout=''.join(name + '\n' for name in names))
            return SimpleNamespace(stdout='15.15\n')
        return run, calls

    def test_init_creates_the_password_private_and_never_regenerates_it(self):
        project, state = self.project()
        manage.init()
        password = project / 'secrets' / 'postgres_password'
        self.assertEqual(password.stat().st_mode & 0o777, 0o400)
        self.assertEqual((project / '.env').stat().st_mode & 0o777, 0o600)
        self.assertEqual((state / 'data').stat().st_mode & 0o777, 0o700)
        first = password.read_text(encoding='utf-8')
        self.assertTrue(first.strip())
        manage.init()
        self.assertEqual(password.read_text(encoding='utf-8'), first)

    def test_storage_refuses_a_state_inside_the_project(self):
        project, _ = self.project()
        (project / '.env').write_text(f'STORAGE_ROOT={project / "storage"}\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            manage.storage()

    def test_every_password_is_carried_over_including_the_superusers(self):
        sql = manage.roles_sql(GLOBALS, {'postgres'})
        self.assertNotIn('CREATE ROLE postgres', sql)
        self.assertIn("ALTER ROLE postgres WITH SUPERUSER LOGIN PASSWORD 'SCRAM-SHA-256$4096:old'", sql)
        self.assertIn('CREATE ROLE pkdb_reader;', sql)
        self.assertIn("PASSWORD 'SCRAM-SHA-256$4096:reader'", sql)
        self.assertIn('GRANT pkdb_reader TO pkdb_editor', sql)

    def test_an_existing_role_is_altered_but_not_created_again(self):
        sql = manage.roles_sql(GLOBALS, {'postgres', 'pkdb_reader'})
        self.assertNotIn('CREATE ROLE pkdb_reader;', sql)
        self.assertIn('ALTER ROLE pkdb_reader WITH', sql)
        self.assertIn('CREATE ROLE pkdb_editor;', sql)

    def test_a_dump_is_private_complete_and_lists_its_databases(self):
        project, _ = self.project()
        client, calls = self.client()
        target = project.parent / (project.name + '-dump')
        self.addCleanup(lambda: shutil.rmtree(target, ignore_errors=True))
        self.assertEqual(manage.dump(client, target), ['pkhack', 'sleepy_pkdb'])
        self.assertEqual(target.stat().st_mode & 0o777, 0o700)
        self.assertEqual((target / 'globals.sql').stat().st_mode & 0o777, 0o600)
        self.assertEqual(sorted(path.name for path in target.iterdir()),
                         ['globals.sql', 'manifest.json', 'pkhack.dump', 'sleepy_pkdb.dump'])
        manifest = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['databases'], ['pkhack', 'sleepy_pkdb'])
        self.assertIn(('pg_dump', ('-Fc', '-d', 'sleepy_pkdb')), calls)
        self.assertFalse(target.with_name(target.name + '.incomplete').exists())

    def test_a_dump_never_overwrites_an_existing_directory(self):
        project, _ = self.project()
        client, _ = self.client()
        with self.assertRaises(ValueError):
            manage.dump(client, project)

    def test_a_remote_client_needs_the_password_and_keeps_it_out_of_arguments(self):
        project, _ = self.project()
        shutil.copyfile(STACK / 'compose.lock.yaml', project / 'compose.lock.yaml')
        with patch.dict(manage.os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                manage.remote('127.0.0.1', 15432, 'postgres')
        with patch.dict(manage.os.environ, {manage.SOURCE_PASSWORD: 's3cret'}):
            client = manage.remote('127.0.0.1', 15432, 'postgres')
            with patch.object(manage, 'run') as run:
                client('pg_dumpall', '--globals-only')
        command = run.call_args.args[0]
        self.assertNotIn('s3cret', ' '.join(command))
        self.assertEqual(run.call_args.kwargs['env']['PGPASSWORD'], 's3cret')
        self.assertTrue(any(part.startswith('postgres@sha256:') for part in command))
        self.assertEqual(command[-8:], ['pg_dumpall', '-h', '127.0.0.1', '-p', '15432',
                                        '-U', 'postgres', '--globals-only'])

    def restore_fixture(self, project):
        directory = project / 'dump'
        directory.mkdir()
        (directory / 'globals.sql').write_text(GLOBALS, encoding='utf-8')
        for name in ('pkhack', 'sleepy_pkdb'):
            (directory / f'{name}.dump').write_bytes(b'archive')
        (directory / 'manifest.json').write_text(
            json.dumps({'databases': ['pkhack', 'sleepy_pkdb']}), encoding='utf-8')
        return directory

    def test_restore_leaves_an_existing_database_alone(self):
        project, _ = self.project()
        directory = self.restore_fixture(project)
        client, calls = self.client(names=('sleepy_pkdb',))
        with patch.object(manage, 'local', client):
            manage.restore(directory)
        restored = [args for program, args in calls if program == 'pg_restore']
        self.assertEqual(len(restored), 1)
        self.assertIn('--exit-on-error', restored[0])
        self.assertIn('--create', restored[0])

    def test_restore_does_nothing_when_every_database_exists(self):
        project, _ = self.project()
        directory = self.restore_fixture(project)
        client, calls = self.client()
        with patch.object(manage, 'local', client):
            manage.restore(directory)
        self.assertEqual([program for program, _ in calls], ['psql'])

    def test_restore_refuses_an_incomplete_dump(self):
        project, _ = self.project()
        directory = self.restore_fixture(project)
        (directory / 'pkhack.dump').unlink()
        client, calls = self.client(names=())
        with patch.object(manage, 'local', client):
            with self.assertRaises(ValueError):
                manage.restore(directory)
        self.assertEqual(calls, [])

    def test_apply_skips_a_database_that_is_not_restored_yet(self):
        project, _ = self.project()
        script = project / 'lowercase.sql'
        script.write_text('select 1;', encoding='utf-8')
        client, calls = self.client(names=())
        with patch.object(manage, 'local', client):
            manage.apply('sleepy_pkdb', script)
        self.assertEqual(len(calls), 1)

    def test_apply_always_runs_against_the_maintenance_database(self):
        project, _ = self.project()
        script = project / 'ubsleepy.sql'
        script.write_text('select 1;', encoding='utf-8')
        calls = []

        def client(program, *args, **kwargs):
            calls.append(args)
            return SimpleNamespace(stdout='', stderr='')
        with patch.object(manage, 'local', client):
            manage.apply('postgres', script)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:2], ('-d', 'postgres'))

    def test_apply_runs_the_script_in_one_transaction_and_reports_changes(self):
        project, _ = self.project()
        script = project / 'lowercase.sql'
        script.write_text('select 1;', encoding='utf-8')
        calls = []

        def client(program, *args, **kwargs):
            calls.append((args, kwargs))
            if manage.LIST_DATABASES in args:
                return SimpleNamespace(stdout='sleepy_pkdb\n')
            return SimpleNamespace(stdout='', stderr='NOTICE:  CHANGED: renamed 3 columns\n')
        with patch.object(manage, 'local', client), patch('builtins.print') as printed:
            manage.apply('sleepy_pkdb', script)
        args, kwargs = calls[-1]
        self.assertIn('--single-transaction', args)
        self.assertIn('ON_ERROR_STOP=1', args)
        self.assertEqual(kwargs['input'], 'select 1;')
        self.assertEqual(printed.call_args.args[0], 'CHANGED: renamed 3 columns')

    def test_apply_skips_the_transaction_for_a_marked_script(self):
        project, _ = self.project()
        script = project / 'ubsleepy.sql'
        script.write_text(manage.NO_TRANSACTION_MARKER + '\nselect 1;', encoding='utf-8')
        calls = []

        def client(program, *args, **kwargs):
            calls.append((args, kwargs))
            if manage.LIST_DATABASES in args:
                return SimpleNamespace(stdout='postgres\n')
            return SimpleNamespace(stdout='', stderr='')
        with patch.object(manage, 'local', client), patch('builtins.print'):
            manage.apply('postgres', script)
        args, kwargs = calls[-1]
        self.assertNotIn('--single-transaction', args)
        self.assertIn('ON_ERROR_STOP=1', args)

    def test_backup_keeps_only_the_newest_dumps(self):
        project, _ = self.project()
        (project / '.env').write_text((project / '.env.example').read_text(encoding='utf-8'),
                                      encoding='utf-8')
        destination = project / 'backups'
        for stamp in ('20260101T000000Z', '20260102T000000Z', '20260103T000000Z'):
            (destination / stamp).mkdir(parents=True)
        (destination / 'notes').mkdir()
        client, _ = self.client()
        with patch.object(manage, 'local', client):
            manage.backup(destination, keep=2)
        names = sorted(path.name for path in destination.iterdir())
        self.assertEqual(len(names), 3)
        self.assertIn('notes', names)
        self.assertNotIn('20260101T000000Z', names)
        self.assertNotIn('20260102T000000Z', names)

    def test_backup_refuses_a_destination_inside_the_data_directory(self):
        project, state = self.project()
        (project / '.env').write_text(f'STORAGE_ROOT={state}\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            manage.backup(state / 'data' / 'backups', keep=2)


if __name__ == '__main__':
    unittest.main()
