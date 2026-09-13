"""Guard the FreshRSS unit for media-01 (shared RSS timeline).

The unit is unusual: a system extension (SharedFeeds) makes every user's
subscription list one common timeline in real time. A wrong project name, a
LAN-bound port, a mount that hides the extension, or a hook that stops being a
system extension would only show up on the VM, so these are source-text, YAML,
JSON and XML assertions. Nothing here connects to media-01 or runs Docker.
"""
import ast
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / 'stacks/media/freshrss'
EXTENSION = UNIT / 'extensions/xExtension-SharedFeeds'
COMPOSE = yaml.safe_load((UNIT / 'compose.yaml').read_text(encoding='utf-8'))
LOCK = yaml.safe_load((UNIT / 'compose.lock.yaml').read_text(encoding='utf-8'))
DNS = yaml.safe_load((ROOT / 'platform/terraform/dns.yaml').read_text(encoding='utf-8'))
PLAYBOOK = ROOT / 'platform/ansible/media-freshrss.yml'
SSO_PLAYBOOK = ROOT / 'platform/ansible/media-freshrss-sso.yml'
ZONE = 'apextox.dpdns.org'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ComposeTests(unittest.TestCase):
    def test_it_is_an_independent_project(self):
        self.assertEqual(COMPOSE['name'], 'media-freshrss')
        self.assertEqual(list(COMPOSE['services']), ['freshrss'])

    def test_the_port_is_loopback_only(self):
        ports = COMPOSE['services']['freshrss']['ports']
        self.assertEqual(ports, ['127.0.0.1:${FRESHRSS_PORT:-8082}:80'])
        self.assertNotIn('0.0.0.0', ''.join(ports))

    def test_data_persists_on_the_data_disk(self):
        volumes = COMPOSE['services']['freshrss']['volumes']
        self.assertIn('${STORAGE_ROOT:-/srv/media-stack/storage}/freshrss/data:/var/www/FreshRSS/data',
                      volumes)

    def test_the_extension_is_mounted_read_only(self):
        volumes = COMPOSE['services']['freshrss']['volumes']
        self.assertIn('./extensions:/var/www/FreshRSS/extensions:ro', volumes)

    def test_native_oidc_is_declared(self):
        environment = COMPOSE['services']['freshrss']['environment']
        # Secrets arrive from manage.py; the compose file must not require them
        # so a first deploy without the identity secret can still start.
        self.assertEqual(environment['OIDC_ENABLED'], '${FRESHRSS_OIDC_ENABLED:-0}')
        self.assertEqual(environment['OIDC_REMOTE_USER_CLAIM'], 'preferred_username')
        self.assertIn('X-Forwarded-Proto', environment['OIDC_X_FORWARDED_HEADERS'])
        self.assertEqual(environment['OIDC_CLIENT_SECRET'], '${FRESHRSS_OIDC_CLIENT_SECRET:-}')

    def test_only_loopback_and_the_docker_bridge_are_trusted(self):
        environment = COMPOSE['services']['freshrss']['environment']
        self.assertEqual(environment['TRUSTED_PROXY'], '127.0.0.0/8 172.16.0.0/12')

    def test_install_and_user_creation_are_non_interactive(self):
        environment = COMPOSE['services']['freshrss']['environment']
        self.assertIn('--default-user ${FRESHRSS_DEFAULT_USER', environment['FRESHRSS_INSTALL'])
        self.assertIn('--auth-type http_auth', environment['FRESHRSS_INSTALL'])
        self.assertIn('--api-enabled', environment['FRESHRSS_INSTALL'])
        self.assertIn('--user ${FRESHRSS_DEFAULT_USER', environment['FRESHRSS_USER'])
        # 既定フィードがあると新規ユーザーが「購読が空」と見なされず共通リストが配られない。
        self.assertIn('--no-default-feeds', environment['FRESHRSS_USER'])

    def test_the_healthcheck_uses_the_api_which_oidc_does_not_protect(self):
        healthcheck = COMPOSE['services']['freshrss']['healthcheck']
        self.assertEqual(healthcheck['test'], ['CMD', 'cli/health.php'])


