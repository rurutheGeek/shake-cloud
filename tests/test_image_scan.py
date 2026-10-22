"""Guard the daily image scan (Trivy plus the runtime version check).

The scan only helps if it sees every pinned image and if a runtime built from
source (PHP in the official images, missed by Trivy) is flagged on the day of a
security release. Nothing here touches a registry or runs Trivy; only
`ansible-playbook --syntax-check` runs.
"""
import json
import unittest
from pathlib import Path

import yaml

from support import load_module, read, role_task, scratch_dir, syntax_check

ROOT = Path(__file__).resolve().parents[1]
ANSIBLE = ROOT / 'platform/ansible'
ROLE = ANSIBLE / 'roles/image_scan'
SCRIPT = ROLE / 'files/image-scan.py'
TASKS = yaml.safe_load(read(ROLE / 'tasks/main.yml'))
DEFAULTS = yaml.safe_load(read(ROLE / 'defaults/main.yml'))
scan = load_module(SCRIPT, 'image_scan')

PHP_FEED = {'8': {
    '8.4': {'version': '8.4.27', 'tags': ['security']},
    '8.3': {'version': '8.3.36', 'tags': []},
    '8.2': {'version': '8.2.35', 'tags': ['security']},
}}
NODE_FEED = [
    {'version': 'v22.21.0', 'security': False},
    {'version': 'v22.20.1', 'security': True},
    {'version': 'v22.20.0', 'security': False},
    {'version': 'v24.3.0', 'security': False},
]
PYTHON_FEED = [
    {'cycle': '3.13', 'latest': '3.13.9', 'eol': '2029-10-31'},
    {'cycle': '3.8', 'latest': '3.8.20', 'eol': '2024-10-07'},
]


class CollectTests(unittest.TestCase):
    def test_every_lock_digest_and_shipped_base_image_is_listed(self):
        root = scratch_dir()
        (root / 'stacks/a').mkdir(parents=True)
        (root / 'stacks/a/compose.lock.yaml').write_text(
            'services:\n  web:\n    image: nextcloud@sha256:' + 'a' * 64 + '\n')
        (root / 'stacks/b').mkdir(parents=True)
        (root / 'stacks/b/compose.lock.yaml').write_text(json.dumps(
            {'services': {'db': {'image': 'postgres@sha256:' + 'b' * 64}}}))
        (root / 'stacks/b/Dockerfile').write_text(
            'FROM golang:1.27@sha256:' + 'c' * 64 + ' AS build\n'
            'FROM python:3.13-slim@sha256:' + 'd' * 64 + '\n')
        images = {item['image']: item['sources'] for item in scan.collect(root)}
        self.assertEqual(images, {
            'nextcloud@sha256:' + 'a' * 64: ['stacks/a/compose.lock.yaml'],
            'postgres@sha256:' + 'b' * 64: ['stacks/b/compose.lock.yaml'],
            # The build stage never ships, so it is not scanned.
            'python:3.13-slim@sha256:' + 'd' * 64: ['stacks/b/Dockerfile'],
        })

    def test_the_repository_yields_the_php_images(self):
        images = [item['image'] for item in scan.collect(ROOT)]
        for name in ('nextcloud@', 'freshrss/freshrss@', 'adminer@', 'ghcr.io/librespeed/speedtest@'):
            self.assertTrue(any(image.startswith(name) for image in images), name)


class ReferenceTests(unittest.TestCase):
    def test_docker_hub_and_other_registries(self):
        digest = 'sha256:' + 'e' * 64
        self.assertEqual(scan.parse_ref('nextcloud@' + digest),
                         ('registry-1.docker.io', 'library/nextcloud', digest))
        self.assertEqual(scan.parse_ref('freshrss/freshrss:latest'),
                         ('registry-1.docker.io', 'freshrss/freshrss', 'latest'))
        self.assertEqual(scan.parse_ref('ghcr.io/librespeed/speedtest:6.3.1@' + digest),
                         ('ghcr.io', 'librespeed/speedtest', digest))
        self.assertEqual(scan.parse_ref('localhost:5000/app'), ('localhost:5000', 'app', 'latest'))

    def test_the_wanted_platform_is_chosen_from_an_index(self):
        manifests = [
            {'digest': 'att', 'platform': {'os': 'unknown', 'architecture': 'unknown'}},
            {'digest': 'arm', 'platform': {'os': 'linux', 'architecture': 'arm64'}},
            {'digest': 'amd', 'platform': {'os': 'linux', 'architecture': 'amd64'}},
        ]
        self.assertEqual(scan.pick_platform(manifests, 'linux/amd64')['digest'], 'amd')
        self.assertEqual(scan.pick_platform(manifests[:2], 'linux/amd64')['digest'], 'arm')


