"""Guard the read-only Gmail viewer: isolation, IMAP read-only, SSO wiring.

The mailbox also carries Authentik invitations and recovery links, so the stack
must stay loopback-only, must never mark messages as read, must never put the
app password in Git or .env, and must sit behind Forward Auth.
"""
import base64
import contextlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import urllib.error
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/mail-view'
SPEC = importlib.util.spec_from_file_location('mail_view_app', STACK / 'app.py')
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)
MANAGE_SPEC = importlib.util.spec_from_file_location('mail_view_manage', STACK / 'manage.py')
manage = importlib.util.module_from_spec(MANAGE_SPEC)
MANAGE_SPEC.loader.exec_module(manage)

CONFIG = {
    'imap_host': 'imap.gmail.com', 'imap_port': 993,
    'imap_username': 'shake.notify@gmail.com', 'imap_password': 'app-password',
    'mailbox': 'INBOX', 'message_limit': 50, 'cache_seconds': 30,
    'max_bytes': 524288, 'offset_hours': 9,
    'bind_address': '127.0.0.1', 'port': 8080,
}


class FakeIMAP:
    instance = None

    def __init__(self, *args, **kwargs):
        self.calls = []
        FakeIMAP.instance = self

    def login(self, username, password):
        self.calls.append(('login', username, password))

    def select(self, mailbox, readonly=False):
        self.calls.append(('select', mailbox, readonly))
        return 'OK', [b'1']

    def logout(self):
        self.calls.append(('logout',))


class FakeClient:
    def __init__(self, search=b'1 2 3', data=()):
        self.search = search
        self.data = data
        self.calls = []

    def uid(self, command, *args):
        self.calls.append((command, args))
        if command == 'search':
            return 'OK', [self.search]
        return 'OK', self.data


