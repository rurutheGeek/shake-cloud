"""Guard the shake_print Nextcloud app and the print API it talks to.

The app is a small custom app: a file action in the Files menu posts the file
id to Nextcloud, the controller forwards the document to the print API on
services-01, and that service runs `lp` against the relayed CUPS queue.
"""
import importlib.util
import json
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'stacks/media/nextcloud/apps/shake_print'
STACK = ROOT / 'stacks/print-api'
ROLE = ROOT / 'platform/ansible/roles/cups'
PLAYBOOK = ROOT / 'platform/ansible/media-nextcloud.yml'
GROUP_VARS = ROOT / 'platform/ansible/group_vars/media.yml'
SOPS_EXAMPLE = ROOT / 'platform/sops/print-api.sops.yaml.example'


def read(path):
    return path.read_text(encoding='utf-8')


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


api = load_module(STACK / 'print_api.py', 'print_api')


class ApiTests(unittest.TestCase):
    def test_a_valid_token_from_the_allowed_client_passes(self):
        self.assertTrue(api.authorized('Bearer s3cret', '192.168.10.101',
                                       's3cret', {'192.168.10.101'}))

    def test_a_wrong_or_missing_token_is_refused(self):
        self.assertFalse(api.authorized('Bearer wrong', '192.168.10.101',
                                        's3cret', {'192.168.10.101'}))
        self.assertFalse(api.authorized(None, '192.168.10.101',
                                        's3cret', {'192.168.10.101'}))

    def test_another_client_is_refused_even_with_the_token(self):
        self.assertFalse(api.authorized('Bearer s3cret', '192.168.10.99',
                                        's3cret', {'192.168.10.101'}))

    def test_an_empty_allowlist_still_requires_the_token(self):
        self.assertTrue(api.authorized('Bearer s3cret', '192.0.2.9', 's3cret', set()))
        self.assertFalse(api.authorized('Bearer wrong', '192.0.2.9', 's3cret', set()))

    def test_only_printable_extensions_are_allowed(self):
        for extension in ('pdf', 'png', 'jpg', 'jpeg', 'txt'):
            self.assertIn(extension, api.ALLOWED_EXTENSIONS)
        for extension in ('exe', 'svg', 'zip'):
            self.assertNotIn(extension, api.ALLOWED_EXTENSIONS)

    def test_the_filename_is_reduced_to_a_safe_title(self):
        # Nextcloud urlencode するので、ここで戻してから basename を取る。
        self.assertEqual(api.printable_name('..%2F..%2Fetc%2Fpasswd.pdf'),
                         ('passwd.pdf', 'pdf'))
        self.assertEqual(api.printable_name(''), ('document', ''))
        self.assertEqual(api.printable_name('report%20final.PDF'),
                         ('report final.PDF', 'pdf'))

    def test_copies_are_bounded(self):
        self.assertEqual(api.bounded('200', 1, 99, 1), 99)
        self.assertEqual(api.bounded('0', 1, 99, 1), 1)
        self.assertEqual(api.bounded('x', 1, 99, 1), 1)
        self.assertEqual(api.bounded('3', 1, 99, 1), 3)

    def test_the_command_targets_the_queue_with_the_chosen_mode(self):
        command = api.lp_command('ts8430', 'report.pdf', 2, 'monochrome', '/tmp/x.pdf')
        self.assertEqual(command[:5], ['lp', '-d', 'ts8430', '-t', 'report.pdf'])
        self.assertIn('print-color-mode=monochrome', command)
        self.assertEqual(command[-1], '/tmp/x.pdf')

    def test_the_job_id_is_read_from_the_lp_output(self):
        self.assertEqual(api.parse_job_id('request id is ts8430-42 (1 file(s))'),
                         'ts8430-42')
        self.assertIsNone(api.parse_job_id('lp: Error - unable to print'))


class RoleTests(unittest.TestCase):
    def setUp(self):
        self.tasks = yaml.safe_load(read(ROLE / 'tasks/main.yml'))
        self.names = [task['name'] for task in self.tasks]
        self.defaults = yaml.safe_load(read(ROLE / 'defaults/main.yml'))

    def task(self, name):
        return next(task for task in self.tasks if task['name'] == name)

    def test_the_api_is_installed_and_started(self):
        for name in ('Read the print API token', 'Install the print API',
                     'Write the print API environment', 'Install the print API unit',
                     'Enable and start the print API'):
            self.assertIn(name, self.names)

    def test_the_api_source_lives_in_the_stack_directory(self):
        # サービス本体は stacks/<機能>/ に置く（音楽同期などと同じ型）。
        self.assertTrue((STACK / 'print_api.py').exists())
        self.assertTrue((STACK / 'print-api.service.j2').exists())
        self.assertEqual(self.defaults['cups_print_api_source_dir'],
                         '{{ playbook_dir }}/../../stacks/print-api')
        self.assertEqual(self.task('Install the print API')['ansible.builtin.copy']['src'],
                         '{{ cups_print_api_source_dir }}/print_api.py')
        self.assertEqual(self.task('Install the print API unit')['ansible.builtin.template']['src'],
                         '{{ cups_print_api_source_dir }}/print-api.service.j2')

    def test_the_token_comes_from_sops_and_never_reaches_the_log(self):
        token = self.task('Read the print API token')
        self.assertTrue(token['no_log'])
        command = token['ansible.builtin.command']['argv']
        self.assertIn('["PRINT_API_TOKEN"]', command)
        self.assertTrue(self.defaults['cups_print_api_sops_file']
                        .endswith('print-api.sops.yaml'))
        env = self.task('Write the print API environment')
        self.assertTrue(env['no_log'])
        self.assertIn('PRINT_API_TOKEN={{ cups_print_api_token.stdout }}',
                      env['ansible.builtin.copy']['content'])

    def test_the_env_keeps_the_allowlist_and_queue(self):
        env = self.task('Write the print API environment')
        content = env['ansible.builtin.copy']['content']
        self.assertIn('PRINT_API_ALLOWED={{ cups_print_api_allowed }}', content)
        self.assertIn('PRINT_QUEUE={{ cups_printer_name }}', content)

    def test_the_service_runs_the_api_with_the_environment_file(self):
        unit = read(STACK / 'print-api.service.j2')
        self.assertIn('ExecStart=/usr/bin/python3 {{ cups_print_api_dir }}/print_api.py', unit)
        self.assertIn('EnvironmentFile={{ cups_print_api_dir }}/print-api.env', unit)
        self.assertIn('ProtectSystem=strict', unit)

    def test_the_defaults_point_at_the_nextcloud_host(self):
        self.assertEqual(self.defaults['cups_print_api_allowed'], '192.168.10.101')
        self.assertEqual(self.defaults['cups_printer_name'], 'ts8430')


