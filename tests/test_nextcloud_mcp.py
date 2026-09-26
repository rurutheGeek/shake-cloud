"""Guard the Nextcloud MCP deployment (A06) after the move to its own repository.

The server implementation lives in https://github.com/rurutheGeek/nextcloud-mcp
and is pulled from a pinned GitHub release. This file guards what stays in this
repository: the pinned version, the Ansible play, the systemd unit and the
syntax of the playbook.
"""
from pathlib import Path
import unittest

import yaml

from support import read, role_task, syntax_check

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/nextcloud-mcp'
PLAYBOOK = ROOT / 'platform/ansible/media-nextcloud-mcp.yml'
GROUP_VARS = ROOT / 'platform/ansible/group_vars/media.yml'
SOPS_EXAMPLE = ROOT / 'platform/sops/music-tags.sops.yaml.example'


class MigrationTests(unittest.TestCase):
    def test_the_implementation_is_no_longer_vendored_here(self):
        self.assertFalse((STACK / 'nextcloud_mcp.py').exists())
        self.assertTrue((STACK / 'nextcloud-mcp.service.j2').exists())

    def test_the_release_is_pinned_in_group_vars(self):
        group = yaml.safe_load(read(GROUP_VARS))
        self.assertRegex(group['nextcloud_mcp_version'], r'^\d+\.\d+\.\d+$')
        self.assertRegex(group['nextcloud_mcp_sha256'], r'^[0-9a-f]{64}$')
        self.assertEqual(group['nextcloud_mcp_sha256'],
                         '1de830942d2255258d0805915a5cad91fca28225a974a07dad1631ea33fc4b3e')

    def test_the_play_pulls_the_pinned_release_with_a_checksum(self):
        play = yaml.safe_load(read(PLAYBOOK))[0]
        task = role_task(play['tasks'], 'Install the MCP server')
        fetch = task['ansible.builtin.get_url']
        self.assertIn('github.com/rurutheGeek/nextcloud-mcp/releases/download/', fetch['url'])
        self.assertIn('nextcloud_mcp_version', fetch['url'])
        self.assertEqual(fetch['checksum'], 'sha256:{{ nextcloud_mcp_sha256 }}')
        self.assertEqual(fetch['mode'], '0755')


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.play = yaml.safe_load(read(PLAYBOOK))[0]
        self.tasks = self.play['tasks']

    def test_the_server_binds_to_loopback_only(self):
        task = role_task(self.tasks, 'Write the MCP environment')
        content = task['ansible.builtin.copy']['content']
        self.assertIn('NEXTCLOUD_MCP_BIND=127.0.0.1', content)
        self.assertIn('NEXTCLOUD_MCP_PORT={{ nextcloud_mcp_port }}', content)

    def test_the_tag_api_token_is_read_from_sops_without_logging(self):
        task = role_task(self.tasks, 'Read the music tag API token')
        self.assertTrue(task['no_log'])
        self.assertIn('music-tags.sops.yaml', str(task['ansible.builtin.command']['argv']))
        env_task = role_task(self.tasks, 'Write the MCP environment')
        self.assertTrue(env_task['no_log'])
        self.assertIn('NEXTCLOUD_MCP_TAG_API_TOKEN=', env_task['ansible.builtin.copy']['content'])

    def test_the_environment_file_is_written_with_owner_only_permissions(self):
        task = role_task(self.tasks, 'Write the MCP environment')
        self.assertEqual(task['ansible.builtin.copy']['mode'], '0400')

    def test_the_temporary_directory_is_created_on_disk_not_tmpfs(self):
        task = role_task(self.tasks, 'Create the MCP temporary directory')
        self.assertEqual(task['ansible.builtin.file']['path'], '{{ nextcloud_mcp_tmp }}')
        self.assertEqual(task['ansible.builtin.file']['mode'], '0700')

    def test_the_unit_is_installed_and_started(self):
        names = [task['name'] for task in self.tasks]
        for name in ('Install the MCP server', 'Install the MCP unit',
                     'Enable and start the MCP server', 'Wait for the MCP server'):
            self.assertIn(name, names)

    def test_the_health_check_targets_the_configured_port(self):
        task = role_task(self.tasks, 'Wait for the MCP server')
        self.assertEqual(task['ansible.builtin.uri']['url'],
                         'http://127.0.0.1:{{ nextcloud_mcp_port }}/healthz')

    def test_the_default_port_matches_the_service(self):
        self.assertEqual(self.play['vars']['nextcloud_mcp_port'], 5811)

    def test_the_sops_example_documents_the_shared_tag_token(self):
        example = read(SOPS_EXAMPLE)
        self.assertIn('TAG_API_TOKEN:', example)


class SystemdUnitTests(unittest.TestCase):
    def test_the_unit_confines_writes_to_the_temporary_directory(self):
        unit = read(STACK / 'nextcloud-mcp.service.j2')
        self.assertIn('ProtectSystem=strict', unit)
        self.assertIn('ReadWritePaths={{ nextcloud_mcp_tmp }}', unit)
        self.assertIn('ExecStart=/usr/bin/python3 {{ nextcloud_mcp_dir }}/nextcloud_mcp.py', unit)
        self.assertIn('EnvironmentFile={{ nextcloud_mcp_dir }}/nextcloud-mcp.env', unit)

    def test_the_unit_restarts_on_failure(self):
        unit = read(STACK / 'nextcloud-mcp.service.j2')
        self.assertIn('Restart=on-failure', unit)
        self.assertIn('WantedBy=multi-user.target', unit)


class SyntaxTests(unittest.TestCase):
    def test_the_playbook_parses(self):
        result = syntax_check(PLAYBOOK)
        self.assertEqual(result.returncode, 0,
                         f'{PLAYBOOK.name} did not parse:\n{result.stdout}\n{result.stderr}')


if __name__ == '__main__':
    unittest.main()
