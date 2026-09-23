"""Guard the weekly Tier1 backups and the game1 saves path.

The backup job is the only copy of the cloud ledger, Authentik and Home
Assistant configuration. The test also pins the two safety properties that
are easy to lose in an edit: the job never includes game1 (approx. 237G of
re-downloadable games and models) and the role refuses to write when the
bulk disk is not mounted (otherwise vzdump fills the root filesystem).
"""
import unittest
from pathlib import Path

import yaml

from support import read, role_task, syntax_check

ROOT = Path(__file__).resolve().parents[1]
ANSIBLE = ROOT / 'platform/ansible'
ROLE = ANSIBLE / 'roles/pve_backup'
DEFAULTS = yaml.safe_load((ROLE / 'defaults/main.yml').read_text(encoding='utf-8'))
TASKS = yaml.safe_load((ROLE / 'tasks/main.yml').read_text(encoding='utf-8'))
PLAYBOOK = ANSIBLE / 'pve-backup.yml'
DOC = ROOT / 'docs/operations/backup.md'
MKDOCS = ROOT / 'mkdocs.yml'
SCRIPT = ROOT / 'tools/game1-saves-backup.sh'


class DefaultsTests(unittest.TestCase):
    def test_the_tier1_vmids_are_the_ones_that_cannot_be_rebuilt(self):
        self.assertEqual(DEFAULTS['pve_backup_vmids'],
                         [101, 110, 130, 140, 150, 401, 5001, 5002])

    def test_game1_is_not_backed_up_as_a_whole_vm(self):
        self.assertNotIn(100, DEFAULTS['pve_backup_vmids'])

    def test_it_backs_up_weekly_and_keeps_four_generations(self):
        self.assertEqual(DEFAULTS['pve_backup_schedule'], 'sun 06:00')
        self.assertEqual(DEFAULTS['pve_backup_keep_last'], 4)
        self.assertEqual(DEFAULTS['pve_backup_prune_arg'],
                         'keep-last={{ pve_backup_keep_last }}')

    def test_it_snapshots_with_compression(self):
        self.assertEqual(DEFAULTS['pve_backup_mode'], 'snapshot')
        self.assertEqual(DEFAULTS['pve_backup_compress'], 'zstd')

    def test_the_storage_points_at_the_bulk_disk(self):
        self.assertEqual(DEFAULTS['pve_backup_storage_id'], 'bulk-backup')
        self.assertEqual(DEFAULTS['pve_backup_storage_path'], '/srv/bulk/backups')

    def test_the_vmid_argument_is_written_in_a_stable_order(self):
        self.assertEqual(DEFAULTS['pve_backup_vmid_arg'],
                         '{{ pve_backup_vmids | sort | map("string") | join(",") }}')


class TaskTests(unittest.TestCase):
    def test_it_refuses_to_run_without_the_bulk_disk(self):
        check = role_task(TASKS, 'Find the filesystem that holds the backup path')
        self.assertEqual(check['ansible.builtin.command']['argv'][0], 'findmnt')
        guard = role_task(TASKS, 'Require the bulk disk to be mounted')['ansible.builtin.assert']['that']
        self.assertIn("pve_backup_mount.stdout | trim != '/'", guard)

    def test_it_registers_the_storage_only_when_missing(self):
        register = role_task(TASKS, 'Register the backup directory as Proxmox storage')
        self.assertIn('is not defined', register['when'])
        argv = register['ansible.builtin.command']['argv']
        self.assertEqual(argv[:4], ['pvesm', 'add', 'dir', '{{ pve_backup_storage_id }}'])
        self.assertIn('backup', argv)

    def test_it_finds_the_job_by_its_comment(self):
        find = role_task(TASKS, 'Find the tier1 backup job')
        expression = ' '.join(find['ansible.builtin.set_fact']['pve_backup_job'].split())
        self.assertIn("selectattr('comment', 'equalto', pve_backup_comment)", expression)

    def test_it_creates_the_job_with_snapshot_and_prune(self):
        create = role_task(TASKS, 'Create the weekly backup job')
        argv = create['ansible.builtin.command']['argv']
        self.assertEqual(argv[:3], ['pvesh', 'create', '/cluster/backup'])
        self.assertIn('{{ pve_backup_vmid_arg }}', argv)
        self.assertIn('{{ pve_backup_prune_arg }}', argv)
        self.assertIn('{{ pve_backup_schedule }}', argv)
        self.assertIn('is not defined', create['when'])

    def test_it_updates_the_job_when_the_declaration_changes(self):
        update = role_task(TASKS, 'Update the weekly backup job when the declaration changed')
        argv = update['ansible.builtin.command']['argv']
        self.assertEqual(argv[:3], ['pvesh', 'set', '/cluster/backup/{{ pve_backup_job.id }}'])
        conditions = ' '.join(update['when'])
        for fragment in ('vmid', 'schedule', 'compress', 'mode', 'prune-backups'):
            self.assertIn(fragment, conditions)

    def test_the_playbook_runs_the_role_on_the_pve_host(self):
        plays = yaml.safe_load(read(PLAYBOOK))
        self.assertEqual(plays[0]['hosts'], 'pve')
        self.assertTrue(plays[0]['become'])
        self.assertEqual(plays[0]['roles'], ['pve_backup'])


class Game1SavesTests(unittest.TestCase):
    def test_the_script_requires_the_nfs_mount(self):
        text = read(SCRIPT)
        self.assertIn('mountpoint -q "$DEST"', text)
        self.assertIn('/srv/game1/backup', text)

    def test_the_script_prunes_old_generations(self):
        text = read(SCRIPT)
        self.assertIn('KEEP=${KEEP:-4}', text)
        self.assertIn('tail -n +$((KEEP + 1))', text)

    def test_the_script_does_not_silently_tar_a_missing_target(self):
        text = read(SCRIPT)
        self.assertIn('存在する保存対象がありません', text)


class DocumentationTests(unittest.TestCase):
    def test_the_page_names_the_critical_secret(self):
        text = read(DOC)
        self.assertIn('keys.txt', text)
        self.assertIn('~/.config/sops/age/keys.txt', text)

    def test_the_page_states_the_single_disk_limits(self):
        text = read(DOC)
        self.assertIn('同じ筐体・単一ディスク', text)
        self.assertIn('メディア原本', text)

    def test_the_navigation_links_the_page(self):
        self.assertIn('operations/backup.md', read(MKDOCS))


class SyntaxTests(unittest.TestCase):
    def test_the_playbook_parses(self):
        result = syntax_check(PLAYBOOK, 'platform/ansible/pve.ini')
        self.assertEqual(result.returncode, 0,
                         f'{PLAYBOOK.name} did not parse:\n{result.stdout}\n{result.stderr}')


if __name__ == '__main__':
    unittest.main()
