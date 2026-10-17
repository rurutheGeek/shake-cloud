"""The external check on negitoroserver notifies like the monitoring stack does."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'platform/ansible/roles/public_monitor/templates/public-monitor.sh.j2'


class PublicMonitorTests(unittest.TestCase):
    def setUp(self):
        self.script = SCRIPT.read_text(encoding='utf-8')

    def test_a_short_outage_does_not_notify(self):
        # 1 分ごとの timer で 10 回続いたら。配線替えの抜き差しで鳴らさない。
        self.assertIn('THRESHOLD=10\n', self.script)
        timer = (SCRIPT.parent / 'public-monitor.timer.j2').read_text(encoding='utf-8')
        self.assertIn('OnUnitActiveSec=1min', timer)

    def test_the_message_has_the_same_shape_as_the_stack(self):
        self.assertIn('"embeds"', self.script)
        self.assertIn('🔴 緊急｜', self.script)
        self.assertIn('✅ 直った｜', self.script)
        self.assertIn('すること：', self.script)

    def test_times_are_in_japan(self):
        self.assertIn('export TZ=Asia/Tokyo', self.script)


if __name__ == '__main__':
    unittest.main()
