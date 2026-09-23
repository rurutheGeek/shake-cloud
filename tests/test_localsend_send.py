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
APP = ROOT / 'stacks/media/nextcloud/apps/shake_localsend'
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


class AppTests(unittest.TestCase):
    def test_info_declares_the_app_and_the_namespace(self):
        info = read(APP / 'appinfo/info.xml')
        application = read(APP / 'lib/AppInfo/Application.php')
        self.assertIn('<id>shake_localsend</id>', info)
        self.assertIn('<namespace>ShakeLocalSend</namespace>', info)
        self.assertIn('namespace OCA\\ShakeLocalSend\\AppInfo;', application)
        self.assertIn('<nextcloud min-version="30" max-version="33"/>', info)

    def test_the_files_script_is_registered(self):
        app = read(APP / 'lib/AppInfo/Application.php')
        listener = read(APP / 'lib/Listener/LoadAdditionalScripts.php')
        self.assertIn('LoadAdditionalScriptsEvent::class', app)
        self.assertIn("Util::addInitScript('shake_localsend', 'localsend')", listener)

    def test_the_controller_proxies_devices_and_send(self):
        controller = read(APP / 'lib/Controller/SendController.php')
        self.assertIn("#[FrontpageRoute(verb: 'GET', url: '/devices')]", controller)
        self.assertIn("#[FrontpageRoute(verb: 'POST', url: '/send')]", controller)
        self.assertIn("getAppValue('shake_localsend', 'send_api_url'", controller)
        self.assertIn("getAppValue('shake_localsend', 'send_api_token'", controller)
        self.assertIn("'X-Send-To' => $fingerprint", controller)
        self.assertIn("'Bearer '", controller)

    def test_the_action_uses_the_files_context_signature(self):
        source = read(APP / 'src/localsend.js')
        self.assertIn('enabled: ({ nodes })', source)
        self.assertIn('exec: async ({ nodes })', source)

    def test_non_admins_may_use_the_send_routes(self):
        # AppFramework は既定で管理者のみ。付けないと一般ユーザーは403になる（実測）。
        controller = read(APP / 'lib/Controller/SendController.php')
        self.assertIn('use OCP\\AppFramework\\Http\\Attribute\\NoAdminRequired;', controller)
        self.assertEqual(controller.count('#[NoAdminRequired]'), 2)

    def test_the_bundle_registers_the_send_action(self):
        bundle = read(APP / 'js/localsend.js')
        self.assertIn('registerFileAction', bundle)
        self.assertIn('/apps/shake_localsend/devices', bundle)
        self.assertIn('/apps/shake_localsend/send', bundle)
        self.assertIn('shake-localsend', bundle)
        # コアと同じ @nextcloud/files v4 のグローバルレジストリへ登録する。
        self.assertIn('_nc_files_scope', bundle)
        self.assertIn('register:action', bundle)
        package = json.loads(read(APP / 'package.json'))
        self.assertNotIn('@nextcloud/dialogs', package['dependencies'])


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.play = yaml.safe_load(read(PLAYBOOK))[0]
        self.tasks = self.play['tasks']
        self.media_tasks = yaml.safe_load(read(MEDIA_PLAYBOOK))[0]['tasks']

    def task(self, name):
        return next(task for task in self.tasks if task['name'] == name)

    def test_the_app_is_copied_into_the_nextcloud_html_volume(self):
        task = self.task('Copy the LocalSend send app')
        self.assertIn('apps/shake_localsend/',
                      task['ansible.builtin.copy']['src'])
        self.assertIn('custom_apps/shake_localsend',
                      task['ansible.builtin.copy']['dest'])

    def test_the_app_list_includes_the_send_app(self):
        apps = [task for task in self.tasks if '--apps' in str(task)]
        self.assertEqual(len(apps), 1)
        self.assertIn("+ ['shake_print', 'shake_localsend', 'shake_tags']",
                      str(apps[0]['ansible.builtin.command']['argv']))

    def test_the_relay_url_and_token_are_configured(self):
        task = self.task('Point the LocalSend send app at the media-01 sender')
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