class LockTests(unittest.TestCase):
    def test_every_service_is_pinned_to_a_digest(self):
        self.assertEqual(set(LOCK['services']), set(COMPOSE['services']))
        for name, service in LOCK['services'].items():
            self.assertRegex(service['image'], r'@sha256:[0-9a-f]{64}$', name)

    def test_the_image_is_the_debian_variant_that_supports_oidc(self):
        image = LOCK['services']['freshrss']['image']
        self.assertTrue(image.startswith('freshrss/freshrss@'), image)
        self.assertNotIn('alpine', image)


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.metadata = json.loads((EXTENSION / 'metadata.json').read_text(encoding='utf-8'))
        self.text = (EXTENSION / 'extension.php').read_text(encoding='utf-8')

    def test_it_is_a_system_extension_named_shared_feeds(self):
        self.assertEqual(self.metadata['name'], 'SharedFeeds')
        self.assertEqual(self.metadata['entrypoint'], 'SharedFeeds')
        self.assertEqual(self.metadata['type'], 'system')
        self.assertIn('final class SharedFeedsExtension extends Minz_Extension', self.text)

    def test_it_hooks_adding_deleting_and_the_first_login(self):
        self.assertIn('Minz_HookType::FeedBeforeInsert', self.text)
        self.assertIn('Minz_HookType::ActionExecute', self.text)
        self.assertIn('Minz_HookType::FreshrssInit', self.text)
        self.assertIn("Minz_Request::is('feed', 'delete')", self.text)

    def test_it_writes_to_other_users_through_the_per_user_dao(self):
        self.assertIn('FreshRSS_user_Controller::listUsers()', self.text)
        self.assertIn('FreshRSS_Factory::createFeedDao($user)', self.text)
        self.assertIn('FreshRSS_Factory::createFeedDao($target)', self.text)
        self.assertIn('listFeeds()', self.text)
        self.assertIn('checkDefault()', self.text)
        self.assertIn('searchByName', self.text)
        self.assertIn('DEFAULTCATEGORYID', self.text)

    def test_a_failure_never_blocks_the_users_own_action(self):
        self.assertIn('catch (Throwable $error)', self.text)
        self.assertIn('Minz_Log::warning', self.text)
        self.assertNotIn('throw ', self.text)


class ManageTests(unittest.TestCase):
    def setUp(self):
        self.text = (UNIT / 'manage.py').read_text(encoding='utf-8')
        self.manage = load(UNIT / 'manage.py', 'freshrss_manage')

    def test_the_required_actions_are_available(self):
        for action in ('init', 'lock', 'up', 'configure', 'seed', 'status', 'down', 'backup'):
            self.assertIn(f"'{action}'", self.text)

    def test_it_enables_the_extension_in_the_system_config(self):
        self.assertIn("extensions_enabled", self.manage.ENABLE_EXTENSION)
        self.assertIn("SharedFeeds", self.manage.ENABLE_EXTENSION)
        self.assertIn('opcache_reset', self.manage.ENABLE_EXTENSION)

    def test_it_generates_secrets_outside_the_env_file(self):
        self.assertIn("'oidc_crypto_key'", self.text)
        self.assertIn('token_urlsafe', self.text)
        self.assertIn("chmod(0o400)", self.text)
        self.assertIn(".env.example", self.text)
        for name in ('compose.yaml', 'compose.lock.yaml', '.env.example'):
            text = (UNIT / name).read_text(encoding='utf-8')
            self.assertNotRegex(text, r'(?im)^(PASSWORD|TOKEN|SECRET|API_KEY)=', name)

    def test_it_disables_the_default_feeds_for_new_users(self):
        # FreshRSS uses data/opml.xml when it exists; an empty OPML keeps a new
        # account from having a feed, so the extension can populate the union.
        self.assertIn("'opml.xml'", self.text)
        self.assertIn('<body></body>', self.text)

    def test_backup_takes_a_cold_snapshot_including_the_secrets(self):
        section = self.text.split('def backup', 1)[1].split('def main', 1)[0]
        self.assertIn('os.geteuid() != 0', section)
        self.assertIn('.incomplete', section)
        self.assertIn("target.rename(complete)", section)
        self.assertIn('state.tar', section)
        self.assertIn("'secrets'", section)
        self.assertIn("compose('stop'", section)

    def test_it_uses_only_the_standard_library(self):
        modules = set()
        for node in ast.walk(ast.parse(self.text)):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add((node.module or '').split('.')[0])
        self.assertLessEqual(modules, set(sys.stdlib_module_names))


class SeedTests(unittest.TestCase):
    def test_the_starter_opml_covers_the_three_timelines(self):
        tree = ET.parse(UNIT / 'feeds.opml')
        self.assertEqual(tree.getroot().tag, 'opml')
        text = (UNIT / 'feeds.opml').read_text(encoding='utf-8')
        for category in ('ゲーム', 'IT', 'ポケモン'):
            self.assertIn(f'text="{category}"', text)
        feeds = [element for element in tree.iter('outline') if 'xmlUrl' in element.attrib]
        self.assertGreaterEqual(len(feeds), 20)
        for feed in feeds:
            self.assertTrue(feed.attrib['xmlUrl'].startswith('https://'), feed.attrib['xmlUrl'])

    def test_the_starter_opml_assigns_subreddits_to_all_three(self):
        tree = ET.parse(UNIT / 'feeds.opml')
        body = tree.getroot().find('body')
        self.assertIsNotNone(body)
        by_category = {}
        for category in body.findall('outline'):
            by_category[category.attrib['text']] = [
                feed.attrib['xmlUrl'] for feed in category.findall('outline')]
        self.assertEqual(set(by_category), {'ゲーム', 'IT', 'ポケモン'})
        for category, feeds in by_category.items():
            self.assertTrue(any('reddit.com' in url for url in feeds), category)

    def test_the_seed_runs_once(self):
        text = (UNIT / 'manage.py').read_text(encoding='utf-8')
        self.assertIn('feeds_seeded', text)
        self.assertIn('import-for-user.php', text)
        self.assertIn("'/var/www/FreshRSS/data/seed.opml'", text)


