"""Check the trim script's parsing and plan without touching real hardware.

The script decides what to delete on machines that hold services. A parse that
silently returns 0 for an unknown unit, or a plan that removes tagged images
without being asked, would be worse than no script at all.
"""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('trim_vms', ROOT / 'tools/trim-vms.py')
trim = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trim)


class ParseSizeTests(unittest.TestCase):
    def test_docker_reports_in_1000s(self):
        self.assertEqual(trim.parse_size('10.53GB (81%)'), int(10.53 * 1000 ** 3))
        self.assertEqual(trim.parse_size('77.82kB'), int(77.82 * 1000))

    def test_systemd_reports_in_1024s(self):
        self.assertEqual(trim.parse_size('111.6M', base=1024), int(111.6 * 1024 ** 2))

    def test_zero_and_empty_are_zero(self):
        self.assertEqual(trim.parse_size('0B'), 0)
        self.assertEqual(trim.parse_size(''), 0)

    def test_an_unknown_unit_is_not_a_silent_number(self):
        self.assertEqual(trim.parse_size('5XB'), 0)


class DockerReclaimableTests(unittest.TestCase):
    def test_reads_the_reclaimable_column(self):
        output = (
            '{"Type":"Images","Reclaimable":"7.98GB (70%)","Size":"11.25GB"}\n'
            '{"Type":"Build Cache","Reclaimable":"2.161GB","Size":"2.314GB"}\n'
            'not json\n'
        )
        seen = trim.docker_reclaimable(output)
        self.assertEqual(seen['Images'], int(7.98 * 1000 ** 3))
        self.assertEqual(seen['Build Cache'], int(2.161 * 1000 ** 3))

    def test_an_empty_report_is_empty(self):
        self.assertEqual(trim.docker_reclaimable(''), {})


class JournalBytesTests(unittest.TestCase):
    def test_reads_the_size_out_of_the_sentence(self):
        text = 'Archived and active journals take up 111.6M in the file system.'
        self.assertEqual(trim.journal_bytes(text), int(111.6 * 1024 ** 2))

    def test_no_number_is_zero(self):
        self.assertEqual(trim.journal_bytes('no journals'), 0)


class PlanTests(unittest.TestCase):
    def test_default_plan_touches_only_cache(self):
        plan = trim.plan_commands({'docker': True, 'apt': True}, {})
        self.assertEqual(plan, ['sudo docker builder prune -f', 'sudo apt-get clean'])

    def test_images_are_opt_in(self):
        plan = trim.plan_commands({'docker': True, 'apt': False}, {'images': True})
        self.assertIn('sudo docker image prune -f', plan)

    def test_all_images_replaces_the_dangling_only_prune(self):
        plan = trim.plan_commands({'docker': True, 'apt': False}, {'images': False, 'all_images': True})
        self.assertEqual(plan, ['sudo docker builder prune -f', 'sudo docker image prune -af'])

    def test_journals_are_only_vacuumed_when_asked(self):
        self.assertNotIn('sudo journalctl --vacuum-size=100M',
                         trim.plan_commands({'docker': False, 'apt': True}, {}))
        self.assertIn('sudo journalctl --vacuum-size=100M',
                      trim.plan_commands({'docker': False, 'apt': True}, {'journal_max': '100M'}))

    def test_a_host_without_docker_or_apt_gets_nothing(self):
        self.assertEqual(trim.plan_commands({}, {}), [])


class SelectTests(unittest.TestCase):
    def test_the_default_is_the_management_vms(self):
        names = [vm['name'] for vm in trim.select_vms(None, False)]
        self.assertIn('cloud-01', names)
        self.assertNotIn('dev-a', names)

    def test_dev_vms_are_opt_in(self):
        names = [vm['name'] for vm in trim.select_vms(None, True)]
        self.assertIn('dev-a', names)
        self.assertIn('dev-b', names)

    def test_naming_a_dev_vm_is_enough(self):
        names = [vm['name'] for vm in trim.select_vms('dev-a', False)]
        self.assertEqual(names, ['dev-a'])

    def test_an_unknown_name_stops_the_run(self):
        with self.assertRaises(SystemExit):
            trim.select_vms('cloud-99', False)


class SizeTextTests(unittest.TestCase):
    def test_disk_sizes_are_1024_based(self):
        self.assertEqual(trim.size_text(1024 ** 3), '1.0GiB')

    def test_docker_sizes_are_1000_based(self):
        self.assertEqual(trim.docker_size_text(1000 ** 3), '1.0GB')


if __name__ == '__main__':
    unittest.main()