class AppTests(unittest.TestCase):
    def test_the_stack_is_the_viewer_alone(self):
        compose = yaml.safe_load((STACK / 'compose.yaml').read_text(encoding='utf-8'))
        self.assertEqual(compose['name'], 'mail-view')
        self.assertEqual(list(compose['services']), ['mail-view'])

    def test_the_service_is_loopback_only(self):
        compose = yaml.safe_load((STACK / 'compose.yaml').read_text(encoding='utf-8'))
        ports = compose['services']['mail-view']['ports']
        self.assertEqual(len(ports), 1)
        self.assertIn('127.0.0.1', ports[0])
        self.assertIn('${MAIL_VIEW_PORT:-8310}', ports[0])

    def test_the_container_is_locked_down_and_stateless(self):
        service = yaml.safe_load((STACK / 'compose.yaml').read_text(encoding='utf-8'))[
            'services']['mail-view']
        self.assertTrue(service['read_only'])
        self.assertEqual(service['cap_drop'], ['ALL'])
        self.assertIn('no-new-privileges:true', service['security_opt'])
        self.assertEqual(service['volumes'], ['./app.py:/app/app.py:ro'])

    def test_the_healthcheck_uses_the_health_endpoint(self):
        service = yaml.safe_load((STACK / 'compose.yaml').read_text(encoding='utf-8'))[
            'services']['mail-view']
        test = ' '.join(str(part) for part in service['healthcheck']['test'])
        self.assertIn('/healthz', test)

    def test_the_app_password_comes_from_manage_py_not_env(self):
        service = yaml.safe_load((STACK / 'compose.yaml').read_text(encoding='utf-8'))[
            'services']['mail-view']
        self.assertEqual(service['environment']['IMAP_PASSWORD'],
                         '${IMAP_PASSWORD:?run manage.py up}')
        example = (STACK / '.env.example').read_text(encoding='utf-8')
        keys = [line.split('=', 1)[0] for line in example.splitlines()
                if line and not line.startswith('#')]
        self.assertIn('IMAP_USERNAME', keys)
        self.assertNotIn('IMAP_PASSWORD', keys)

    def test_the_image_is_the_staged_base_and_pinned(self):
        service = yaml.safe_load((STACK / 'compose.yaml').read_text(encoding='utf-8'))[
            'services']['mail-view']
        self.assertEqual(service['image'], 'python:3.13-alpine')
        self.assertNotIn('latest', service['image'])
        lock = yaml.safe_load((STACK / 'compose.lock.yaml').read_text(encoding='utf-8'))
        self.assertTrue(lock['services']['mail-view']['image'].startswith('python@sha256:'))

    def test_the_script_uses_the_standard_library_only(self):
        for name in ('app.py', 'manage.py'):
            text = (STACK / name).read_text(encoding='utf-8')
            for library in ('import requests', 'import flask', 'import fastapi'):
                self.assertNotIn(library, text, name)

    def test_the_password_stays_out_of_git(self):
        path = str(STACK / 'secrets' / 'imap_password')
        result = subprocess.run(['git', 'check-ignore', '-q', path], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class ConnectionTests(unittest.TestCase):
    def test_the_mailbox_is_selected_read_only(self):
        with patch.object(app.imaplib, 'IMAP4_SSL', FakeIMAP):
            with app.connection(CONFIG) as client:
                self.assertIsNotNone(client)
            calls = FakeIMAP.instance.calls
        self.assertIn(('login', 'shake.notify@gmail.com', 'app-password'), calls)
        # EXAMINE, not SELECT: opening a message must not set \Seen.
        self.assertIn(('select', 'INBOX', True), calls)
        self.assertIn(('logout',), calls)

    def test_a_failed_login_becomes_a_user_facing_error(self):
        class Rejecting(FakeIMAP):
            def login(self, username, password):
                raise app.imaplib.IMAP4.error(b'[AUTHENTICATIONFAILED] Invalid credentials')

        with patch.object(app.imaplib, 'IMAP4_SSL', Rejecting):
            with self.assertRaises(app.MailViewError):
                with app.connection(CONFIG):
                    pass

    def test_a_socket_timeout_becomes_a_user_facing_error(self):
        class Timing(FakeIMAP):
            def login(self, username, password):
                raise TimeoutError('timed out')

        with patch.object(app.imaplib, 'IMAP4_SSL', Timing):
            with self.assertRaises(app.MailViewError):
                with app.connection(CONFIG):
                    pass

    def test_the_header_decode_handles_iso_2022_jp(self):
        header = app.email.header.Header('テスト通知', 'iso-2022-jp').encode()
        self.assertEqual(app.decode_header_value(header), 'テスト通知')
        self.assertEqual(app.decode_header_value(None), '')

    def test_dates_are_converted_to_japan_time(self):
        self.assertEqual(app.format_date('Fri, 25 Sep 2026 03:00:00 +0000', 9),
                         '2026-09-25 12:00')
        self.assertEqual(app.format_date('not a date', 9), 'not a date')

    def test_list_fetches_only_envelope_fields_and_reads_flags(self):
        raw = b'From: notify@example.org\r\nSubject: Hello\r\nDate: Fri, 25 Sep 2026 03:00:00 +0000\r\n\r\n'
        data = [
            (b'1 (UID 3 FLAGS (\\Seen) RFC822.SIZE 2048 '
             b'BODY[HEADER.FIELDS (FROM SUBJECT DATE)] {100}', raw),
            b')',
        ]
        rows, total = app.list_messages(FakeClient(search=b'2 3', data=data), 50, 9)
        self.assertEqual(len(rows), 1)
        self.assertEqual(total, 2)
        self.assertEqual(rows[0]['uid'], '3')
        self.assertEqual(rows[0]['subject'], 'Hello')
        self.assertFalse(rows[0]['unread'])
        self.assertEqual(rows[0]['date'], '2026-09-25 12:00')

    def test_an_unseen_message_is_marked_unread(self):
        raw = b'From: a@example.org\r\nSubject: New\r\nDate: Fri, 25 Sep 2026 03:00:00 +0000\r\n\r\n'
        data = [(b'1 (UID 7 FLAGS () RFC822.SIZE 10 '
                 b'BODY[HEADER.FIELDS (FROM SUBJECT DATE)] {80}', raw), b')']
        rows, total = app.list_messages(FakeClient(search=b'7', data=data), 50, 9)
        self.assertTrue(rows[0]['unread'])

    def test_a_zero_limit_selects_every_message_newest_first(self):
        raw = b'From: a@example.org\r\nSubject: S\r\nDate: Fri, 25 Sep 2026 03:00:00 +0000\r\n\r\n'
        picks = (b'1 (UID 1 FLAGS () RFC822.SIZE 10 BODY[HEADER.FIELDS (FROM SUBJECT DATE)] {60}',
                 b'2 (UID 2 FLAGS () RFC822.SIZE 10 BODY[HEADER.FIELDS (FROM SUBJECT DATE)] {60}',
                 b'3 (UID 3 FLAGS () RFC822.SIZE 10 BODY[HEADER.FIELDS (FROM SUBJECT DATE)] {60}')
        data = [(meta, raw) for meta in picks] + [b')']
        rows, total = app.list_messages(FakeClient(search=b'1 2 3', data=data), 0, 9)
        self.assertEqual([row['uid'] for row in rows], ['3', '2', '1'])
        self.assertEqual(total, 3)

    def test_the_subject_is_flattened_to_one_line(self):
        # Alertmanager の件名はエンコードされた語の中に改行を持つことがある。
        encoded = base64.b64encode('行1\n行2'.encode('utf-8')).decode('ascii')
        raw = (f'From: a@example.org\r\nSubject: =?utf-8?B?{encoded}?=\r\n'
               'Date: Fri, 25 Sep 2026 03:00:00 +0000\r\n\r\n').encode('ascii')
        data = [(b'1 (UID 7 FLAGS () RFC822.SIZE 10 '
                 b'BODY[HEADER.FIELDS (FROM SUBJECT DATE)] {80}', raw), b')']
        rows, _ = app.list_messages(FakeClient(search=b'7', data=data), 50, 9)
        self.assertEqual(rows[0]['subject'], '行1 行2')

    def test_the_limit_override_reads_all_or_a_number(self):
        config = dict(CONFIG)
        self.assertEqual(app.requested_limit(config, {'limit': ['all']}), 0)
        self.assertEqual(app.requested_limit(config, {'limit': ['10']}), 10)
        self.assertEqual(app.requested_limit(config, {'limit': ['99999']}), 2000)
        self.assertEqual(app.requested_limit(config, {}), 50)

    def test_body_prefers_plain_text_and_lists_attachments(self):
        message = app.email.message.EmailMessage()
        message.set_content('Plain body https://example.org/invite')
        message.add_attachment(b'data', maintype='application', subtype='pdf',
                               filename='notice.pdf')
        body, attachments = app.extract_body(message)
        self.assertIn('Plain body', body)
        self.assertEqual(attachments, [('notice.pdf', 4)])

    def test_html_only_mail_loses_scripts_but_keeps_links(self):
        message = app.email.message.EmailMessage()
        message.set_content(
            '<p>こんにちは</p><script>alert(1)</script>'
            '<a href="https://example.org/x">ここ</a>', subtype='html')
        body, _ = app.extract_body(message)
        self.assertIn('こんにちは', body)
        self.assertNotIn('alert(1)', body)
        self.assertIn('https://example.org/x', body)

    def test_html_tables_become_tidy_lines(self):
        # Alertmanager 風の、インデントと表だらけの HTML。
        source = ('<html><body>\n'
                  '        <div>1 alert for</div>\n'
                  '        <table><tr><td>alertname</td><td>=</td>'
                  '<td>ServiceProbeFailed</td></tr></table>\n'
                  '        <p>   </p>\n'
                  '        <p>Labels</p>\n'
                  '        <p>severity = warning</p>\n'
                  '    </body></html>')
        text = app.strip_html(source)
        self.assertIn('alertname = ServiceProbeFailed', text)
        self.assertIn('severity = warning', text)
        self.assertNotIn('\n\n\n', text)
        for line in text.splitlines():
            self.assertEqual(line, line.strip(), repr(line))

    def test_render_text_escapes_everything_except_http_links(self):
        rendered = app.render_text('<b>太字</b> https://example.org/a?b=1&c=2')
        self.assertIn('&lt;b&gt;太字&lt;/b&gt;', rendered)
        self.assertIn('href="https://example.org/a?b=1&amp;c=2"', rendered)
        self.assertNotIn('<b>', rendered)

    def test_javascript_urls_are_not_linkified(self):
        rendered = app.render_text('javascript:alert(1) https://ok.example/')
        self.assertNotIn('href="javascript:', rendered)
        self.assertIn('href="https://ok.example/"', rendered)

    def test_a_password_file_wins_over_the_environment(self):
        directory = Path(tempfile.mkdtemp(prefix='mail-view-secret-'))
        self.addCleanup(lambda: shutil.rmtree(directory, ignore_errors=True))
        (directory / 'password').write_text('from-file\n', encoding='utf-8')
        environment = {
            'IMAP_USERNAME': 'shake.notify@gmail.com',
            'IMAP_PASSWORD': 'from-env',
            'IMAP_PASSWORD_FILE': str(directory / 'password'),
        }
        with patch.dict(app.os.environ, environment, clear=True):
            self.assertEqual(app.settings()['imap_password'], 'from-file')


class FetchTests(unittest.TestCase):
    def message(self):
        message = app.email.message.EmailMessage()
        message['From'] = 'notify@example.org'
        message['To'] = 'shake.notify@gmail.com'
        message['Subject'] = 'Invitation'
        message.set_content('リンク: https://auth.example.org/if/flow/x/?itoken=abc')
        return message

    def test_fetch_returns_the_body_and_notes_truncation(self):
        raw = self.message().as_bytes()
        data = [(f'1 (RFC822.SIZE {len(raw) + 10} BODY[] {{{len(raw)}}}'.encode(), raw), b')']
        result = app.fetch_message(FakeClient(data=data), '5', 65536)
        self.assertEqual(result['subject'], 'Invitation')
        self.assertIn('https://auth.example.org/if/flow/x/?itoken=abc', result['body'])
        self.assertTrue(result['truncated'])

    def test_fetch_without_a_body_is_an_error(self):
        with self.assertRaises(app.MailViewError):
            app.fetch_message(FakeClient(data=[]), '5', 65536)


class HttpTests(unittest.TestCase):
    def start(self):
        server = app.Server(('127.0.0.1', 0), dict(CONFIG))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        return server, f'http://127.0.0.1:{server.server_address[1]}'

    def get(self, url):
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.status, response.headers, response.read().decode('utf-8')
        except urllib.error.HTTPError as error:
            with error:
                return error.code, error.headers, error.read().decode('utf-8')

    def test_healthz_answers_without_imap(self):
        server, base = self.start()
        status, headers, body = self.get(base + '/healthz')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['mailbox'], 'INBOX')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertIn("default-src 'none'", headers['Content-Security-Policy'])

    def test_the_inbox_lists_subjects_and_escapes_them(self):
        server, base = self.start()
        rows = [{'uid': '5', 'from': 'a@example.org', 'subject': '<script>x</script>',
                 'date': '2026-09-25 12:00', 'unread': True, 'size': 10}]
        with patch.object(app, 'cached_list',
                          return_value=(rows, 1, '2026-09-25 12:00', False)):
            status, _, body = self.get(base + '/')
        self.assertEqual(status, 200)
        self.assertIn('&lt;script&gt;x&lt;/script&gt;', body)
        self.assertIn('/m/5', body)

    def test_the_inbox_offers_every_message_when_more_exist(self):
        server, base = self.start()
        rows = [{'uid': '5', 'from': 'a@example.org', 'subject': 'S',
                 'date': '2026-09-25 12:00', 'unread': False, 'size': 10}]
        with patch.object(app, 'cached_list',
                          return_value=(rows, 335, '2026-09-25 12:00', False)):
            status, _, body = self.get(base + '/')
        self.assertEqual(status, 200)
        self.assertIn('全 335 件中 1 件', body)
        self.assertIn('?limit=all', body)

    def test_a_message_page_links_its_body_text(self):
        server, base = self.start()
        message = {
            'uid': '5', 'from': 'a@example.org', 'to': 'b@example.org',
            'subject': '招待', 'date': '2026-09-25 12:00', 'body': 'https://auth.example.org/x',
            'attachments': [], 'truncated': False,
        }
        with patch.object(app, 'connection', lambda config: contextlib.nullcontext(object())), \
             patch.object(app, 'fetch_message', return_value=message):
            status, _, body = self.get(base + '/m/5')
        self.assertEqual(status, 200)
        self.assertIn('href="https://auth.example.org/x"', body)

    def test_an_imap_failure_is_a_502_with_a_japanese_notice(self):
        server, base = self.start()
        error = app.MailViewError('IMAP のログインに失敗しました。')
        with patch.object(app, 'cached_list', side_effect=error):
            status, _, body = self.get(base + '/')
        self.assertEqual(status, 502)
        self.assertIn('IMAP のログインに失敗しました。', body)

    def test_a_socket_timeout_is_a_502_not_a_crash(self):
        server, base = self.start()
        with patch.object(app, 'cached_list', side_effect=TimeoutError('timed out')):
            status, _, body = self.get(base + '/')
        self.assertEqual(status, 502)
        self.assertIn('タイムアウト', body)


