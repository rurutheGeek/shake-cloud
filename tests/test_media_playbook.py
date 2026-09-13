"""Guard the single media-01 entry point and the post-deploy verification.

media.yml is what makes the five independently developed units (W03-W06・LocalSend)
reproducible in one run; media-verify.yml is what turns "deployed" from a
memory into a check. These are source-text and YAML assertions in the same
spirit as test_media_nextcloud.py. The only thing executed is
`ansible-playbook --syntax-check`; nothing here connects to media-01.
"""
import shutil
import subprocess
import sys
import os
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
ANSIBLE = ROOT / 'platform/ansible'
ENTRY = ANSIBLE / 'media.yml'
VERIFY = ANSIBLE / 'media-verify.yml'
GROUP_VARS = ANSIBLE / 'group_vars/media.yml'
UNIT_PLAYBOOKS = ['media-nextcloud.yml', 'media-kavita.yml', 'media-localsend.yml',
                  'media-navidrome.yml', 'music-tools.yml']
COMPOSE_FILES = {
    'nextcloud': ROOT / 'stacks/media/nextcloud/compose.yaml',
    'kavita': ROOT / 'stacks/media/kavita/compose.yaml',
    'navidrome': ROOT / 'stacks/media/navidrome/compose.yaml',
    'music-tools': ROOT / 'stacks/music-tools/compose.yaml',
}


def read(path):
    return path.read_text(encoding='utf-8')


def ansible_playbook():
    candidate = Path(sys.executable).with_name('ansible-playbook')
    if candidate.exists():
        return str(candidate)
    found = shutil.which('ansible-playbook')
    if found:
        return found
    raise unittest.SkipTest('ansible-playbook is not installed')


class EntryPointTests(unittest.TestCase):
    """media.yml is the one command that deploys and then verifies media-01."""

    def setUp(self):
        self.text = read(ENTRY)
        self.imports = [entry['import_playbook'] for entry in yaml.safe_load(self.text)
                        if isinstance(entry, dict) and 'import_playbook' in entry]

    def test_the_base_then_the_five_units_run_in_order(self):
        self.assertEqual(self.imports[0], 'media-base.yml')
        self.assertEqual(self.imports[1:6], UNIT_PLAYBOOKS)

    def test_verification_and_the_https_entrypoint_run_last(self):
        self.assertEqual(self.imports[-2:], ['media-verify.yml', 'media-tls.yml'])

    def test_only_the_base_the_units_the_verifier_and_tls_are_imported(self):
        self.assertEqual(self.imports,
                         ['media-base.yml'] + UNIT_PLAYBOOKS + ['media-verify.yml', 'media-tls.yml'])

    def test_the_base_play_keeps_egress_on_ipv4(self):
        # The LAN's IPv6 default route does not reach the internet; Docker then
        # fails to pull images. The base play disables IPv6 until that is fixed.
        base = read(ANSIBLE / 'media-base.yml')
        self.assertIn('net.ipv6.conf.all.disable_ipv6 = 1', base)
        self.assertIn('sysctl --system', base)
        self.assertIn('/etc/sysctl.d/99-media-no-ipv6.conf', base)

    def test_romm_is_not_part_of_the_media_01_entry_point(self):
        # RomM is W07 on game1, not a media-01 unit.
        self.assertFalse(any('romm' in name.lower() for name in self.imports))
        self.assertIn('RomM', self.text)

    def test_it_warns_about_the_netbox_media_group(self):
        # `media` also exists in inventory.netbox.yml (media-stack tag), so the
        # entry point has to say which inventory to use and how to limit it.
        self.assertIn('inventory.netbox.yml', self.text)
        self.assertIn('inventory.cloud.py', self.text)
        self.assertIn('--limit', self.text)

    def test_it_documents_staged_execution_with_unit_playbooks(self):
        # import_playbook has no `when`; staged runs are separate invocations.
        for name in UNIT_PLAYBOOKS:
            self.assertIn(name, self.text)
        self.assertIn('--start-at-task', self.text)
        self.assertIn('media_units', self.text)

    def test_it_shows_the_json_form_for_list_variables(self):
        # `-e key=["a"]` is a string to Ansible; the comment must not teach it.
        self.assertIn('{"media_units"', self.text)
        self.assertIn('{"music_tools_services"', self.text)

    def test_every_imported_playbook_exists(self):
        for name in self.imports:
            self.assertTrue((ANSIBLE / name).is_file(), name)


