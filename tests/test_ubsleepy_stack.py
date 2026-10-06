"""Guard the UBSLEEPY bot stack: the save data must survive updates and deploys.

The bot keeps its users' records under STORAGE_ROOT/state on apps-01. The image
is pinned by digest in compose.lock.yaml, and the bot never starts before the
save data is in place. A change that let a deploy reach the data, that started
the bot with nothing, or that let the mounts miss a write path would lose
records that exist nowhere else.
"""
import importlib.util
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
ROLE = ROOT / 'platform/ansible/roles/ubsleepy-next'
SPEC = importlib.util.spec_from_file_location('ubsleepy_manage', STACK / 'manage.py')
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)

# セーブデータ（Botが書き、どこにも残っていないもの）。
SAVE = {
    'save/report.csv': b'report',
    'log/bqlog.csv': b'quiz',
    'config.json': b'{}',
    'resource/pokemon_senryu.csv': b'senryu',
    'resource/image/decamark.png': b'png',
}


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

    def test_the_save_data_is_mounted_from_the_state(self):
        mounted = {}
        for volume in self.service()['volumes']:
            host, target = volume.rsplit(':', 1)
            self.assertEqual(host, '${STORAGE_ROOT:-/srv/ubsleepy-next}/state/'
                             + target[len('/app/'):])
            mounted[target] = host
        self.assertEqual(set(mounted), {f'/app/{name}' for name in
                                        manage.STATE_DIRECTORIES + manage.STATE_FILES})

    def test_the_state_covers_every_path_the_bot_is_configured_to_write(self):
        # config.json の PATH_DICT のうち Bot が書く先（2026-10-04 時点の main）。
        covered = manage.STATE_DIRECTORIES + manage.STATE_FILES

        def mounted(path):
            return any(path == name or path.startswith(name + '/') for name in covered)

        for path in ('save/pogakuin_list.csv', 'save/report.csv', 'save/graph.png',
                     'save/restmemorychannel.csv', 'save/call_cache.csv', 'save/output_cache.txt',
                     'log/feedbacks_log.csv', 'log/auth_log.csv', 'log/call_log.csv',
                     'log/bqlog.csv', 'resource/pokemon_senryu.csv', 'config.json',
                     'resource/image/decamark.png'):
            self.assertTrue(mounted(path), path)
        for path in ('main.py', 'resource/pokemon_database.csv', 'bot_module/func.py'):
            self.assertFalse(mounted(path), path)

    def test_the_secrets_are_required_and_come_from_manage_py(self):
        environment = self.service()['environment']
        self.assertEqual(environment['DISCORD_TOKEN'], '${DISCORD_TOKEN:?run the playbook}')
        self.assertEqual(environment['PKDB_PASSWORD'], '${PKDB_PASSWORD:?run the playbook}')
        self.assertEqual(environment['UBSLEEPY_DB_PASSWORD'],
                         '${UBSLEEPY_DB_PASSWORD:?run the playbook}')
        self.assertEqual(environment['UBSLEEPY_DB_NAME'], '${UBSLEEPY_DB_NAME:-ubsleepy}')
        self.assertNotIn('env_file', self.service())

    def test_the_lock_pins_the_image_the_compose_uses(self):
        self.assertEqual(
            self.service()['image'],
            '${UBSLEEPY_NEXT_IMAGE:-ghcr.io/ruruthegeek/ubsleepy-next}')
        lock = yaml.safe_load((STACK / 'compose.lock.yaml').read_text(encoding='utf-8'))
        self.assertRegex(
            lock['services']['bot']['image'],
            r'^ghcr\.io/ruruthegeek/ubsleepy-next@sha256:[0-9a-f]{64}$')

    def test_the_env_example_carries_no_secret(self):
        text = (STACK / '.env.example').read_text(encoding='utf-8')
        self.assertNotIn('TOKEN', text)
        self.assertNotIn('PASSWORD', text)
        self.assertIn('STORAGE_ROOT=/srv/ubsleepy', text)

    def test_the_secrets_and_backups_stay_out_of_git(self):
        for name in ('secrets/discord_token', 'backups/20261004T000000Z.tar.gz'):
            result = subprocess.run(['git', 'check-ignore', '-q', str(STACK / name)], cwd=ROOT)
            self.assertEqual(result.returncode, 0, name)


