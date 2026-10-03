"""配備スタック（apps-01）の静的な検査。

壊れると: ホストネットワークや秘密値の受け渡しが崩れ、HA と同じホストで
ライブ配信が動かなくなる。
"""

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/eufy-leo-rtc'
PLAY = ROOT / 'platform/ansible/eufy-leo-rtc.yml'


class StackTests(unittest.TestCase):
    def setUp(self):
        self.compose = yaml.safe_load((STACK / 'compose.yaml').read_text(encoding='utf-8'))

    def test_containers_use_host_networking_and_pinned_images(self):
        services = self.compose['services']
        self.assertEqual(set(services), {'mediamtx', 'leo-live'})
        for name, service in services.items():
            self.assertEqual(service['network_mode'], 'host', name)
            self.assertEqual(service['restart'], 'unless-stopped', name)
        self.assertRegex(services['mediamtx']['image'], r'bluenviron/mediamtx:1\.9\.3@sha256:[0-9a-f]{64}')
        self.assertRegex((STACK / 'Dockerfile').read_text(encoding='utf-8'),
                         r'FROM python:3\.13-slim[\w.-]*@sha256:[0-9a-f]{64}')

    def test_rtsp_and_snapshot_are_only_on_the_ha_gateway(self):
        mediamtx = yaml.safe_load((STACK / 'mediamtx.yml').read_text(encoding='utf-8'))
        self.assertEqual(mediamtx['rtspAddress'], '172.31.254.1:8554')
        self.assertEqual(mediamtx['logFile'], '/state/mediamtx.log')
        live = self.compose['services']['leo-live']
        self.assertEqual(live['environment']['LEO_MJPEG_BIND'], '172.31.254.1')
        self.assertEqual(live['environment']['LEO_RTSP'], 'rtsp://172.31.254.1:8554/eufy')

    def test_credentials_come_from_the_environment_not_the_image(self):
        live = self.compose['services']['leo-live']
        for key in ('EUFY_SN', 'EUFY_DID', 'EUFY_LICENSE', 'EUFY_ACCOUNT'):
            self.assertIn(key, live['environment'])
        dockerfile = (STACK / 'Dockerfile').read_text(encoding='utf-8')
        self.assertNotIn('EUFY_SN', dockerfile)
        self.assertNotIn('.env', dockerfile)


class PlaybookTests(unittest.TestCase):
    def test_playbook_deploys_the_stack_with_sops_credentials(self):
        play = yaml.safe_load(PLAY.read_text(encoding='utf-8'))[0]
        self.assertEqual(play['hosts'], 'apps')
        self.assertEqual(play['vars']['leo_project_dir'], '/opt/eufy-leo-rtc')
        self.assertEqual(play['vars']['leo_keys'],
                         ['EUFY_SN', 'EUFY_DID', 'EUFY_LICENSE', 'EUFY_ACCOUNT', 'EUFY_CONTACT'])
        self.assertIn('eufy-security.sops.yaml', play['vars']['leo_sops_file'])


if __name__ == '__main__':
    unittest.main()