class GroupVarsTests(unittest.TestCase):
    """Path variables live in group_vars/media.yml, not in the playbooks."""

    def test_the_group_vars_define_the_shared_paths(self):
        values = yaml.safe_load(read(GROUP_VARS))
        self.assertEqual(values['project_dir'], '/opt/media-stack')
        self.assertEqual(values['storage_root'], '/srv/media-stack/storage')
        self.assertEqual(values['library_root'], '/srv/media-stack/library')

    def test_the_verifier_uses_the_group_vars_project_dir(self):
        text = read(VERIFY)
        self.assertIn('{{ project_dir }}', text)
        self.assertNotIn('/opt/media-stack', text)
        self.assertNotIn('/srv/media-stack', text)

    def test_the_deployed_units_read_paths_from_the_group_vars(self):
        for name in UNIT_PLAYBOOKS:
            text = read(ANSIBLE / name)
            self.assertIn('{{ project_dir }}', text, name)
            self.assertNotIn('/opt/media-stack', text, name)


class VerifyTests(unittest.TestCase):
    """media-verify.yml reads status and endpoints; it never changes the host."""

    def setUp(self):
        self.play = yaml.safe_load(read(VERIFY))[0]
        self.tasks = self.play['tasks']
        self.vars = self.play['vars']

    def uri_tasks(self):
        return [task for task in self.tasks if 'ansible.builtin.uri' in task]

    def uri_for(self, fragment):
        for task in self.uri_tasks():
            if fragment in task['ansible.builtin.uri']['url']:
                return task
        raise AssertionError(f'no uri task targets {fragment}')

    def conditions(self):
        found = []
        for task in self.tasks:
            if 'ansible.builtin.assert' not in task:
                continue
            that = task['ansible.builtin.assert']['that']
            found.extend(that if isinstance(that, list) else [that])
        return '\n'.join(str(condition) for condition in found)

    def test_it_targets_the_media_group_as_root(self):
        self.assertEqual(self.play['hosts'], 'media')
        self.assertTrue(self.play['become'])

    def test_the_default_selection_is_all_four_units(self):
        self.assertEqual(self.vars['media_units'],
                         ['nextcloud', 'kavita', 'navidrome', 'music-tools'])

    def test_the_unit_directories_are_under_the_project_dir(self):
        directories = self.vars['media_unit_dirs']
        self.assertEqual(sorted(directories), sorted(self.vars['media_units']))
        for name, directory in directories.items():
            self.assertTrue(directory.startswith('{{ project_dir }}/'), name)

    def test_every_unit_is_read_with_manage_py_status(self):
        commands = [task['ansible.builtin.command']['argv'] for task in self.tasks
                    if 'ansible.builtin.command' in task]
        status = [argv for argv in commands if argv[-1] == 'status']
        self.assertEqual(len(status), 1)
        self.assertEqual(status[0][0], 'python3')
        self.assertIn('media_unit_dirs[item]', ''.join(status[0]))
        self.assertTrue(status[0][1].endswith('manage.py'))

    def test_every_check_is_read_only(self):
        for task in self.tasks:
            if 'ansible.builtin.command' in task or 'ansible.builtin.uri' in task:
                self.assertIs(task.get('changed_when'), False, task['name'])

    def test_every_http_check_uses_loopback(self):
        for task in self.uri_tasks():
            url = task['ansible.builtin.uri']['url']
            self.assertTrue(url.startswith('http://127.0.0.1:'), task['name'])
            self.assertNotIn('0.0.0.0', url, task['name'])

    def test_the_status_check_requires_running_and_healthy(self):
        conditions = self.conditions()
        self.assertIn("' Up '", conditions)
        self.assertIn('(healthy)', conditions)
        self.assertIn("'unhealthy' not in", conditions)

    def test_the_selection_must_be_a_list_not_a_string(self):
        # Ansible parses `-e key=["a"]` as a string; fail with guidance instead
        # of silently treating the value as one character per unit.
        conditions = self.conditions()
        self.assertIn('media_units is not string', conditions)
        self.assertIn('music_tools_services is not string', conditions)

    def test_the_staged_command_is_documented_as_json(self):
        self.assertIn('{"media_units"', read(VERIFY))

    def test_nextcloud_requires_installed_true_on_status_php(self):
        uri = self.uri_for('/status.php')['ansible.builtin.uri']
        self.assertIn('nextcloud_port', uri['url'])
        self.assertIn('"installed":true', self.conditions())

    def test_kavita_answers_on_its_loopback_port(self):
        uri = self.uri_for('kavita_port')['ansible.builtin.uri']
        self.assertIn(200, uri['status_code'])

    def test_navidrome_answers_on_its_loopback_port(self):
        uri = self.uri_for('navidrome_port')['ansible.builtin.uri']
        self.assertIn(200, uri['status_code'])

    def test_the_expected_service_and_health_counts_match_the_compose_projects(self):
        # The runtime check is an equality on the number of running services;
        # here it is enough that the expectations name real services and the
        # health count is the number of healthchecks among them.
        for name in ('nextcloud', 'kavita', 'navidrome'):
            compose = yaml.safe_load(read(COMPOSE_FILES[name]))
            expected = self.vars['media_unit_services'][name]
            self.assertLessEqual(set(expected), set(compose['services']), name)
            self.assertEqual(
                self.vars['media_unit_healthy'][name],
                sum('healthcheck' in compose['services'][service] for service in expected), name)

    def test_music_tools_expectations_follow_the_deploy_selection(self):
        # W06 deploys a subset with -e music_tools_services=[...]; the verifier
        # reads the same variable instead of hard-coding the full list.
        self.assertEqual(self.vars['music_tools_services'], ['metube', 'convert', 'tag-api'])
        self.assertNotIn('music-tools', self.vars['media_unit_services'])
        self.assertIn('default(music_tools_services)', self.conditions())
        compose = yaml.safe_load(read(COMPOSE_FILES['music-tools']))
        self.assertLessEqual(set(self.vars['music_tools_services']), set(compose['services']))
        # The verifier counts the healthchecked music-tools services; convert
        # and the tag API both have one.
        healthchecked = [service for service in self.vars['music_tools_services']
                         if 'healthcheck' in compose['services'][service]]
        self.assertEqual(healthchecked, ['convert', 'tag-api'])


class SyntaxTests(unittest.TestCase):
    def check(self, playbook):
        # The managed development VM may expose /home as read-only.  Ansible
        # otherwise tries to create its controller-side temporary directory
        # there before it can perform a syntax check.
        environment = os.environ.copy()
        environment.setdefault('ANSIBLE_LOCAL_TEMP', '/tmp/shake-cloud-ansible')
        result = subprocess.run(
            [ansible_playbook(), '--syntax-check', '-i', 'localhost,', str(playbook)],
            cwd=ROOT, capture_output=True, text=True, env=environment)
        self.assertEqual(result.returncode, 0,
                         f'{playbook.name} did not parse:\n{result.stdout}\n{result.stderr}')

    def test_the_entry_point_parses_including_its_imports(self):
        self.check(ENTRY)

    def test_the_verifier_parses(self):
        self.check(VERIFY)


if __name__ == '__main__':
    unittest.main()