class DeploymentTests(unittest.TestCase):
    def tasks(self):
        return yaml.safe_load((ROLE / 'tasks/main.yml').read_text(encoding='utf-8'))

    def play(self):
        return yaml.safe_load(
            (ROOT / 'platform/ansible/ubsleepy.yml').read_text(encoding='utf-8'))[0]

    def test_the_playbook_targets_apps_without_the_http_entry(self):
        play = self.play()
        self.assertEqual(play['hosts'], 'apps')
        self.assertEqual(play['roles'][0], 'docker')
        role = play['roles'][1]
        self.assertEqual(role['role'], 'ubsleepy-next')
        # 本番の向き先（ロールの既定はテスト配備）。
        self.assertEqual(role['vars']['ubsleepy_next_project_dir'], '/opt/ubsleepy')
        self.assertEqual(role['vars']['ubsleepy_next_storage_root'], '/srv/ubsleepy')
        self.assertFalse(role['vars']['ubsleepy_next_test'])
        self.assertEqual(role['vars']['ubsleepy_next_token_key'], 'DISCORD_TOKEN')

    def test_the_playbook_deploys_the_production_stack(self):
        # 本番playbookは本番スタック（compose の name: ubsleepy）を配る。
        # ロールの既定（テスト配備の stacks/ubsleepy-next）のままだと、
        # /opt/ubsleepy に name: ubsleepy-next の compose が入り、
        # テストと同じ compose プロジェクト名になってしまう。
        role = self.play()['roles'][1]
        self.assertEqual(role['vars']['ubsleepy_next_source_dir'],
                         '{{ playbook_dir }}/../../stacks/ubsleepy')
        compose = yaml.safe_load(
            (ROOT / 'stacks/ubsleepy/compose.yaml').read_text(encoding='utf-8'))
        self.assertEqual(compose['name'], 'ubsleepy')

    def test_the_old_auto_update_units_are_removed(self):
        # イメージ固定なので、ホストが git pull する更新タイマーは消して戻さない。
        names = [task['name'] for task in self.play()['tasks']]
        self.assertIn('Stop the old auto-update timer', names)
        self.assertIn('Remove the old auto-update units', names)
        for task in self.tasks():
            self.assertNotIn('ubsleepy-update.timer', task.get('loop', []))

    def test_the_bot_is_not_started_before_the_save_data_is_moved(self):
        look = next(task for task in self.tasks() if task['name'] == 'Look for the save data')
        self.assertEqual(look['ansible.builtin.stat']['path'],
                         '{{ ubsleepy_next_storage_root }}/state/config.json')
        start = next(task for task in self.tasks() if task['name'] == 'Start the bot')
        self.assertEqual(start['when'], 'ubsleepy_next_state.stat.exists')

    def test_the_secrets_are_read_from_sops_and_never_logged(self):
        read = next(task for task in self.tasks()
                    if task['name'] == 'Read the UBSLEEPY credentials')
        self.assertTrue(read['no_log'])
        install = next(task for task in self.tasks()
                       if task['name'] == 'Install the Discord token')
        self.assertTrue(install['no_log'])
        self.assertEqual(install['ansible.builtin.copy']['mode'], '0400')
        database = next(task for task in self.tasks()
                        if task['name'] == 'Install the database secrets')
        self.assertEqual(database['loop'], ['PKDB_PASSWORD', 'UBSLEEPY_DB_PASSWORD'])
        self.assertTrue(database['no_log'])
        self.assertTrue((ROOT / 'platform/sops/ubsleepy.sops.yaml.example').exists())

    def test_the_role_fetches_the_cries_into_the_state(self):
        task = next(task for task in self.tasks() if task['name'] == 'Fetch the cries')
        self.assertEqual(task['ansible.builtin.command']['argv'],
                         ['python3', 'manage.py', 'cries'])
        self.assertEqual(task['when'], 'ubsleepy_next_state.stat.exists')

    def test_the_host_archives_the_save_data_daily(self):
        service = (ROLE / 'templates/ubsleepy-backup.service.j2').read_text(encoding='utf-8')
        self.assertIn('manage.py backup --destination', service)
        self.assertIn('--keep {{ ubsleepy_next_backup_keep }}', service)
        timer = (ROLE / 'templates/ubsleepy-backup.timer.j2').read_text(encoding='utf-8')
        self.assertIn('OnCalendar={{ ubsleepy_next_backup_calendar }}', timer)
        enabled = [task for task in self.tasks()
                   if task.get('ansible.builtin.systemd', {}).get('name') == 'ubsleepy-backup.timer']
        self.assertTrue(enabled)


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
            f'STORAGE_ROOT={storage}\n', encoding='utf-8')
        manage.init()
        return directory, storage

    def write_state(self, storage, files=SAVE):
        for name, data in files.items():
            path = storage / 'state' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def write_secrets(self, project):
        for name in ('discord_token', 'pkdb_password', 'ubsleepy_db_password'):
            (project / 'secrets' / name).write_text('x\n', encoding='utf-8')

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
        self.write_secrets(project)
        with patch.object(manage, 'compose') as compose:
            with self.assertRaisesRegex(ValueError, 'Save data is missing'):
                manage.up()
            compose.assert_not_called()
            self.write_state(storage)
            manage.up()
        self.assertEqual(compose.call_args.args, ('up', '-d', '--remove-orphans'))
        self.assertIn(('pull',), [call.args for call in compose.call_args_list])

    def test_up_refuses_to_start_without_the_token(self):
        project, _ = self.project()
        (project / 'compose.lock.yaml').write_text('{}', encoding='utf-8')
        with patch.object(manage, 'compose') as compose:
            with self.assertRaisesRegex(ValueError, 'discord_token'):
                manage.up()
        compose.assert_not_called()

    def test_deploy_pins_the_resolved_digest_and_starts(self):
        project, _ = self.project()
        digest = 'sha256:' + 'a' * 64
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            if args[:2] == ['docker', 'inspect']:
                return SimpleNamespace(
                    stdout=f'ghcr.io/ruruthegeek/ubsleepy-next@{digest}\n', stderr='')
            return SimpleNamespace(stdout='', stderr='')

        with patch.object(manage, 'run', fake_run), \
                patch.object(manage, 'compose') as compose, \
                patch('builtins.print'):
            manage.deploy('b' * 40)

        self.assertIn(['docker', 'pull', f'{manage.IMAGE}:{"b" * 40}'], calls)
        lock = (project / 'compose.lock.yaml').read_text(encoding='utf-8')
        self.assertIn(f'image: {manage.IMAGE}@{digest}', lock)
        self.assertEqual(compose.call_args.args, ('up', '-d', '--remove-orphans'))

    def test_deploy_needs_a_commit(self):
        self.project()
        with self.assertRaisesRegex(ValueError, 'deploy'):
            manage.deploy('')

    def test_digest_matches_sha256sum_of_the_state(self):
        _, storage = self.project()
        self.write_state(storage)
        expected = subprocess.run(
            'find . -type f | sed "s|^\\./||" | LC_ALL=C sort | xargs sha256sum',
            shell=True, cwd=storage / 'state', capture_output=True, text=True, check=True).stdout
        with patch('builtins.print') as printed:
            manage.digest()
        lines = ''.join(call.args[0] + '\n' for call in printed.call_args_list)
        self.assertEqual(lines, expected)

    def test_backup_archives_the_state_and_keeps_the_newest(self):
        _, storage = self.project()
        self.write_state(storage)
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

    def test_backup_leaves_the_redownloadable_cries_out(self):
        _, storage = self.project()
        self.write_state(storage)
        cry = storage / 'state' / 'resource' / 'cry' / 'latest'
        cry.mkdir(parents=True)
        (cry / '0006.ogg').write_bytes(b'cry')
        destination = storage / 'backups'
        manage.backup(destination, keep=2)
        target = sorted(destination.glob('*.tar.gz'))[-1]
        with tarfile.open(target) as tar:
            archived = {member.name for member in tar.getmembers() if member.isfile()}
        self.assertEqual(archived, set(SAVE))  # 鳴き声は再取得できるので入らない

    def test_cries_runs_the_fetch_inside_the_container(self):
        self.project()
        with patch.object(manage, 'compose',
                          return_value=SimpleNamespace(stdout='abc123\n')) as compose, \
                patch.object(manage, 'run') as run:
            manage.cries()
        self.assertEqual(compose.call_args.args, ('ps', '-q', 'bot'))
        run.assert_called_once_with(
            ['docker', 'exec', 'abc123', 'python', 'tools/fetch_cries.py'])

    def test_backup_refuses_a_destination_inside_the_save_data(self):
        _, storage = self.project()
        with self.assertRaises(ValueError):
            manage.backup(storage / 'state' / 'backups', keep=2)


if __name__ == '__main__':
    unittest.main()