class AppTests(unittest.TestCase):
    def test_info_declares_the_app_and_the_supported_versions(self):
        info = read(APP / 'appinfo/info.xml')
        self.assertIn('<id>shake_print</id>', info)
        self.assertIn('<nextcloud min-version="30" max-version="33"/>', info)
        self.assertIn('<php min-version="8.1"/>', info)

    def test_the_namespace_matches_the_php_namespace(self):
        # 宣言が無いと Nextcloud は ucfirst した OCA\Shake_print を探し、
        # OCA\ShakePrint と噛み合わず二重includeで落ちる（2026-09-13 実測）。
        info = read(APP / 'appinfo/info.xml')
        application = read(APP / 'lib/AppInfo/Application.php')
        self.assertIn('<namespace>ShakePrint</namespace>', info)
        self.assertIn('namespace OCA\\ShakePrint\\AppInfo;', application)

    def test_the_files_script_is_registered_on_the_files_page(self):
        application = read(APP / 'lib/AppInfo/Application.php')
        listener = read(APP / 'lib/Listener/LoadAdditionalScripts.php')
        self.assertIn('LoadAdditionalScriptsEvent::class', application)
        self.assertIn("Util::addScript('shake_print', 'shake_print')", listener)

    def test_the_controller_forwards_with_a_token_to_the_relay(self):
        controller = read(APP / 'lib/Controller/PrintController.php')
        self.assertIn("#[FrontpageRoute(verb: 'POST', url: '/print')]", controller)
        self.assertIn("getAppValue('shake_print', 'print_api_url'", controller)
        self.assertIn("getAppValue('shake_print', 'print_api_token'", controller)
        self.assertIn("'Bearer ' . $token", controller)
        self.assertIn("'allow_local_address' => true", controller)
        self.assertIn('isReadable()', controller)

    def test_the_bundle_registers_the_print_action(self):
        bundle = read(APP / 'js/shake_print.js')
        self.assertIn('registerFileAction', bundle)
        self.assertIn('/apps/shake_print/print', bundle)
        self.assertIn('shake-print', bundle)

    def test_the_bundle_does_not_pull_the_dialog_vue_tree(self):
        # dialogs は FilePicker 経由で path/Vue/CSS を引き込むため使わない。
        package = json.loads(read(APP / 'package.json'))
        self.assertNotIn('@nextcloud/dialogs', package['dependencies'])
        self.assertFalse((APP / 'js/shake_print.css').exists())
        self.assertTrue((APP / 'package-lock.json').exists())


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.play = yaml.safe_load(read(PLAYBOOK))[0]

    def test_the_app_is_copied_into_the_nextcloud_html_volume(self):
        copies = [task for task in self.play['tasks']
                  if 'ansible.builtin.copy' in task
                  and 'shake_print' in str(task['ansible.builtin.copy'].get('src', ''))]
        self.assertEqual(len(copies), 1)
        task = copies[0]
        self.assertIn('custom_apps/shake_print', task['ansible.builtin.copy']['dest'])

    def test_the_relay_url_and_token_are_configured(self):
        commands = [task for task in self.play['tasks']
                    if 'ansible.builtin.command' in task
                    and 'config-print' in str(task['ansible.builtin.command']['argv'])]
        self.assertEqual(len(commands), 1)
        environment = commands[0]['environment']
        self.assertIn('PRINT_API_URL', environment)
        self.assertIn('PRINT_API_TOKEN', environment)

    def test_the_play_reads_the_token_from_sops(self):
        readers = [task for task in self.play['tasks']
                   if 'ansible.builtin.command' in task
                   and 'print-api.sops.yaml' in str(task['ansible.builtin.command']['argv'])]
        self.assertEqual(len(readers), 1)
        self.assertTrue(readers[0]['no_log'])

    def test_the_api_url_matches_the_cups_role(self):
        defaults = yaml.safe_load(read(ROLE / 'defaults/main.yml'))
        group = yaml.safe_load(read(GROUP_VARS))
        self.assertIn(f":{defaults['cups_print_api_port']}", group['nextcloud_print_api_url'])

    def test_the_sops_example_documents_the_token(self):
        example = read(SOPS_EXAMPLE)
        self.assertIn('PRINT_API_TOKEN:', example)
        self.assertIn('REPLACE_WITH_A_RANDOM_TOKEN', example)


if __name__ == '__main__':
    unittest.main()