class AnsibleTests(unittest.TestCase):
    def setUp(self):
        self.play = yaml.safe_load(PLAYBOOK.read_text(encoding='utf-8'))[0]

    def test_it_targets_the_media_group_as_root(self):
        self.assertEqual(self.play['hosts'], 'media')
        self.assertTrue(self.play['become'])

    def test_it_deploys_the_unit_and_the_extension(self):
        copies = [task['ansible.builtin.copy'] for task in self.play['tasks']
                  if 'ansible.builtin.copy' in task]
        self.assertTrue(any(copy['dest'].startswith('{{ project_dir }}/media/freshrss/')
                            for copy in copies))
        self.assertTrue(any(copy['src'].endswith('/extensions/') for copy in copies))
        self.assertTrue(any(copy['dest'].endswith('/.env') and copy['mode'] == '0600'
                            for copy in copies))

    def test_it_starts_the_unit_with_manage_py(self):
        commands = [task['ansible.builtin.command']['argv'] for task in self.play['tasks']
                    if 'ansible.builtin.command' in task]
        self.assertTrue(any(argv[-1] == 'up' and argv[-2].endswith('manage.py')
                            for argv in commands))


class SsoPlaybookTests(unittest.TestCase):
    def setUp(self):
        self.text = SSO_PLAYBOOK.read_text(encoding='utf-8')
        self.play = yaml.safe_load(self.text)[0]

    def test_it_reads_the_secret_from_identity_without_logging_it(self):
        slurps = [task for task in self.play['tasks'] if 'ansible.builtin.slurp' in task]
        self.assertEqual(len(slurps), 1)
        self.assertIn('oidc-media.json', slurps[0]['ansible.builtin.slurp']['src'])
        self.assertTrue(slurps[0]['no_log'])
        copies = [task for task in self.play['tasks'] if 'ansible.builtin.copy' in task]
        secret = [task for task in copies if task['ansible.builtin.copy']['dest'].endswith('oidc_client.json')]
        self.assertEqual(len(secret), 1)
        self.assertEqual(secret[0]['ansible.builtin.copy']['mode'], '0600')
        self.assertTrue(secret[0]['no_log'])

    def test_it_restarts_the_unit_after_writing_the_secret(self):
        commands = [task['ansible.builtin.command']['argv'] for task in self.play['tasks']
                    if 'ansible.builtin.command' in task]
        self.assertTrue(any(argv[-1] == 'up' and argv[-2].endswith('manage.py')
                            for argv in commands))


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.configure = load(ROOT / 'stacks/identity/configure.py', 'identity_configure')

    def test_freshrss_is_a_native_oidc_client(self):
        self.assertEqual(self.configure.MEDIA_OIDC_CLIENTS['freshrss'], '/i/oidc/')
        self.assertEqual(self.configure.media_redirect('freshrss', ZONE),
                         f'https://freshrss.{ZONE}/i/oidc/')
        self.assertIn('freshrss', self.configure.MEDIA_APPLICATIONS)

    def test_freshrss_is_not_a_forward_auth_provider(self):
        self.assertNotIn('freshrss', self.configure.MEDIA_PROXY_PROVIDERS)


class DnsTests(unittest.TestCase):
    def test_freshrss_points_at_the_loopback_upstream_without_forward_auth(self):
        record = DNS['records']['freshrss']
        self.assertEqual(record['upstream'], '127.0.0.1:8082')
        self.assertEqual(record['host'], 'media-01')
        self.assertNotIn('auth', record)


class DocsTests(unittest.TestCase):
    def test_the_user_guide_and_nav_exist(self):
        guide = (ROOT / 'docs/services/rss.md').read_text(encoding='utf-8')
        self.assertIn('SharedFeeds', guide)
        self.assertIn('freshrss.apextox.dpdns.org', guide)
        nav = (ROOT / 'mkdocs.yml').read_text(encoding='utf-8')
        self.assertIn('services/rss.md', nav)


if __name__ == '__main__':
    unittest.main()
