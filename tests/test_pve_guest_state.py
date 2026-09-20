"""Check that the boot-time guest restore follows the last real power state.

The snapshot runs every minute, but a host hang arrives seconds after a stop
(game1's iGPU passthrough does exactly that), so the saved set can still say
"running" for a guest the operator had just stopped. restore() therefore reads
the Proxmox task log and skips those. These pin that behaviour, because getting
it wrong silently starts a VM nobody asked for -- or leaves one down after a
power cut.
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'platform/ansible/roles/pve_guest_state/files/shakecloud-guests'

SNAPSHOT_TIME = 1_700_000_000


def load_script():
    """Import the hook script, which has no .py suffix."""
    loader = importlib.machinery.SourceFileLoader('shakecloud_guests', str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def upid(action, vmid, started):
    """One Proxmox task log line; the 5th field is the hex start time."""
    return (f'UPID:apextox:0000ABCD:00001234:{started:08X}:{action}:{vmid}:root@pam: '
            f'{started + 1:08X} OK')


class RestoreTest(unittest.TestCase):
    def setUp(self):
        self.module = load_script()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.state = base / 'guests-running'
        self.index = base / 'index'
        self.index.write_text('')
        self.module.STATE = self.state
        self.module.TASK_LOGS = (self.index,)

    def given(self, saved, tasks=(), up=()):
        self.state.write_text('\n'.join(saved) + '\n')
        os.utime(self.state, (SNAPSHOT_TIME, SNAPSHOT_TIME))
        self.index.write_text('\n'.join(tasks) + '\n')
        self.module.running = lambda: list(up)

    def restore(self):
        """Run restore() and return the VMIDs it asked Proxmox to start."""
        started = []

        def fake_run(argv, **kwargs):
            started.append(argv[2])
            return mock.Mock(returncode=0, stderr='')

        with mock.patch.object(self.module.subprocess, 'run', side_effect=fake_run):
            self.module.restore()
        return started

    def test_skips_a_guest_stopped_after_the_snapshot(self):
        # The hang that loses the next snapshot is exactly this case.
        self.given(['100', '401'], tasks=[upid('qmstop', '100', SNAPSHOT_TIME + 5)])
        self.assertEqual(self.restore(), ['401'])

    def test_a_shutdown_counts_as_a_stop(self):
        self.given(['100'], tasks=[upid('qmshutdown', '100', SNAPSHOT_TIME + 5)])
        self.assertEqual(self.restore(), [])

    def test_a_guest_stopped_then_started_again_is_restored(self):
        self.given(['100'], tasks=[
            upid('qmstop', '100', SNAPSHOT_TIME + 5),
            upid('qmstart', '100', SNAPSHOT_TIME + 30),
        ])
        self.assertEqual(self.restore(), ['100'])

    def test_a_stop_before_the_snapshot_does_not_block_the_restore(self):
        # The snapshot already saw the result of that stop.
        self.given(['100'], tasks=[upid('qmstop', '100', SNAPSHOT_TIME - 60)])
        self.assertEqual(self.restore(), ['100'])

    def test_a_guest_already_up_is_left_alone(self):
        self.given(['100', '401'], up=['100'])
        self.assertEqual(self.restore(), ['401'])

    def test_a_stop_of_another_guest_is_not_confused(self):
        self.given(['100'], tasks=[upid('qmstop', '401', SNAPSHOT_TIME + 5)])
        self.assertEqual(self.restore(), ['100'])

    def test_unreadable_task_log_still_restores(self):
        # A missing task log must not strand the guests after a power cut.
        self.given(['100'])
        self.module.TASK_LOGS = (Path(self.tmp.name) / 'absent',)
        self.assertEqual(self.restore(), ['100'])

    def test_no_saved_state_starts_nothing(self):
        self.module.running = lambda: []
        self.assertEqual(self.restore(), [])


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.module = load_script()

    def test_reads_the_hex_start_time_and_action(self):
        tmp = tempfile.NamedTemporaryFile('w', suffix='.log', delete=False)
        self.addCleanup(os.unlink, tmp.name)
        tmp.write(upid('qmstop', '100', SNAPSHOT_TIME + 5) + '\n')
        tmp.write(upid('vncproxy', '100', SNAPSHOT_TIME + 9) + '\n')
        tmp.close()
        self.module.TASK_LOGS = (Path(tmp.name),)
        # vncproxy is not a power task, so the stop stays newest.
        self.assertEqual(self.module.last_power_action(SNAPSHOT_TIME), {'100': 'qmstop'})


if __name__ == '__main__':
    unittest.main()
