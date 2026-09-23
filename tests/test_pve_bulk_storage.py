"""Guard the shared bulk storage: host role, media-01 mount, and docs.

The 6TB USB HDD carries both the media library and the ROM library. A wrong
export option (root_squash instead of all_squash) breaks Kavita's read path,
and a missing fail-closed dependency would let Docker write into the local
directory that the NFS mount later hides. These are source-text and YAML
assertions; the only thing executed is `ansible-playbook --syntax-check`.
"""
import unittest
from pathlib import Path

import yaml

from support import read, syntax_check

ROOT = Path(__file__).resolve().parents[1]
ANSIBLE = ROOT / 'platform/ansible'
ROLE = ANSIBLE / 'roles/pve_bulk_storage'
DEFAULTS = yaml.safe_load((ROLE / 'defaults/main.yml').read_text(encoding='utf-8'))
TASKS = yaml.safe_load((ROLE / 'tasks/main.yml').read_text(encoding='utf-8'))
PLAYBOOK = ANSIBLE / 'pve-bulk-storage.yml'
MEDIA_BASE = ANSIBLE / 'media-base.yml'
GROUP_VARS = ANSIBLE / 'group_vars/media.yml'
DOC = ROOT / 'docs/operations/bulk-storage.md'
MKDOCS = ROOT / 'mkdocs.yml'


class HostRoleTests(unittest.TestCase):
    def test_the_disk_is_pinned_to_its_ata_identity(self):
        self.assertTrue(DEFAULTS['pve_bulk_storage_device'].startswith('/dev/disk/by-id/ata-'))

    def test_initialization_is_off_by_default(self):
        # The role must never wipe an unrecognized filesystem on its own.
        self.assertFalse(DEFAULTS['pve_bulk_storage_initialize'])

    def test_the_mount_survives_a_missing_disk(self):
        opts = DEFAULTS['pve_bulk_storage_fstab_opts']
        self.assertIn('nofail', opts)
        self.assertIn('noatime', opts)

    def test_the_media_export_squashes_to_www_data(self):
        export = [item for item in DEFAULTS['pve_bulk_storage_exports']
                  if 'media_dir' in item['path']][0]
        self.assertEqual(export['clients'], '192.168.10.101')
        self.assertIn('all_squash', export['options'])
        self.assertIn('anonuid=33', export['options'])
        self.assertIn('anongid=33', export['options'])

    def test_the_roms_export_squashes_to_the_game1_uid(self):
        export = [item for item in DEFAULTS['pve_bulk_storage_exports']
                  if 'roms_dir' in item['path']][0]
        self.assertEqual(export['clients'], '192.168.10.127')
        self.assertIn('all_squash', export['options'])
        self.assertIn('anonuid=1000', export['options'])

    def test_the_shared_directories_match_the_export_ids(self):
        self.assertEqual(DEFAULTS['pve_bulk_storage_media_uid'], 33)
        self.assertEqual(DEFAULTS['pve_bulk_storage_roms_uid'], 1000)
        self.assertEqual(sorted(DEFAULTS['pve_bulk_storage_media_subdirs']),
                         ['books', 'docs', 'inbox', 'music'])

    def test_the_game1_saves_export_lives_under_the_backup_root(self):
        saves = DEFAULTS['pve_bulk_storage_game1_saves_dir']
        backups = DEFAULTS['pve_bulk_storage_backup_dir']
        self.assertEqual(backups, '{{ pve_bulk_storage_mount }}/backups')
        self.assertEqual(saves, '{{ pve_bulk_storage_backup_dir }}/game1-saves')
        export = [item for item in DEFAULTS['pve_bulk_storage_exports']
                  if 'game1_saves_dir' in item['path']][0]
        self.assertEqual(export['clients'], '192.168.10.127')
        self.assertIn('anonuid=1000', export['options'])

    def test_the_backup_root_is_not_exported(self):
        # vzdumpの保存先をゲストに見せない。共有するのは game1-saves だけ。
        paths = [item['path'] for item in DEFAULTS['pve_bulk_storage_exports']]
        self.assertNotIn(DEFAULTS['pve_bulk_storage_backup_dir'], paths)

    def test_it_creates_the_backup_directories(self):
        targets = [task['ansible.builtin.file']['path'] for task in TASKS
                   if 'ansible.builtin.file' in task
                   and task['ansible.builtin.file']['state'] == 'directory']
        self.assertIn('{{ pve_bulk_storage_backup_dir }}', targets)
        self.assertIn('{{ pve_bulk_storage_game1_saves_dir }}', targets)

    def task_names(self):
        return [task.get('name', '') for task in TASKS]

    def initialization_block(self):
        return [task for task in TASKS if 'block' in task][0]

    def test_initialization_needs_an_explicit_request(self):
        names = self.task_names()
        self.assertIn('Refuse to initialize without an explicit request', names)
        self.assertIn('Note whether the partition already has a filesystem', names)
        before = names.index('Refuse to initialize without an explicit request')
        self.assertLess(names.index('Note whether the partition already has a filesystem'), before)
        self.assertLess(before, names.index('Initialize the bulk disk'))

    def test_initialization_runs_only_without_a_filesystem(self):
        block = self.initialization_block()
        self.assertIn('not pve_bulk_storage_has_fs', block['when'])
        commands = [task['ansible.builtin.command']['argv'][0]
                    for task in block['block'] if 'ansible.builtin.command' in task]
        self.assertEqual(commands[:1], ['wipefs'])
        self.assertIn('sgdisk', commands)
        self.assertIn('mkfs.ext4', commands)

    def test_the_uuid_is_checked_before_writing_fstab(self):
        names = self.task_names()
        self.assertIn('Require a filesystem UUID before writing fstab', names)
        self.assertLess(names.index('Require a filesystem UUID before writing fstab'),
                        names.index('Mount the bulk disk at boot'))

    def test_the_exports_are_reloaded_on_change(self):
        template = [task for task in TASKS if 'ansible.builtin.template' in task][0]
        self.assertEqual(template['notify'], 'Re-export the shares')
        handlers = yaml.safe_load((ROLE / 'handlers/main.yml').read_text(encoding='utf-8'))
        argv = [handler['ansible.builtin.command']['argv']
                for handler in handlers if 'ansible.builtin.command' in handler][0]
        self.assertEqual(argv, ['exportfs', '-ra'])

    def test_the_nfs_server_is_enabled(self):
        service = [task for task in TASKS if 'ansible.builtin.service' in task][0]
        self.assertEqual(service['ansible.builtin.service']['name'], 'nfs-kernel-server')
        self.assertTrue(service['ansible.builtin.service']['enabled'])

    def test_the_export_template_has_one_line_per_share(self):
        text = (ROLE / 'templates/bulk.exports.j2').read_text(encoding='utf-8')
        self.assertIn('{% for export in pve_bulk_storage_exports %}', text)
        self.assertIn('{{ export.path }} {{ export.clients }}({{ export.options }})', text)

    def test_the_playbook_runs_the_role_on_the_pve_host(self):
        plays = yaml.safe_load(read(PLAYBOOK))
        self.assertEqual(plays[0]['hosts'], 'pve')
        self.assertTrue(plays[0]['become'])
        self.assertEqual(plays[0]['roles'], ['pve_bulk_storage'])