class ManageTests(unittest.TestCase):
    def project(self):
        directory = Path(tempfile.mkdtemp(prefix='mail-view-project-'))
        self.addCleanup(lambda: shutil.rmtree(directory, ignore_errors=True))
        return directory

    def test_init_refuses_to_run_without_the_app_password(self):
        project = self.project()
        (project / '.env.example').write_text('MAIL_VIEW_PORT=8310\n', encoding='utf-8')
        with patch.object(manage, 'ROOT', project):
            with self.assertRaises(ValueError):
                manage.init()

    def test_init_keeps_the_installed_password_and_sets_private_modes(self):
        project = self.project()
        (project / '.env.example').write_text('MAIL_VIEW_PORT=8310\n', encoding='utf-8')
        (project / 'secrets').mkdir()
        password = project / 'secrets' / 'imap_password'
        password.write_text('app-password\n', encoding='utf-8')
        with patch.object(manage, 'ROOT', project):
            manage.init()
        self.assertEqual(password.read_text(encoding='utf-8'), 'app-password\n')
        self.assertEqual(password.stat().st_mode & 0o777, 0o400)
        self.assertEqual((project / '.env').stat().st_mode & 0o777, 0o600)

    def test_compose_receives_the_password_from_the_secret_file(self):
        project = self.project()
        (project / 'secrets').mkdir()
        (project / 'secrets' / 'imap_password').write_text('app-password\n', encoding='utf-8')
        with patch.object(manage, 'ROOT', project):
            with patch.object(manage, 'run') as run:
                manage.compose('config')
        self.assertEqual(run.call_args.kwargs['env']['IMAP_PASSWORD'], 'app-password')

    def test_restart_forces_the_container_to_be_recreated(self):
        project = self.project()
        (project / 'compose.lock.yaml').write_text('{}', encoding='utf-8')
        with patch.object(manage, 'ROOT', project), \
             patch.object(manage, 'compose') as compose:
            manage.restart()
        self.assertEqual(compose.call_args.args,
                         ('up', '-d', '--force-recreate', '--remove-orphans',
                          '--wait', '--wait-timeout', '120'))

    def test_existing_digests_are_not_refreshed(self):
        project = self.project()
        existing = {'services': {'mail-view': {'image': 'python@sha256:old'}}}
        (project / '.env').write_text('MAIL_VIEW_PORT=8310\n', encoding='utf-8')
        (project / 'compose.lock.yaml').write_text(json.dumps(existing), encoding='utf-8')
        config = json.dumps({'services': {'mail-view': {'image': 'python:3.13-alpine'}}})
        with patch.object(manage, 'ROOT', project), \
             patch.object(manage, 'compose', return_value=SimpleNamespace(stdout=config)), \
             patch.object(manage, 'run') as run:
            manage.lock()
        run.assert_not_called()
        self.assertEqual(json.loads((project / 'compose.lock.yaml').read_text()), existing)


