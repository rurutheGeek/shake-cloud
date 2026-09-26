"""Guard the LocalSend sender used by the Nextcloud "send" action.

The hub on media-01 only receives; this sender implements the v2 client half
(discover -> prepare-upload -> upload) so Nextcloud can send files to another
device's LocalSend app.
"""
import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import unittest

import yaml

from support import read

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'stacks/localsend-send/localsend_send.py'
STACK = ROOT / 'stacks/localsend-send'
PLAYBOOK = ROOT / 'platform/ansible/media-nextcloud.yml'
MEDIA_PLAYBOOK = ROOT / 'platform/ansible/media-localsend.yml'
GROUP_VARS = ROOT / 'platform/ansible/group_vars/media.yml'
SOPS_EXAMPLE = ROOT / 'platform/sops/localsend-send.sops.yaml.example'



spec = importlib.util.spec_from_file_location('localsend_send', SOURCE)
sender = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sender)


class PrepareTests(unittest.TestCase):
    def test_the_metadata_carries_one_file(self):
        body, file_id = sender.prepare_body('media-01', 'FP', 53200, 'photo.jpg',
                                            123, '2026-09-13T00:00:00Z')
        self.assertEqual(file_id, 'file0')
        info = body['info']
        self.assertEqual(info['alias'], 'media-01')
        self.assertEqual(info['fingerprint'], 'FP')
        self.assertEqual(info['protocol'], 'http')
        self.assertFalse(info['download'])
        entry = body['files'][file_id]
        self.assertEqual(entry['fileName'], 'photo.jpg')
        self.assertEqual(entry['size'], 123)
        self.assertEqual(entry['fileType'], 'image/jpeg')

    def test_the_ticket_needs_a_session_and_a_token(self):
        payload = {'sessionId': 's', 'files': {'file0': 't'}}
        self.assertEqual(sender.parse_upload_ticket(payload, 'file0'), ('s', 't'))
        with self.assertRaises(ValueError):
            sender.parse_upload_ticket({'sessionId': 's', 'files': {}}, 'file0')

    def test_the_address_defaults_to_https(self):
        self.assertEqual(sender.device_address(
            {'protocol': 'https', 'port': 53317}, '192.0.2.5'),
            ('https', '192.0.2.5', 53317))
        self.assertEqual(sender.device_address(
            {'protocol': 'http'}, '192.0.2.5'), ('http', '192.0.2.5', 53317))
        self.assertEqual(sender.device_address({}, '192.0.2.5'),
                         ('https', '192.0.2.5', 53317))

    def test_our_own_fingerprint_is_ignored(self):
        self.assertTrue(sender.device_is_self({'fingerprint': 'ab'}, 'AB'))
        self.assertFalse(sender.device_is_self({'fingerprint': 'cd'}, 'AB'))


