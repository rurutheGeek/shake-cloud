"""The shared way a play deploys one Compose stack through its manage.py."""
from pathlib import Path
import unittest

import yaml

from support import compose_stack_vars

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / 'platform/ansible/roles/compose_stack'
# Plays that have been moved onto the role. The rest still spell the steps out.
PLAYS = ['media-kavita.yml', 'media-navidrome.yml', 'media-freshrss.yml', 'media-localsend.yml']


class RoleTests(unittest.TestCase):
    def setUp(self):
        self.tasks = {task['name']: task for task in yaml.safe_load((ROLE / 'tasks/main.yml').read_text())}
        self.defaults = yaml.safe_load((ROLE / 'defaults/main.yml').read_text())

    def test_the_environment_is_private(self):
        env = self.tasks['Write the stack environment']['ansible.builtin.copy']
        self.assertEqual(env['mode'], '0600')
        self.assertEqual(env['dest'], '{{ compose_stack_project_dir }}/.env')

    def test_the_definitions_are_in_place_before_manage_py_runs(self):
        order = list(self.tasks)
        for earlier in ('Create the stack directory', 'Copy the stack definitions',
                        'Copy the stack directories', 'Write the stack environment'):
            self.assertLess(order.index(earlier), order.index("Run the stack's manage.py"), earlier)

    def test_state_is_prepared_before_the_stack_starts(self):
        self.assertEqual(self.defaults['compose_stack_actions'], ['init', 'up'])
        manage = self.tasks["Run the stack's manage.py"]
        self.assertEqual(manage['ansible.builtin.command']['argv'],
                         ['python3', '{{ compose_stack_project_dir }}/manage.py', '{{ item }}'])
        self.assertEqual(manage['loop'], '{{ compose_stack_actions }}')

    def test_a_rerun_that_changes_nothing_reports_nothing(self):
        # manage.py prints CHANGED: only when it made something; docker compose
        # names the containers it created or replaced on stderr. A play that
        # always says "changed" hides the run that really changed something.
        changed = self.tasks["Run the stack's manage.py"]['changed_when']
        self.assertNotEqual(changed, True)
        self.assertIn("'CHANGED' in compose_stack_manage.stdout", changed)
        for word in ('Created', 'Recreated', 'Started'):
            self.assertIn(f"'{word}' in compose_stack_manage.stderr", changed)

    def test_every_manage_py_follows_the_convention_the_role_reads(self):
        for name in PLAYS:
            stack = compose_stack_vars(yaml.safe_load((ROOT / 'platform/ansible' / name).read_text())[0])
            relative = stack['compose_stack_source_dir'].replace('{{ source_dir }}/', '')
            text = (ROOT / 'stacks' / relative / 'manage.py').read_text()
            self.assertIn("'init'", text, name)
            self.assertIn("'up'", text, name)
            self.assertIn("print('OK:", text, name)


class PlayTests(unittest.TestCase):
    def test_each_play_names_files_that_exist(self):
        for name in PLAYS:
            stack = compose_stack_vars(yaml.safe_load((ROOT / 'platform/ansible' / name).read_text())[0])
            source = ROOT / 'stacks' / stack['compose_stack_source_dir'].replace('{{ source_dir }}/', '')
            for file_name in stack['compose_stack_files']:
                self.assertTrue((source / file_name).is_file(), f'{name}: {file_name}')
            for directory in stack.get('compose_stack_directories', []):
                self.assertTrue((source / directory).is_dir(), f'{name}: {directory}')
            # The digests are reviewed in Git and must reach the host.
            self.assertIn('compose.lock.yaml', stack['compose_stack_files'], name)
            self.assertIn('manage.py', stack['compose_stack_files'], name)

    def test_the_moved_plays_no_longer_claim_a_change_on_every_run(self):
        for name in PLAYS:
            text = (ROOT / 'platform/ansible' / name).read_text()
            self.assertNotIn('changed_when: true', text, name)


class ChangeReportingTests(unittest.TestCase):
    """A play that always says "changed" hides the run that changed something."""

    # Plays that still claim a change on every manage.py call, and why.
    PENDING = {
        # 未コミットの作業と重なる。そちらが入ってから直す。
        'home-assistant.yml',
        # 旧一体型スタック。移行元が使っている可能性があり、触らない。
        'deploy.yml',
    }

    def test_no_play_claims_a_change_for_every_manage_py_call(self):
        for path in sorted((ROOT / 'platform/ansible').glob('*.yml')):
            if path.name in self.PENDING:
                continue
            loaded = yaml.safe_load(path.read_text())
            if not isinstance(loaded, list):
                continue
            for play in loaded:
                for task in (play.get('tasks') or []) if isinstance(play, dict) else []:
                    argv = task.get('ansible.builtin.command', {}).get('argv', []) if isinstance(task.get('ansible.builtin.command'), dict) else []
                    if any(str(part).endswith('manage.py') for part in argv):
                        self.assertIsNot(task.get('changed_when'), True, f"{path.name}: {task['name']}")

    def test_the_pending_list_only_names_plays_that_still_need_it(self):
        for name in self.PENDING:
            self.assertIn('changed_when: true', (ROOT / 'platform/ansible' / name).read_text(), name)


if __name__ == '__main__':
    unittest.main()
