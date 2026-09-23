"""Guard the LibreSpeed stack's isolation, local-only measurement and wiring.

LibreSpeed is its own Compose project on services-01. The browser measures the
path between the device that opens the page and services-01, so the stack must
stay loopback-only behind Caddy and must not pretend to measure the internet
line. A test that exposed the port on the LAN, that let the stats password into
.env, or that lost the pinned digest would be worse than no test.
"""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/librespeed'
SPEC = importlib.util.spec_from_file_location('librespeed_manage', STACK / 'manage.py')
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)

PUBLIC_URL = 'https://speed.apextox.dpdns.org'


class StackTests(unittest.TestCase):
    def compose(self):
        return yaml.safe_load((STACK / 'compose.yaml').read_text(encoding='utf-8'))

    def service(self):
        return self.compose()['services']['librespeed']

    def test_the_project_is_librespeed_alone(self):
        compose = self.compose()
        self.assertEqual(compose['name'], 'librespeed')
        self.assertEqual(list(compose['services']), ['librespeed'])

    def test_the_old_hub_services_are_not_copied_in(self):
        services = set(self.compose()['services'])
        for name in ('authentik', 'caddy', 'postgresql', 'docs', 'media-hub'):
            self.assertNotIn(name, services, name)

    def test_the_service_is_loopback_only(self):
        ports = self.service()['ports']
        self.assertEqual(len(ports), 1)
        self.assertIn('127.0.0.1', ports[0])
        self.assertIn('${LIBRESPEED_PORT:-8300}', ports[0])

    def test_the_state_lives_outside_the_deployment_directory(self):
        volumes = self.service()['volumes']
        self.assertEqual(volumes,
                         ['${STORAGE_ROOT:-/srv/services/librespeed}/database:/database'])

    def test_the_measurement_is_device_to_server_not_the_internet_line(self):
        environment = self.service()['environment']
        self.assertEqual(environment['MODE'], 'standalone')
        # 端末↔サーバの計測なので、ISP・距離の外部問い合わせは使わない。
        self.assertEqual(environment['DISABLE_IPINFO'], 'true')
        self.assertEqual(environment['TAGLINE'], '端末 ↔ services-01 の実効速度')

    def test_telemetry_is_local_sqlite_with_ip_redaction(self):
        environment = self.service()['environment']
        self.assertEqual(environment['TELEMETRY'], 'true')
        self.assertEqual(environment['DB_TYPE'], 'sqlite')
        self.assertEqual(environment['REDACT_IP_ADDRESSES'], 'true')

    def test_the_stats_password_is_injected_by_manage_py_and_required(self):
        password = self.service()['environment']['PASSWORD']
        self.assertEqual(password, '${LIBRESPEED_STATS_PASSWORD:?run manage.py up}')
        self.assertIn(':?', password)

    def test_the_healthcheck_reads_the_front_page(self):
        test = self.service()['healthcheck']['test']
        self.assertIn('curl', test)
        self.assertIn('http://127.0.0.1:8080/', ' '.join(str(part) for part in test))

    def test_the_image_uses_the_staged_fixed_version(self):
        image = self.service()['image']
        self.assertEqual(
            image,
            '${LIBRESPEED_IMAGE:-ghcr.io/librespeed/speedtest}:${LIBRESPEED_TAG:-6.2.0}')
        self.assertNotIn('latest', image)

    def test_the_lock_pins_the_same_repository_as_compose(self):
        lock = json.loads((STACK / 'compose.lock.yaml').read_text(encoding='utf-8'))
        self.assertTrue(lock['services']['librespeed']['image'].startswith(
            'ghcr.io/librespeed/speedtest@sha256:'))

    def test_the_env_example_carries_no_secret(self):
        text = (STACK / '.env.example').read_text(encoding='utf-8')
        self.assertNotIn('PASSWORD=', text)
        self.assertNotIn('stats_password=', text)
        for key in ('STORAGE_ROOT=', 'LIBRESPEED_PORT=', 'TZ='):
            self.assertIn(key, text, key)

    def test_the_secrets_directory_stays_out_of_git(self):
        path = str(STACK / 'secrets' / 'stats_password')
        result = subprocess.run(['git', 'check-ignore', '-q', path], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_script_uses_the_standard_library_only(self):
        text = (STACK / 'manage.py').read_text(encoding='utf-8')
        self.assertNotIn('import requests', text)


class ManageTests(unittest.TestCase):
    def project(self):
        directory = Path(tempfile.mkdtemp(prefix='librespeed-project-'))
        self.addCleanup(lambda: shutil.rmtree(directory, ignore_errors=True))
        return directory

    def patch_root(self, project):
        patcher = patch.object(manage, 'ROOT', project)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_env(self, project, state):
        (project / '.env').write_text(f'STORAGE_ROOT={state}\n', encoding='utf-8')

    def test_init_creates_the_stats_password_private_and_the_state(self):
        project = self.project()
        state = project.parent / (project.name + '-state')
        self.addCleanup(lambda: shutil.rmtree(state, ignore_errors=True))
        self.patch_root(project)
        (project / '.env.example').write_text(f'STORAGE_ROOT={state}\n', encoding='utf-8')
        manage.init()
        password = project / 'secrets' / 'stats_password'
        self.assertEqual(password.stat().st_mode & 0o777, 0o400)
        self.assertTrue(password.read_text(encoding='utf-8').strip())
        self.assertEqual((project / '.env').stat().st_mode & 0o777, 0o600)
        self.assertTrue((state / 'database').is_dir())

    def test_init_never_regenerates_an_existing_password(self):
        project = self.project()
        state = project.parent / (project.name + '-state')
        self.addCleanup(lambda: shutil.rmtree(state, ignore_errors=True))
        self.patch_root(project)
        (project / '.env.example').write_text(f'STORAGE_ROOT={state}\n', encoding='utf-8')
        password = project / 'secrets' / 'stats_password'
        password.parent.mkdir()
        password.write_text('keep-me\n', encoding='utf-8')
        manage.init()
        self.assertEqual(password.read_text(encoding='utf-8'), 'keep-me\n')

    def test_storage_refuses_a_state_inside_the_project(self):
        project = self.project()
        self.patch_root(project)
        self.write_env(project, project / 'storage')
        with self.assertRaises(ValueError):
            manage.storage()

    def test_compose_receives_the_stats_password_from_the_environment(self):
        project = self.project()
        self.patch_root(project)
        secrets = project / 'secrets'
        secrets.mkdir()
        (secrets / 'stats_password').write_text('s3cret\n', encoding='utf-8')
        with patch.object(manage, 'run') as run:
            manage.compose('config')
        environment = run.call_args.kwargs['env']
        self.assertEqual(environment['LIBRESPEED_STATS_PASSWORD'], 's3cret')

    def test_backup_separates_state_and_deployment(self):
        project = self.project()
        state = project.parent / (project.name + '-state')
        destination = project.parent / (project.name + '-backups')
        self.addCleanup(lambda: shutil.rmtree(state, ignore_errors=True))
        self.addCleanup(lambda: shutil.rmtree(destination, ignore_errors=True))
        self.patch_root(project)
        self.write_env(project, state)
        (state / 'database').mkdir(parents=True)
        (state / 'database' / 'db.sql').write_text('data', encoding='utf-8')
        (project / 'secrets').mkdir()
        (project / 'secrets' / 'stats_password').write_text('t', encoding='utf-8')
        for name in ('compose.yaml', 'compose.lock.yaml', '.env.example', 'manage.py'):
            (project / name).write_text('x', encoding='utf-8')
        with patch.object(manage, 'compose',
                          return_value=SimpleNamespace(stdout='librespeed\n')) as compose:
            with patch.object(manage, 'run') as run:
                manage.backup(destination)
        archived = [' '.join(str(part) for part in call.args[0]) for call in run.call_args_list]
        self.assertTrue(any('state.tar' in command for command in archived))
        self.assertTrue(any('deployment.tar' in command for command in archived))
        self.assertTrue(compose.called)
        backups = list(destination.iterdir())
        self.assertEqual(len(backups), 1)
        manifest = json.loads((backups[0] / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['storage_root'], str(state / 'database'))
        self.assertIn('test history', manifest['notes'])

    def test_backup_refuses_a_destination_inside_the_state(self):
        project = self.project()
        self.patch_root(project)
        self.write_env(project, project / '..' / (project.name + '-state'))
        with self.assertRaises(ValueError):
            manage.backup(project.parent / (project.name + '-state') / 'database' / 'backups')


class IacTests(unittest.TestCase):
    def test_the_playbook_deploys_librespeed_behind_tls(self):
        play = yaml.safe_load((ROOT / 'platform/ansible/librespeed.yml').read_text(encoding='utf-8'))
        self.assertEqual(play[0]['hosts'], 'netbox_bootstrap')
        roles = play[0]['roles']
        self.assertLess(roles.index('docker'), roles.index('librespeed'))
        # tls_proxy first: Caddy serves https://speed.<zone> and owns the cert.
        self.assertLess(roles.index('tls_proxy'), roles.index('librespeed'))

    def test_the_role_manages_the_stack(self):
        defaults = yaml.safe_load(
            (ROOT / 'platform/ansible/roles/librespeed/defaults/main.yml').read_text(encoding='utf-8'))
        self.assertEqual(defaults['librespeed_project_dir'], '/opt/services/librespeed')
        self.assertEqual(defaults['librespeed_storage_root'], '/srv/services/librespeed')
        self.assertEqual(defaults['librespeed_port'], 8300)
        self.assertEqual(defaults['librespeed_tz'], 'Asia/Tokyo')
        self.assertEqual(defaults['librespeed_public_url'], 'https://speed.{{ librespeed_dns.zone }}')
        tasks = yaml.safe_load(
            (ROOT / 'platform/ansible/roles/librespeed/tasks/main.yml').read_text(encoding='utf-8'))
        serialized = json.dumps(tasks)
        for token in ('compose.yaml', 'compose.lock.yaml', 'manage.py', '.env.example'):
            self.assertIn(token, serialized, token)
        commands = {tuple(task['ansible.builtin.command']['argv'])
                    for task in tasks if 'ansible.builtin.command' in task}
        for action in ('init', 'lock', 'up'):
            self.assertIn(('python3', 'manage.py', action), commands, action)
        templates = [task for task in tasks if 'ansible.builtin.template' in task]
        self.assertEqual(len(templates), 1)
        self.assertEqual(templates[0]['ansible.builtin.template']['src'], 'env.j2')
        self.assertEqual(templates[0]['ansible.builtin.template']['dest'],
                         '{{ librespeed_project_dir }}/.env')
        environment = (ROOT / 'platform/ansible/roles/librespeed/templates/env.j2').read_text(
            encoding='utf-8')
        for key in ('STORAGE_ROOT=', 'LIBRESPEED_PORT=', 'TZ='):
            self.assertIn(key, environment, key)

    def test_dns_declares_speed_on_services_01(self):
        dns = yaml.safe_load((ROOT / 'platform/terraform/dns.yaml').read_text(encoding='utf-8'))
        record = dns['records']['speed']
        self.assertEqual(record['host'], 'services-01')
        self.assertEqual(record['upstream'], '127.0.0.1:8300')
        self.assertIn('LibreSpeed', record['description'])

    def test_homarr_offers_the_speed_tile(self):
        apps = json.loads((ROOT / 'stacks/homarr/apps.json').read_text(encoding='utf-8'))
        tile = next(row for row in apps if row['href'] == PUBLIC_URL)
        self.assertEqual(tile['name'], 'LibreSpeed')
        self.assertIn('librespeed.svg', tile['iconUrl'])
        self.assertEqual(tile['pingUrl'], PUBLIC_URL + '/')


if __name__ == '__main__':
    unittest.main()