class RuntimeTests(unittest.TestCase):
    def test_php2shell_is_a_security_release_for_the_old_images(self):
        self.assertEqual(scan.runtime_status('php', '8.4.25', PHP_FEED), ('security', '8.4.27'))
        self.assertEqual(scan.runtime_status('php', '8.4.27', PHP_FEED), ('current', '8.4.27'))
        self.assertEqual(scan.runtime_status('php', '8.3.30', PHP_FEED), ('update', '8.3.36'))
        self.assertEqual(scan.runtime_status('php', '8.1.34', PHP_FEED), ('eol', ''))

    def test_node_security_releases_count_only_within_the_major(self):
        self.assertEqual(scan.runtime_status('node', '22.20.0', NODE_FEED), ('security', '22.21.0'))
        self.assertEqual(scan.runtime_status('node', '22.20.1', NODE_FEED), ('update', '22.21.0'))
        self.assertEqual(scan.runtime_status('node', '24.3.0', NODE_FEED), ('current', '24.3.0'))

    def test_python_patch_and_end_of_life(self):
        self.assertEqual(scan.runtime_status('python', '3.13.7', PYTHON_FEED), ('update', '3.13.9'))
        self.assertEqual(scan.runtime_status('python', '3.8.20', PYTHON_FEED), ('eol', '3.8.20'))

    def test_runtimes_come_from_the_image_environment(self):
        config = {'config': {'Env': ['PATH=/usr/bin', 'PHP_VERSION=8.4.25', 'PHPIZE_DEPS=x']}}
        self.assertEqual(scan.runtimes_of(config), {'php': '8.4.25'})


class MetricTests(unittest.TestCase):
    def test_only_fixed_critical_findings_are_kept(self):
        report = {'Results': [{'Vulnerabilities': [
            {'VulnerabilityID': 'CVE-1', 'PkgName': 'libc', 'InstalledVersion': '1',
             'FixedVersion': '2', 'Severity': 'CRITICAL'},
            {'VulnerabilityID': 'CVE-2', 'PkgName': 'zlib', 'InstalledVersion': '1',
             'Severity': 'CRITICAL'},
            {'VulnerabilityID': 'CVE-3', 'PkgName': 'curl', 'InstalledVersion': '1',
             'FixedVersion': '2', 'Severity': 'HIGH'},
        ]}]}
        self.assertEqual(scan.critical_findings(report), [('CVE-1', 'libc', '1', '2')])

    def test_the_textfile_carries_what_the_alerts_read(self):
        images = [
            {'image': 'nextcloud@sha256:' + 'a' * 64, 'sources': ['stacks/media/nextcloud/compose.lock.yaml'],
             'critical': [('CVE-1', 'libc', '1', '2')],
             'runtimes': {'php': ('8.4.25', 'security', '8.4.27')}},
            {'image': 'broken:1', 'sources': ['x/Dockerfile'], 'error': 'HTTPError'},
        ]
        text = scan.render(images, 100, 160)
        self.assertIn('shakecloud_image_scan_last_success_timestamp_seconds 160', text)
        self.assertIn('shakecloud_image_critical_vulnerabilities{image="nextcloud@aaaaaaaaaaaa",'
                      'source="stacks/media/nextcloud/compose.lock.yaml"} 1', text)
        self.assertIn('runtime="php",installed="8.4.25",latest="8.4.27",status="security"} 1', text)
        self.assertIn('shakecloud_image_scan_error{image="broken:1",source="x/Dockerfile",reason="HTTPError"} 1', text)

    def test_every_metric_the_alerts_use_is_written(self):
        rules = yaml.safe_load(read(ROOT / 'stacks/monitoring/prometheus/alerts.yml'))
        group = next(g for g in rules['groups'] if g['name'] == 'image_scan')
        text = scan.render([], 0, 1)
        for rule in group['rules']:
            for metric in ('shakecloud_image_critical_vulnerabilities', 'shakecloud_image_runtime',
                           'shakecloud_image_scan_error', 'shakecloud_image_scan_last_success_timestamp_seconds'):
                if metric in rule['expr']:
                    self.assertIn(f'# TYPE {metric} gauge', text, rule['alert'])


class RoleTests(unittest.TestCase):
    def test_trivy_is_pinned_and_checked(self):
        download = role_task(TASKS, 'Download Trivy')['ansible.builtin.get_url']
        self.assertIn('image_scan_trivy_version', download['url'])
        self.assertTrue(download['checksum'].startswith('sha256:'))
        self.assertEqual(set(DEFAULTS['image_scan_trivy_sha256']), {'ARM64', '64bit'})

    def test_the_image_list_is_collected_on_the_controller(self):
        task = role_task(TASKS, 'Collect the pinned images')
        self.assertEqual(task['delegate_to'], 'localhost')
        self.assertIn('collect', task['ansible.builtin.command']['argv'])

    def test_the_scan_runs_gently_on_the_monitoring_host(self):
        units = role_task(TASKS, 'Place the scan service and timer')['loop']
        service = next(u for u in units if u['name'] == 'image-scan.service')['content']
        for line in ('Nice=19', 'IOSchedulingClass=idle', 'MemoryMax=1G'):
            self.assertIn(line, service)
        self.assertTrue(DEFAULTS['image_scan_state_dir'].startswith('/srv/'))
        self.assertTrue(DEFAULTS['image_scan_textfile'].startswith('/var/lib/prometheus/node-exporter/'))

    def test_the_dashboard_reads_the_scan_metrics(self):
        dashboard = json.loads(read(ROOT / 'stacks/monitoring/grafana/provisioning/dashboards/image-scan.json'))
        expressions = ' '.join(t['expr'] for p in dashboard['panels'] for t in p.get('targets', []))
        for metric in ('shakecloud_image_vulnerability', 'shakecloud_image_runtime',
                       'shakecloud_image_scan_last_success_timestamp_seconds', 'ALERTS'):
            self.assertIn(metric, expressions)


class SyntaxTests(unittest.TestCase):
    def test_the_playbook_parses(self):
        result = syntax_check(ANSIBLE / 'image-scan.yml')
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
