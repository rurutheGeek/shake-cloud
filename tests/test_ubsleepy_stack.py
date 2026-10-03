"""Guard the UBSLEEPY bot stack: the save data must survive updates and imports.

The bot keeps its users' records in CSV files next to its code. On apps-01 they
live outside the Git checkout and are mounted over it. A change that let an
update reach them, that started the bot before they were moved, or that let an
import write over them would lose data that exists nowhere else.
"""
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/ubsleepy'
ROLE = ROOT / 'platform/ansible/roles/ubsleepy'
SPEC = importlib.util.spec_from_file_location('ubsleepy_manage', STACK / 'manage.py')
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)

SAVE = {
    'save/report.csv': b'report',
    'log/bqlog.csv': b'quiz',
    'config.json': b'{}',
    'resource/pokemon_senryu.csv': b'senryu',
    'resource/image/decamark.png': b'png',
}


def archive(files, directories=()):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        for name in directories:
            info = tarfile.TarInfo(name)
            info.type = tarfile.DIRTYPE
            tar.addfile(info)
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class StackTests(unittest.TestCase):
    def compose(self):
        return yaml.safe_load((STACK / 'compose.yaml').read_text(encoding='utf-8'))

    def service(self):
        return self.compose()['services']['bot']

    def test_the_project_is_the_bot_alone_with_no_published_port(self):
        compose = self.compose()
        self.assertEqual(compose['name'], 'ubsleepy')
        self.assertEqual(list(compose['services']), ['bot'])
        self.assertNotIn('ports', self.service())

    def test_everything_the_bot_writes_is_mounted_from_the_state(self):
        volumes = self.service()['volumes']
        self.assertEqual(volumes[0], '${STORAGE_ROOT:-/srv/ubsleepy}/source:/app')
        mounted = {target[len('/app/'):]: host
                   for host, target in (volume.rsplit(':', 1) for volume in volumes[1:])}
        self.assertEqual(set(mounted), set(manage.STATE_DIRECTORIES + manage.STATE_FILES))
        for name, host in mounted.items():
            self.assertEqual(host, '${STORAGE_ROOT:-/srv/ubsleepy}/state/' + name)

    def test_the_state_covers_every_path_the_bot_is_configured_to_write(self):
        # config.json の PATH_DICT のうち Bot が書く先（2026-10-04 時点の main）。
        for path in ('save/pogakuin_list.csv', 'save/report.csv', 'save/graph.png',
                     'save/restmemorychannel.csv', 'save/call_cache.csv', 'save/output_cache.txt',
                     'log/feedbacks_log.csv', 'log/auth_log.csv', 'log/call_log.csv',
                     'log/bqlog.csv', 'resource/pokemon_senryu.csv', 'config.json',
                     'resource/image/decamark.png'):
            self.assertTrue(manage.allowed(path), path)
        for path in ('main.py', 'resource/pokemon_database.csv', 'bot_module/func.py'):
            self.assertFalse(manage.allowed(path), path)

    def test_the_token_is_required_and_comes_from_manage_py(self):
        self.assertEqual(self.service()['environment']['DISCORD_TOKEN'],
                         '${DISCORD_TOKEN:?run manage.py up}')
        self.assertNotIn('env_file', self.service())

    def test_the_lock_pins_the_same_repository_as_compose(self):
        self.assertEqual(self.service()['image'], 'python:3.13')
        lock = json.loads((STACK / 'compose.lock.yaml').read_text(encoding='utf-8'))
        self.assertRegex(lock['services']['bot']['image'], r'^python@sha256:[0-9a-f]{64}$')

    def test_the_env_example_carries_no_secret(self):
        text = (STACK / '.env.example').read_text(encoding='utf-8')
        self.assertNotIn('TOKEN', text)
        self.assertIn('UBSLEEPY_REPOSITORY=https://github.com/rurutheGeek/UBSLEEPY.git', text)
        self.assertIn('UBSLEEPY_BRANCH=main', text)

    def test_the_secrets_and_backups_stay_out_of_git(self):
        for name in ('secrets/discord_token', 'backups/20261004T000000Z.tar.gz'):
            result = subprocess.run(['git', 'check-ignore', '-q', str(STACK / name)], cwd=ROOT)
            self.assertEqual(result.returncode, 0, name)


