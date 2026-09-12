"""Check the volume/security-group end-to-end script's judgement without hardware.

The script exists to catch a security group that does not filter, a volume the
guest never sees, or a delete that leaks. A check that reads a blocked port as
open, or a leftover disk as cleaned up, would be worse than no check at all.
"""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('verify_volumes', ROOT / 'tools/verify-volumes.py')
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


def good():
    return {
        'state': 'running', 'state_reason': '', 'address': '192.168.10.100',
        'logged_in': True,
        'firewall_in_sync': True, 'ssh_open': True,
        'probe_blocked': True, 'probe_allowed': True, 'probe_blocked_again': True,
        'volume_state_created': 'available', 'serial': 'vol0123456789abcdef0',
        'device_seen': True, 'volume_state_detached': 'available', 'volume_state_deleted': 'deleted',
        'final_state': 'terminated',
        'leftover_vms': [], 'leftover_holder_disks': [], 'leftover_addresses': [],
    }


class JudgeTests(unittest.TestCase):
    def test_a_clean_run_passes(self):
        self.assertEqual(verify.judge(good()), [])

    def test_a_security_group_that_does_not_filter_fails(self):
        seen = good()
        seen['probe_blocked'] = False
        self.assertTrue(any('does not allow' in problem for problem in verify.judge(seen)))

    def test_a_rule_that_never_opens_the_port_fails(self):
        seen = good()
        seen['probe_allowed'] = False
        self.assertTrue(verify.judge(seen))

    def test_a_rule_that_never_closes_the_port_again_fails(self):
        seen = good()
        seen['probe_blocked_again'] = False
        self.assertTrue(verify.judge(seen))

    def test_a_firewall_that_stays_applying_fails(self):
        seen = good()
        seen['firewall_in_sync'] = False
        self.assertTrue(any('in-sync' in problem for problem in verify.judge(seen)))

    def test_ssh_lost_after_applying_a_group_fails(self):
        seen = good()
        seen['ssh_open'] = False
        self.assertTrue(verify.judge(seen))

    def test_a_volume_not_visible_in_the_guest_fails(self):
        seen = good()
        seen['device_seen'] = False
        self.assertTrue(any('virtio-' in problem for problem in verify.judge(seen)))

    def test_each_volume_state_transition_is_checked(self):
        for name, want in (('volume_state_created', 'available'),
                           ('volume_state_detached', 'available'),
                           ('volume_state_deleted', 'deleted')):
            seen = good()
            seen[name] = 'error'
            self.assertTrue(verify.judge(seen), name)

    def test_a_launch_that_ended_terminated_fails(self):
        seen = good()
        seen['state'] = 'terminated'
        seen['state_reason'] = 'Server.InternalError: no storage'
        self.assertTrue(any('never reached running' in problem for problem in verify.judge(seen)))

    def test_a_guest_that_never_answered_fails(self):
        seen = good()
        seen['logged_in'] = False
        self.assertTrue(any('cloud-init' in problem for problem in verify.judge(seen)))

    def test_every_kind_of_leftover_fails(self):
        for name in ('leftover_vms', 'leftover_holder_disks', 'leftover_addresses'):
            seen = good()
            seen[name] = ['something']
            self.assertTrue(verify.judge(seen), name)

    def test_an_instance_left_behind_fails(self):
        seen = good()
        seen['final_state'] = 'shutting-down'
        self.assertTrue(verify.judge(seen))


if __name__ == '__main__':
    unittest.main()