class FakeReceiver(BaseHTTPRequestHandler):
    received = {}

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length)
        if self.path.startswith('/api/localsend/v2/prepare-upload'):
            FakeReceiver.received['prepare'] = json.loads(body)
            payload = json.dumps(
                {'sessionId': 'sess', 'files': {'file0': 'tok'}}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif self.path.startswith('/api/localsend/v2/upload'):
            FakeReceiver.received['upload_url'] = self.path
            FakeReceiver.received['content'] = body
            self.send_response(200)
            self.send_header('Content-Length', '0')
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


class SendTests(unittest.TestCase):
    def test_the_upload_flow_reaches_the_receiver(self):
        FakeReceiver.received = {}
        server = ThreadingHTTPServer(('127.0.0.1', 0), FakeReceiver)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            device = {'alias': 'phone', 'fingerprint': 'dev',
                      'protocol': 'http', 'port': server.server_address[1]}
            result = sender.send_file(device, '127.0.0.1', 'note.txt', b'hello',
                                      'media-01', 'FP', 53200, timeout=10)
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(result['status'], 'sent')
        prepare = FakeReceiver.received['prepare']
        self.assertEqual(prepare['files']['file0']['fileName'], 'note.txt')
        self.assertIn('sessionId=sess', FakeReceiver.received['upload_url'])
        self.assertIn('token=tok', FakeReceiver.received['upload_url'])
        self.assertEqual(FakeReceiver.received['content'], b'hello')

    def test_a_rejected_transfer_is_reported(self):
        class Rejecting(FakeReceiver):
            def do_POST(self):
                self.send_response(403)
                self.send_header('Content-Length', '0')
                self.end_headers()

        server = ThreadingHTTPServer(('127.0.0.1', 0), Rejecting)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            device = {'alias': 'phone', 'fingerprint': 'dev',
                      'protocol': 'http', 'port': server.server_address[1]}
            with self.assertRaises(RuntimeError):
                sender.send_file(device, '127.0.0.1', 'note.txt', b'hello',
                                 'media-01', 'FP', 53200, timeout=10)
        finally:
            server.shutdown()
            server.server_close()


class MigrationTests(unittest.TestCase):
    def test_the_app_is_no_longer_vendored_here(self):
        # アプリ本体は公開リポジトリ rurutheGeek/nextcloud-localsend が正本。
        self.assertFalse((ROOT / 'stacks/media/nextcloud/apps/shake_localsend').exists())

    def test_the_release_is_pinned_in_group_vars(self):
        group = yaml.safe_load(read(GROUP_VARS))
        pinned = {app['name']: app for app in group['nextcloud_custom_apps']}
        self.assertEqual(pinned['localsend_share']['repo'],
                         'rurutheGeek/nextcloud-localsend')
        self.assertRegex(pinned['localsend_share']['version'], r'^\d+\.\d+\.\d+$')

    def test_the_retired_app_is_removed(self):
        group = yaml.safe_load(read(GROUP_VARS))
        self.assertIn('shake_localsend', group['nextcloud_retired_apps'])
        self.assertIn('remove-apps', read(PLAYBOOK))

    def test_manage_py_points_the_app_at_the_relay(self):
        manage = read(ROOT / 'stacks/media/nextcloud/manage.py')
        self.assertIn("config_app('localsend_share'", manage)
        self.assertIn("('relay_url', os.environ['SEND_API_URL'])", manage)
        self.assertIn("('relay_token', os.environ['SEND_API_TOKEN'])", manage)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.play = yaml.safe_load(read(PLAYBOOK))[0]
        self.tasks = self.play['tasks']
        self.media_tasks = yaml.safe_load(read(MEDIA_PLAYBOOK))[0]['tasks']

    def task(self, name):
        return next(task for task in self.tasks if task['name'] == name)

    def test_the_custom_apps_are_installed_from_pinned_releases(self):
        commands = [task['ansible.builtin.command']['argv'] for task in self.tasks
                    if 'ansible.builtin.command' in task]
        custom = [argv for argv in commands if len(argv) > 2 and argv[2] == 'custom-apps']
        self.assertEqual(len(custom), 1)
        self.assertIn('--repos', custom[0])
        self.assertIn('--versions', custom[0])

    def test_the_app_list_includes_the_send_app(self):
        commands = [task['ansible.builtin.command']['argv'] for task in self.tasks
                    if 'ansible.builtin.command' in task]
        apps = [argv for argv in commands if len(argv) > 2 and argv[2] == 'apps']
        self.assertEqual(len(apps), 1)
        self.assertIn("localsend_share", str(apps[0]))

    def test_the_relay_url_and_token_are_configured(self):
        task = self.task('Point the localsend_share app at the media-01 relay')
        self.assertIn('SEND_API_URL', task['environment'])
        self.assertIn('SEND_API_TOKEN', task['environment'])
        self.assertTrue(task['no_log'])

    def test_the_play_reads_the_token_from_sops(self):
        readers = [task for task in self.tasks
                   if 'ansible.builtin.command' in task
                   and 'localsend-send.sops.yaml'
                   in str(task['ansible.builtin.command']['argv'])]
        self.assertEqual(len(readers), 1)
        self.assertTrue(readers[0]['no_log'])

    def test_the_api_url_matches_the_service_port(self):
        group = yaml.safe_load(read(GROUP_VARS))
        self.assertEqual(group['nextcloud_localsend_api_url'],
                         'http://192.168.10.101:53200')

    def test_the_service_is_deployed_next_to_the_receiver(self):
        names = [task['name'] for task in self.media_tasks]
        for name in ('Read the LocalSend send credentials',
                     'Install the LocalSend sender',
                     'Write the LocalSend send environment',
                     'Install the LocalSend send unit',
                     'Enable and start the LocalSend sender'):
            self.assertIn(name, names)
        unit = read(STACK / 'localsend-send.service.j2')
        self.assertIn(
            'ExecStart=/usr/bin/python3 {{ localsend_send_dir }}/localsend_send.py', unit)
        self.assertIn(
            'EnvironmentFile={{ localsend_send_dir }}/localsend-send.env', unit)

    def test_the_sops_example_documents_the_credentials(self):
        example = read(SOPS_EXAMPLE)
        self.assertIn('LOCALSEND_SEND_TOKEN:', example)
        self.assertIn('LOCALSEND_SEND_FINGERPRINT:', example)


if __name__ == '__main__':
    unittest.main()
