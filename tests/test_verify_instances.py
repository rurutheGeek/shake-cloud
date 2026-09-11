"""Check the end-to-end script's judgement without touching real hardware.

The script exists to catch a broken seed ISO or a terminate that leaks
resources. A check that reads a leftover VM, or a guest that never answered, as
success would be worse than no check at all.
"""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('verify_instances', ROOT / 'tools/verify-instances.py')
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


def good():
    return {
        'state': 'running', 'state_reason': '', 'address': '192.168.10.100/24',
        'vm': [{'vmid': 5000}], 'seed_iso': ['cloud-images:iso/shakecloud-i-1.iso'],
        'netbox_addresses': [('192.168.10.100/24', 'web')],
        'logged_in': True, 'guest_address': '192.168.10.100/24',
        'final_state': 'terminated',
        'leftover_vms': [], 'leftover_isos': [], 'leftover_disks': [], 'leftover_addresses': [],
    }


class JudgeTests(unittest.TestCase):
    def test_a_clean_run_passes(self):
        self.assertEqual(verify.judge(good()), [])

    def test_every_kind_of_leftover_fails(self):
        for name in ('leftover_vms', 'leftover_isos', 'leftover_disks', 'leftover_addresses'):
            seen = good()
            seen[name] = ['something']
            self.assertTrue(verify.judge(seen), name)

    def test_a_guest_that_never_answered_fails(self):
        seen = good()
        seen['logged_in'] = False
        problems = verify.judge(seen)
        self.assertTrue(any('cloud-init' in problem for problem in problems), problems)

    def test_the_wrong_address_inside_the_guest_fails(self):
        # The address is written into the seed ISO's network-config; a guest with
        # a different one means DHCP answered instead.
        seen = good()
        seen['guest_address'] = '192.168.10.55/24'
        self.assertTrue(verify.judge(seen))

    def test_a_launch_that_ended_terminated_fails(self):
        seen = good()
        seen['state'] = 'terminated'
        seen['state_reason'] = 'Server.InternalError: storage full'
        problems = verify.judge(seen)
        self.assertTrue(any('never reached running' in problem for problem in problems), problems)

    def test_missing_backend_objects_fail(self):
        for name in ('vm', 'seed_iso', 'netbox_addresses', 'address'):
            seen = good()
            seen[name] = [] if name != 'address' else ''
            self.assertTrue(verify.judge(seen), name)

    def test_an_instance_left_behind_fails(self):
        seen = good()
        seen['final_state'] = 'shutting-down'
        self.assertTrue(verify.judge(seen))


if __name__ == '__main__':
    unittest.main()