class IacTests(unittest.TestCase):
    def test_the_playbook_deploys_the_viewer_behind_tls_and_sso(self):
        play = yaml.safe_load((ROOT / 'platform/ansible/mail-view.yml').read_text(encoding='utf-8'))
        self.assertEqual(play[0]['hosts'], 'netbox_bootstrap')
        roles = play[0]['roles']
        self.assertLess(roles.index('docker'), roles.index('mail_view'))
        self.assertLess(roles.index('tls_proxy'), roles.index('mail_view'))

    def test_the_role_wires_the_credentials_and_the_stack(self):
        defaults = yaml.safe_load(
            (ROOT / 'platform/ansible/roles/mail_view/defaults/main.yml').read_text(encoding='utf-8'))
        self.assertEqual(defaults['mail_view_project_dir'], '/opt/services/mail-view')
        self.assertEqual(defaults['mail_view_port'], 8310)
        self.assertEqual(defaults['mail_view_public_url'],
                         'https://mail-view.{{ mail_view_dns.zone }}')
        self.assertTrue(defaults['mail_view_sops_file'].endswith('mail-view.sops.yaml'))
        self.assertTrue(defaults['mail_view_fallback_sops_file'].endswith('smtp.sops.yaml'))
        tasks = yaml.safe_load(
            (ROOT / 'platform/ansible/roles/mail_view/tasks/main.yml').read_text(encoding='utf-8'))
        serialized = json.dumps(tasks)
        for token in ('compose.yaml', 'compose.lock.yaml', 'manage.py', 'app.py',
                      '.env.example', 'imap_password'):
            self.assertIn(token, serialized, token)
        commands = {tuple(task['ansible.builtin.command']['argv'])
                    for task in tasks if 'ansible.builtin.command' in task}
        for action in ('init', 'lock', 'up', 'restart'):
            self.assertIn(('python3', 'manage.py', action), commands, action)
        secret_tasks = [task for task in tasks
                        if 'imap_password' in json.dumps(task)
                        or 'mail_view_credentials.stdout' in json.dumps(task)]
        self.assertTrue(secret_tasks)
        for task in secret_tasks:
            self.assertTrue(task.get('no_log'), task['name'])
        # content に Jinja の改行を足すと、copy はリテラルのバックスラッシュ+n を
        # 書いてしまいパスワードに2文字混入する（2026-09-26 実測）。値をそのまま書く。
        installs = [task['ansible.builtin.copy'] for task in tasks
                    if task.get('ansible.builtin.copy', {}).get('dest', '')
                    .endswith('secrets/imap_password')]
        self.assertEqual(len(installs), 1)
        self.assertEqual(installs[0]['content'],
                         '{{ (mail_view_credentials.stdout | from_json)[mail_view_password_key] }}')

    def test_dns_declares_mail_view_on_services_01_behind_auth(self):
        dns = yaml.safe_load((ROOT / 'platform/terraform/dns.yaml').read_text(encoding='utf-8'))
        record = dns['records']['mail-view']
        self.assertEqual(record['host'], 'services-01')
        self.assertEqual(record['upstream'], '127.0.0.1:8310')
        self.assertTrue(record['auth'])
        self.assertIn('Gmail', record['description'])


if __name__ == '__main__':
    unittest.main()