class DeploymentTests(unittest.TestCase):
    def tasks(self):
        return yaml.safe_load((ROLE / 'tasks/main.yml').read_text(encoding='utf-8'))

    def test_the_playbook_targets_apps_without_the_http_entry(self):
        play = yaml.safe_load((ROOT / 'platform/ansible/ubsleepy.yml').read_text(encoding='utf-8'))[0]
        self.assertEqual(play['hosts'], 'apps')
        self.assertEqual(play['roles'], ['docker', 'ubsleepy'])

    def test_the_bot_is_not_started_before_the_save_data_is_moved(self):
        start = next(task for task in self.tasks() if task['name'] == 'Start the bot')
        self.assertEqual(start['when'], 'ubsleepy_state.stat.exists')

    def test_the_token_is_read_from_sops_and_never_logged(self):
        for name in ('Read the Discord token', 'Install the Discord token'):
            task = next(task for task in self.tasks() if task['name'] == name)
            self.assertTrue(task['no_log'], name)
        install = next(task for task in self.tasks() if task['name'] == 'Install the Discord token')
        self.assertEqual(install['ansible.builtin.copy']['mode'], '0400')
        self.assertTrue((ROOT / 'platform/sops/ubsleepy.sops.yaml.example').exists())

    def test_the_host_pulls_updates_and_archives_the_save_data(self):
        update = (ROLE / 'templates/ubsleepy-update.service.j2').read_text(encoding='utf-8')
        self.assertIn('ExecStart=/usr/bin/python3 manage.py update', update)
        backup = (ROLE / 'templates/ubsleepy-backup.service.j2').read_text(encoding='utf-8')
        self.assertIn('manage.py backup --destination {{ ubsleepy_backup_dir }}', backup)
        timers = next(task for task in self.tasks() if 'ansible.builtin.systemd' in task)
        self.assertEqual(timers['loop'], ['ubsleepy-update.timer', 'ubsleepy-backup.timer'])