class MediaBaseTests(unittest.TestCase):
    def setUp(self):
        self.text = read(MEDIA_BASE)
        self.tasks = yaml.safe_load(self.text)[0]['tasks']

    def test_it_installs_the_nfs_client(self):
        packages = [task['ansible.builtin.apt']['name'] for task in self.tasks
                    if 'ansible.builtin.apt' in task]
        self.assertIn('nfs-common', packages)

    def test_it_mounts_the_host_share_at_the_library_root(self):
        task = [task for task in self.tasks
                if task.get('name') == 'Mount the shared library at boot'][0]
        line = task['ansible.builtin.lineinfile']['line']
        for fragment in ('bulk_storage_server', 'bulk_storage_media_path',
                         'library_root', 'nfs4', 'bulk_storage_mount_opts'):
            self.assertIn(fragment, line)
        self.assertIn('mountpoint', self.text)

    def test_docker_will_not_start_without_the_library(self):
        task = [task for task in self.tasks
                if task.get('name') == 'Require the shared library before Docker starts'][0]
        content = task['ansible.builtin.copy']['content']
        self.assertIn('RequiresMountsFor={{ library_root }}', content)
        self.assertIn('20-media-library.conf', task['ansible.builtin.copy']['dest'])

    def test_an_added_mount_restarts_docker(self):
        task = [task for task in self.tasks
                if task.get('name') == 'Mount the shared library now'][0]
        self.assertEqual(task['notify'], 'Restart Docker to pick up the shared library')
        handlers = yaml.safe_load(self.text)[0]['handlers']
        restart = [handler for handler in handlers if handler.get('name') == task['notify']][0]
        self.assertEqual(restart['ansible.builtin.systemd_service']['state'], 'restarted')

    def test_the_group_vars_point_at_the_host_export(self):
        values = yaml.safe_load(read(GROUP_VARS))
        self.assertEqual(values['bulk_storage_server'], '192.168.10.10')
        self.assertEqual(values['bulk_storage_media_path'], '/srv/bulk/media')
        self.assertIn('_netdev', values['bulk_storage_mount_opts'])
        self.assertIn('nofail', values['bulk_storage_mount_opts'])


class DocumentationTests(unittest.TestCase):
    def test_the_page_exists_and_covers_the_risk(self):
        text = read(DOC)
        for fragment in ('USB3', 'all_squash', 'RequiresMountsFor',
                         'pve_bulk_storage_initialize', 'usb-storage.quirks'):
            self.assertIn(fragment, text)

    def test_the_game1_runbook_keeps_the_rom_library_read_only(self):
        text = read(DOC)
        self.assertIn('192.168.10.10:/srv/bulk/roms', text)
        self.assertIn('/romm/library:ro', text)

    def test_the_site_navigation_links_the_page(self):
        self.assertIn('operations/bulk-storage.md', read(MKDOCS))

    def test_the_disk_page_points_to_the_shared_storage(self):
        self.assertIn('bulk-storage.md', read(ROOT / 'docs/operations/disk.md'))


class SyntaxTests(unittest.TestCase):
    def test_the_host_playbook_parses(self):
        result = syntax_check(PLAYBOOK, 'platform/ansible/pve.ini')
        self.assertEqual(result.returncode, 0,
                         f'{PLAYBOOK.name} did not parse:\n{result.stdout}\n{result.stderr}')


if __name__ == '__main__':
    unittest.main()
