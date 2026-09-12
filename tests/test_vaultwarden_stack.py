"""Guard the Vaultwarden stack's isolation, SSO declaration and deployment wiring.

Vaultwarden is its own Compose project on services-01 and a native OIDC client
of the new identity. It holds no data from the old staging host. A test that
let the old media-hub installation creep back in, that enabled open signups,
or that put the admin token or the OIDC secret in Git, would be worse than no
test.
"""
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/vaultwarden'
SPEC = importlib.util.spec_from_file_location('vaultwarden_manage', STACK / 'manage.py')
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)

PUBLIC_URL = 'https://vault.apextox.dpdns.org'
REDIRECT = PUBLIC_URL + '/identity/connect/oidc-signin'

SSO_EXPECTED = {
    'SSO_ENABLED': 'true',
    'SSO_ONLY': 'false',
    'SSO_SIGNUPS_MATCH_EMAIL': 'false',
    'SSO_ALLOW_UNKNOWN_EMAIL_VERIFICATION': 'false',
    'SSO_SCOPES': 'email profile offline_access',
    'SSO_PKCE': 'true',
}


class StackTests(unittest.TestCase):
    def compose(self):
        return yaml.safe_load((STACK / 'compose.yaml').read_text(encoding='utf-8'))

    def service(self):
        return self.compose()['services']['vaultwarden']

    def test_the_project_is_vaultwarden_alone(self):
        compose = self.compose()
        self.assertEqual(compose['name'], 'vaultwarden')
        self.assertEqual(list(compose['services']), ['vaultwarden'])

    def test_the_old_hub_services_are_not_copied_in(self):
        services = set(self.compose()['services'])
        for name in ('authentik', 'postgresql', 'database', 'docs', 'caddy'):
            self.assertNotIn(name, services, name)

    def test_the_service_is_loopback_only(self):
        ports = self.service()['ports']
        self.assertEqual(len(ports), 1)
        self.assertIn('127.0.0.1', ports[0])
        self.assertIn('${VAULTWARDEN_PORT:-8222}', ports[0])

    def test_the_state_lives_outside_the_deployment_directory(self):
        volumes = self.service()['volumes']
        self.assertEqual(volumes, ['${STORAGE_ROOT:-/srv/services/vaultwarden}/data:/data'])

    def test_the_public_name_is_the_new_https_entry(self):
        self.assertEqual(self.service()['environment']['DOMAIN'], PUBLIC_URL)

    def test_open_signups_are_disabled(self):
        self.assertEqual(self.service()['environment']['SIGNUPS_ALLOWED'],
                         '${VAULTWARDEN_SIGNUPS_ALLOWED:-false}')

    def test_org_invitations_are_disabled_so_the_ui_stops_offering_signup(self):
        # Vaultwarden's is_signup_disabled() stays false while
        # INVITATIONS_ALLOWED is true, so the web UI offers "Create account"
        # even though the API refuses it. SSO first-login is not affected.
        self.assertEqual(self.service()['environment']['INVITATIONS_ALLOWED'],
                         '${VAULTWARDEN_INVITATIONS_ALLOWED:-false}')

    def test_the_admin_token_is_mounted_as_a_compose_secret(self):
        service = self.service()
        self.assertEqual(service['environment']['ADMIN_TOKEN_FILE'], '/run/secrets/admin_token')
        self.assertEqual(service['secrets'], ['admin_token'])
        self.assertEqual(self.compose()['secrets']['admin_token']['file'],
                         './secrets/admin_token')

    def test_the_healthcheck_uses_the_alive_endpoint(self):
        test = self.service()['healthcheck']['test']
        self.assertIn('/alive', ' '.join(str(part) for part in test))
        self.assertIn('curl', test)

    def test_the_image_uses_the_staged_fixed_version(self):
        image = self.service()['image']
        default = re.search(r'\$\{[A-Z_]+:-([^}]+)\}', image)
        fixed = default.group(1) if default else image
        self.assertEqual(fixed, 'vaultwarden/server:1.37.2')
        self.assertNotIn('latest', image)

    def test_the_lock_pins_the_same_repository_as_compose(self):
        lock = yaml.safe_load((STACK / 'compose.lock.yaml').read_text(encoding='utf-8'))
        self.assertTrue(lock['services']['vaultwarden']['image'].startswith(
            'vaultwarden/server@sha256:'))

    def test_the_sso_environment_matches_the_staging_values(self):
        environment = self.service()['environment']
        for key, value in SSO_EXPECTED.items():
            self.assertEqual(environment[key], value, key)
        self.assertEqual(environment['SSO_AUTHORITY'],
                         'https://auth.apextox.dpdns.org/application/o/vaultwarden/')

    def test_the_oidc_secret_is_injected_by_manage_py(self):
        environment = self.service()['environment']
        self.assertEqual(environment['SSO_CLIENT_ID'], '${SSO_CLIENT_ID:-vaultwarden}')
        self.assertEqual(environment['SSO_CLIENT_SECRET'], '${SSO_CLIENT_SECRET:-}')

    def test_the_env_example_carries_no_secret(self):
        text = (STACK / '.env.example').read_text(encoding='utf-8')
        self.assertNotIn('SSO_CLIENT_SECRET=', text)
        self.assertNotIn('admin_token=', text)
        for key in ('STORAGE_ROOT=', 'VAULTWARDEN_PORT=', 'VAULTWARDEN_SIGNUPS_ALLOWED=',
                    'VAULTWARDEN_INVITATIONS_ALLOWED='):
            self.assertIn(key, text, key)

    def test_the_secrets_directory_stays_out_of_git(self):
        path = str(STACK / 'secrets' / 'admin_token')
        result = subprocess.run(['git', 'check-ignore', '-q', path], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_script_uses_the_standard_library_only(self):
        text = (STACK / 'manage.py').read_text(encoding='utf-8')
        self.assertNotIn('import requests', text)


class ManageTests(unittest.TestCase):
    def project(self):
        directory = Path(tempfile.mkdtemp(prefix='vaultwarden-project-'))
        self.addCleanup(lambda: shutil.rmtree(directory, ignore_errors=True))
        return directory

    def patch_root(self, project):
        patcher = patch.object(manage, 'ROOT', project)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_env(self, project, state):
        (project / '.env').write_text(f'STORAGE_ROOT={state}\n', encoding='utf-8')

    def test_init_creates_the_admin_token_private_and_the_state(self):
        project = self.project()
        state = project.parent / (project.name + '-state')
        self.addCleanup(lambda: shutil.rmtree(state, ignore_errors=True))
        self.patch_root(project)
        (project / '.env.example').write_text(f'STORAGE_ROOT={state}\n', encoding='utf-8')
        manage.init()
        token = project / 'secrets' / 'admin_token'
        self.assertEqual(token.stat().st_mode & 0o777, 0o400)
        self.assertTrue(token.read_text(encoding='utf-8').strip())
        self.assertEqual((project / '.env').stat().st_mode & 0o777, 0o600)
        self.assertTrue((state / 'data').is_dir())

    def test_init_never_regenerates_an_existing_token(self):
        project = self.project()
        state = project.parent / (project.name + '-state')
        self.addCleanup(lambda: shutil.rmtree(state, ignore_errors=True))
        self.patch_root(project)
        (project / '.env.example').write_text(f'STORAGE_ROOT={state}\n', encoding='utf-8')
        token = project / 'secrets' / 'admin_token'
        token.parent.mkdir()
        token.write_text('keep-me\n', encoding='utf-8')
        manage.init()
        self.assertEqual(token.read_text(encoding='utf-8'), 'keep-me\n')

    def test_storage_refuses_a_state_inside_the_project(self):
        project = self.project()
        self.patch_root(project)
        self.write_env(project, project / 'storage')
        with self.assertRaises(ValueError):
            manage.storage()

    def test_the_oidc_client_file_is_read_from_the_identity_secret(self):
        project = self.project()
        self.patch_root(project)
        secrets = project / 'secrets'
        secrets.mkdir()
        (secrets / 'oidc_client.json').write_text(
            json.dumps({'client_id': 'vaultwarden', 'client_secret': 's3cret'}))
        self.assertEqual(manage.oidc_client(),
                         {'client_id': 'vaultwarden', 'client_secret': 's3cret'})

    def test_compose_receives_the_oidc_secret_from_the_environment(self):
        project = self.project()
        self.patch_root(project)
        secrets = project / 'secrets'
        secrets.mkdir()
        (secrets / 'oidc_client.json').write_text(
            json.dumps({'client_id': 'vaultwarden', 'client_secret': 's3cret'}))
        with patch.object(manage, 'run') as run:
            manage.compose('config')
        environment = run.call_args.kwargs['env']
        self.assertEqual(environment['SSO_CLIENT_ID'], 'vaultwarden')
        self.assertEqual(environment['SSO_CLIENT_SECRET'], 's3cret')

    def test_backup_separates_state_and_deployment(self):
        project = self.project()
        state = project.parent / (project.name + '-state')
        destination = project.parent / (project.name + '-backups')
        self.addCleanup(lambda: shutil.rmtree(state, ignore_errors=True))
        self.addCleanup(lambda: shutil.rmtree(destination, ignore_errors=True))
        self.patch_root(project)
        self.write_env(project, state)
        (state / 'data').mkdir(parents=True)
        (state / 'data' / 'db.sqlite3').write_text('data', encoding='utf-8')
        (project / 'secrets').mkdir()
        (project / 'secrets' / 'admin_token').write_text('t', encoding='utf-8')
        for name in ('compose.yaml', 'compose.lock.yaml', '.env.example', 'manage.py'):
            (project / name).write_text('x', encoding='utf-8')
        with patch.object(manage, 'compose',
                          return_value=SimpleNamespace(stdout='vaultwarden\n')) as compose:
            with patch.object(manage, 'run') as run:
                manage.backup(destination)
        archived = [' '.join(str(part) for part in call.args[0]) for call in run.call_args_list]
        self.assertTrue(any('state.tar' in command for command in archived))
        self.assertTrue(any('deployment.tar' in command for command in archived))
        self.assertTrue(compose.called)
        backups = list(destination.iterdir())
        self.assertEqual(len(backups), 1)
        manifest = json.loads((backups[0] / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['storage_root'], str(state / 'data'))
        self.assertIn('master password', manifest['notes'])

    def test_backup_refuses_a_destination_inside_the_state(self):
        project = self.project()
        self.patch_root(project)
        self.write_env(project, project / '..' / (project.name + '-state'))
        with self.assertRaises(ValueError):
            manage.backup(project.parent / (project.name + '-state') / 'data' / 'backups')


class IacTests(unittest.TestCase):
    def test_the_playbook_deploys_vaultwarden_behind_tls(self):
        play = yaml.safe_load((ROOT / 'platform/ansible/vaultwarden.yml').read_text(encoding='utf-8'))
        self.assertEqual(play[0]['hosts'], 'netbox_bootstrap')
        roles = play[0]['roles']
        self.assertLess(roles.index('docker'), roles.index('vaultwarden'))
        # tls_proxy first: Caddy serves https://vault.<zone> and owns the cert.
        self.assertLess(roles.index('tls_proxy'), roles.index('vaultwarden'))

    def test_the_role_reads_the_identity_client_and_manages_the_stack(self):
        defaults = yaml.safe_load(
            (ROOT / 'platform/ansible/roles/vaultwarden/defaults/main.yml').read_text(encoding='utf-8'))
        self.assertEqual(defaults['vaultwarden_project_dir'], '/opt/services/vaultwarden')
        self.assertEqual(defaults['vaultwarden_storage_root'], '/srv/services/vaultwarden')
        self.assertEqual(defaults['vaultwarden_port'], 8222)
        self.assertEqual(defaults['vaultwarden_tz'], 'Asia/Tokyo')
        self.assertEqual(defaults['vaultwarden_oidc_credentials_path'],
                         '/opt/identity-stack/secrets/oidc-vaultwarden.json')
        tasks = yaml.safe_load(
            (ROOT / 'platform/ansible/roles/vaultwarden/tasks/main.yml').read_text(encoding='utf-8'))
        serialized = json.dumps(tasks)
        for token in ('compose.yaml', 'compose.lock.yaml', 'manage.py', '.env.example',
                      'oidc_client.json'):
            self.assertIn(token, serialized, token)
        commands = {tuple(task['ansible.builtin.command']['argv'])
                    for task in tasks if 'ansible.builtin.command' in task}
        for action in ('init', 'lock', 'up'):
            self.assertIn(('python3', 'manage.py', action), commands, action)
        templates = [task for task in tasks if 'ansible.builtin.template' in task]
        self.assertEqual(len(templates), 1)
        self.assertEqual(templates[0]['ansible.builtin.template']['src'], 'env.j2')
        self.assertEqual(templates[0]['ansible.builtin.template']['dest'],
                         '{{ vaultwarden_project_dir }}/.env')
        environment = (ROOT / 'platform/ansible/roles/vaultwarden/templates/env.j2').read_text(
            encoding='utf-8')
        for key in ('STORAGE_ROOT=', 'VAULTWARDEN_PORT=', 'VAULTWARDEN_SIGNUPS_ALLOWED=',
                    'VAULTWARDEN_INVITATIONS_ALLOWED=', 'TZ='):
            self.assertIn(key, environment, key)
        slurp = [task for task in tasks if 'ansible.builtin.slurp' in task]
        self.assertEqual(len(slurp), 1)
        self.assertEqual(slurp[0]['ansible.builtin.slurp']['src'],
                         '{{ vaultwarden_oidc_credentials_path }}')
        self.assertTrue(slurp[0]['no_log'])
        assertions = [task for task in tasks if 'ansible.builtin.assert' in task]
        self.assertTrue(assertions)
        for task in assertions:
            self.assertTrue(task.get('no_log'), task['name'])
        installs = [task for task in tasks if task.get('ansible.builtin.copy', {}).get('dest', '')
                    .endswith('secrets/oidc_client.json')]
        self.assertEqual(len(installs), 1)
        self.assertTrue(installs[0]['no_log'])

    def test_dns_declares_vault_on_services_01(self):
        dns = yaml.safe_load((ROOT / 'platform/terraform/dns.yaml').read_text(encoding='utf-8'))
        record = dns['records']['vault']
        self.assertEqual(record['host'], 'services-01')
        self.assertEqual(record['upstream'], '127.0.0.1:8222')
        self.assertIn('Vaultwarden', record['description'])

    def test_identity_offers_the_vaultwarden_client(self):
        spec = importlib.util.spec_from_file_location(
            'identity_configure', ROOT / 'stacks/identity/configure.py')
        identity = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(identity)
        self.assertEqual(identity.VAULTWARDEN, 'vaultwarden')
        self.assertEqual(identity.VAULTWARDEN_HOST, 'vault')
        self.assertEqual(identity.vaultwarden_redirect('apextox.dpdns.org'), REDIRECT)
        body = identity.oidc_provider_body(
            identity.VAULTWARDEN, REDIRECT,
            {identity.AUTHORIZATION_FLOW: 'auth', identity.INVALIDATION_FLOW: 'inval'},
            ['mapping'], 'key', {'client_id': 'vaultwarden', 'client_secret': 's'})
        self.assertEqual(body['sub_mode'], 'user_uuid')
        self.assertIn('refresh_token', body['grant_types'])
        self.assertEqual(body['redirect_uris'][0]['url'], REDIRECT)

    def test_the_identity_credential_is_created_private_and_reused(self):
        spec = importlib.util.spec_from_file_location(
            'identity_configure_creds', ROOT / 'stacks/identity/configure.py')
        identity = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(identity)
        directory = Path(tempfile.mkdtemp(prefix='identity-vaultwarden-'))
        self.addCleanup(lambda: shutil.rmtree(directory, ignore_errors=True))
        with patch.object(identity, 'ROOT', directory):
            first = identity.vaultwarden_credential()
            path = directory / 'secrets' / 'oidc-vaultwarden.json'
            self.assertEqual(first['client_id'], 'vaultwarden')
            self.assertTrue(first['client_secret'])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(identity.vaultwarden_credential(), first)


if __name__ == '__main__':
    unittest.main()