class ManageTests(unittest.TestCase):
    def project(self):
        directory = Path(tempfile.mkdtemp(prefix='ubsleepy-project-'))
        self.addCleanup(lambda: shutil.rmtree(directory, ignore_errors=True))
        storage = directory.parent / (directory.name + '-storage')
        self.addCleanup(lambda: shutil.rmtree(storage, ignore_errors=True))
        patcher = patch.object(manage, 'ROOT', directory)
        patcher.start()
        self.addCleanup(patcher.stop)
        (directory / '.env.example').write_text(
            f'STORAGE_ROOT={storage}\nUBSLEEPY_REPOSITORY=https://example.invalid/bot.git\n'
            'UBSLEEPY_BRANCH=main\n', encoding='utf-8')
        manage.init()
        return directory, storage

    def tarball(self, project, files=SAVE, directories=('save', 'log', 'resource/image')):
        path = project / 'state.tar.gz'
        path.write_bytes(archive(files, directories))
        return path

    def test_init_lays_out_the_state_without_inventing_save_files(self):
        project, storage = self.project()
        self.assertEqual((project / '.env').stat().st_mode & 0o777, 0o600)
        self.assertEqual((project / 'secrets').stat().st_mode & 0o777, 0o700)
        for name in manage.STATE_DIRECTORIES:
            self.assertTrue((storage / 'state' / name).is_dir(), name)
        for name in manage.STATE_FILES:
            self.assertFalse((storage / 'state' / name).exists(), name)

    def test_storage_refuses_a_state_inside_the_project(self):
        project, _ = self.project()
        (project / '.env').write_text(f'STORAGE_ROOT={project / "storage"}\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            manage.storage()

    def test_up_refuses_to_start_without_the_save_data(self):
        project, storage = self.project()
        (project / 'compose.lock.yaml').write_text('{}', encoding='utf-8')
        (project / 'secrets' / 'discord_token').write_text('t\n', encoding='utf-8')
        (storage / 'source').mkdir()
        (storage / 'source' / 'main.py').write_text('', encoding='utf-8')
        with patch.object(manage, 'compose') as compose:
            with self.assertRaisesRegex(ValueError, 'Save data is missing'):
                manage.up()
            compose.assert_not_called()
            manage.import_state(self.tarball(project))
            manage.up()
        self.assertEqual(compose.call_args.args, ('up', '-d', '--remove-orphans'))

    def test_up_refuses_to_start_without_the_token(self):
        project, _ = self.project()
        (project / 'compose.lock.yaml').write_text('{}', encoding='utf-8')
        with patch.object(manage, 'compose') as compose:
            with self.assertRaisesRegex(ValueError, 'discord_token'):
                manage.up()
        compose.assert_not_called()

    def test_import_places_the_old_hosts_files_and_keeps_their_content(self):
        project, storage = self.project()
        manage.import_state(self.tarball(project))
        for name, data in SAVE.items():
            self.assertEqual((storage / 'state' / name).read_bytes(), data, name)
        self.assertEqual(manage.missing_state(), [])

    def test_import_never_writes_over_existing_save_data(self):
        project, storage = self.project()
        manage.import_state(self.tarball(project))
        (storage / 'state' / 'save' / 'report.csv').write_bytes(b'newer')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            manage.import_state(self.tarball(project))
        self.assertEqual((storage / 'state' / 'save' / 'report.csv').read_bytes(), b'newer')

    def test_import_refuses_entries_outside_the_save_data(self):
        project, storage = self.project()
        for name in ('main.py', '../escape', 'save/../../escape', '/etc/passwd'):
            with self.assertRaises(ValueError, msg=name):
                manage.import_state(self.tarball(project, {**SAVE, name: b'x'}))
            self.assertEqual(manage.state_files(), [], name)

    def test_import_refuses_an_archive_that_lacks_a_save_file(self):
        project, _ = self.project()
        files = {name: data for name, data in SAVE.items() if name != 'config.json'}
        with self.assertRaisesRegex(ValueError, 'lacks'):
            manage.import_state(self.tarball(project, files))

    def test_digest_matches_sha256sum_of_the_state(self):
        project, storage = self.project()
        manage.import_state(self.tarball(project))
        expected = subprocess.run(
            'find . -type f | sed "s|^\\./||" | LC_ALL=C sort | xargs sha256sum',
            shell=True, cwd=storage / 'state', capture_output=True, text=True, check=True).stdout
        with patch('builtins.print') as printed:
            manage.digest()
        lines = ''.join(call.args[0] + '\n' for call in printed.call_args_list)
        self.assertEqual(lines, expected)

    def update_fixture(self, head, fetched, running):
        calls = []

        def git(*args):
            calls.append(args)
            if args[:2] == ('rev-parse', 'FETCH_HEAD'):
                return fetched
            if args[:2] == ('rev-parse', 'HEAD'):
                return head
            return ''
        return git, calls, SimpleNamespace(stdout='bot\n' if running else '')

    def test_update_leaves_a_current_checkout_and_the_bot_alone(self):
        _, storage = self.project()
        (storage / 'source' / '.git').mkdir(parents=True)
        git, calls, ps = self.update_fixture('a' * 40, 'a' * 40, running=True)
        with patch.object(manage, 'git', git), patch.object(manage, 'compose', return_value=ps) as compose:
            manage.update()
        self.assertNotIn(('reset', '--hard', 'a' * 40), calls)
        compose.assert_not_called()

    def test_update_resets_the_checkout_and_restarts_a_running_bot(self):
        _, storage = self.project()
        (storage / 'source' / '.git').mkdir(parents=True)
        git, calls, ps = self.update_fixture('a' * 40, 'b' * 40, running=True)
        with patch.object(manage, 'git', git), patch.object(manage, 'compose', return_value=ps) as compose:
            manage.update()
        self.assertIn(('reset', '--hard', 'b' * 40), calls)
        self.assertEqual(compose.call_args.args, ('up', '-d', '--force-recreate'))

    def test_update_does_not_start_a_bot_that_is_not_running(self):
        _, storage = self.project()
        (storage / 'source' / '.git').mkdir(parents=True)
        git, _, ps = self.update_fixture('a' * 40, 'b' * 40, running=False)
        with patch.object(manage, 'git', git), patch.object(manage, 'compose', return_value=ps) as compose:
            manage.update()
        self.assertEqual([call.args[0] for call in compose.call_args_list], ['ps'])

    def test_backup_archives_the_state_and_keeps_the_newest(self):
        project, storage = self.project()
        manage.import_state(self.tarball(project))
        destination = storage / 'backups'
        destination.mkdir()
        for stamp in ('20260101T000000Z', '20260102T000000Z'):
            (destination / f'{stamp}.tar.gz').write_bytes(b'old')
        manage.backup(destination, keep=2)
        names = sorted(path.name for path in destination.iterdir())
        self.assertEqual(len(names), 2)
        self.assertNotIn('20260101T000000Z.tar.gz', names)
        with tarfile.open(destination / names[-1]) as tar:
            archived = {member.name for member in tar.getmembers() if member.isfile()}
        self.assertEqual(archived, set(SAVE))

    def test_backup_refuses_a_destination_inside_the_save_data(self):
        _, storage = self.project()
        with self.assertRaises(ValueError):
            manage.backup(storage / 'state' / 'backups', keep=2)


if __name__ == '__main__':
    unittest.main()
