"""Guard the bot portal: allowlisted actions only, loopback-only, SSO inside.

The portal runs manage.py and talks to the Docker socket, so it is effectively
as powerful as the host. It must stay on loopback, behind Forward Auth, and it
must only run the actions listed in services.yaml.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/bot-portal'
SPEC = importlib.util.spec_from_file_location('bot_portal_actions', STACK / 'app/actions.py')
actions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(actions)

REGISTRY = '''
services:
  - name: ubsleepy
    title: UBSLEEPY
    description: test bot
    container: ubsleepy-bot-1
    project_dir: /opt/ubsleepy
    source_dir: /srv/ubsleepy/source
    actions: [restart, status, update]
    help: これはテストです。
    checks:
      - 確認手順その1
      - 確認手順その2
'''


class RegistryTests(unittest.TestCase):
    def load(self, text=REGISTRY):
        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False, encoding='utf-8') as file:
            file.write(text)
            path = file.name
        self.addCleanup(lambda: Path(path).unlink(missing_ok=True))
        return actions.load_services(path)

    def test_loads_services_and_their_actions(self):
        service = self.load()[0]
        self.assertEqual(service.name, 'ubsleepy')
        self.assertTrue(service.allows('update'))
        self.assertFalse(service.allows('down'))

    def test_loads_help_and_checks(self):
        service = self.load()[0]
        self.assertEqual(service.help, 'これはテストです。')
        self.assertEqual(service.checks, ('確認手順その1', '確認手順その2'))

    def test_action_buttons_carry_labels_and_danger(self):
        buttons = {button['name']: button for button in self.load()[0].action_buttons()}
        self.assertEqual(buttons['restart']['label'], '再起動')
        self.assertFalse(buttons['restart']['dangerous'])
        self.assertTrue(buttons['update']['dangerous'])

    def test_unknown_action_is_rejected_at_load(self):
        with self.assertRaises(ValueError):
            self.load(REGISTRY.replace('[restart, status, update]', '[rm -rf]'))

    def test_command_for_manage_action(self):
        service = self.load()[0]
        self.assertEqual(actions.command_for(service, 'status'),
                         ['python3', '/opt/ubsleepy/manage.py', 'status'])

    def test_command_for_restart(self):
        service = self.load()[0]
        self.assertEqual(actions.command_for(service, 'restart'),
                         ['docker', 'restart', 'ubsleepy-bot-1'])

    def test_command_for_disallowed_action(self):
        service = self.load()[0]
        with self.assertRaises(ValueError):
            actions.command_for(service, 'down')


class StackTests(unittest.TestCase):
    def compose(self):
        return yaml.safe_load((STACK / 'compose.yaml').read_text(encoding='utf-8'))

    def test_the_portal_is_loopback_only(self):
        ports = self.compose()['services']['portal']['ports']
        self.assertEqual(ports, ['127.0.0.1:${PORTAL_PORT:-8095}:8095'])

    def test_the_portal_reaches_docker_and_the_bot_directories(self):
        volumes = self.compose()['services']['portal']['volumes']
        self.assertIn('/var/run/docker.sock:/var/run/docker.sock', volumes)
        self.assertIn('/opt/ubsleepy:/opt/ubsleepy', volumes)
        self.assertIn('/opt/circleauth:/opt/circleauth', volumes)

    def test_the_dns_record_goes_through_forward_auth(self):
        dns = yaml.safe_load((ROOT / 'platform/terraform/dns.yaml').read_text(encoding='utf-8'))
        record = dns['records']['portal']
        self.assertEqual(record['host'], 'apps-01')
        self.assertEqual(record['upstream'], '127.0.0.1:8095')
        self.assertTrue(record['auth'])

    def test_the_authentik_app_is_reconciled(self):
        spec = importlib.util.spec_from_file_location(
            'identity_configure', ROOT / 'stacks/identity/configure.py')
        configure = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(configure)
        self.assertEqual(configure.BOT_PORTAL, 'portal')
        source = (ROOT / 'stacks/identity/configure.py').read_text(encoding='utf-8')
        self.assertIn('configure_bot_portal(api, groups, flows, portal_url)', source)

    def test_the_playbook_targets_apps(self):
        play = yaml.safe_load(
            (ROOT / 'platform/ansible/bot-portal.yml').read_text(encoding='utf-8'))[0]
        self.assertEqual(play['hosts'], 'apps')
        self.assertEqual(play['roles'], ['docker', 'bot_portal', 'tls_proxy'])
