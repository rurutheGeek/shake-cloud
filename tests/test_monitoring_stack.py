"""Guard the monitoring stack: scope, reachability targets and secret handling.

The stack runs on its own VM and is the only place that sees the Proxmox token
and the UPS. A test that let a service port escape to 0.0.0.0, or that let the
blackbox targets drift away from dns.yaml, would be worse than no test.
"""
import importlib.util
import json
from pathlib import Path
import string
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/monitoring'
DNS = yaml.safe_load((ROOT / 'platform/terraform/dns.yaml').read_text(encoding='utf-8'))
ZONE = DNS['zone']
# play.apextox.dpdns.org is served by game1 and is not in dns.yaml yet.
KNOWN_OUTSIDE_DNS = {'play.' + ZONE}


def load(path):
    return yaml.safe_load(path.read_text(encoding='utf-8'))


class ComposeTests(unittest.TestCase):
    def compose(self):
        return load(STACK / 'compose.yaml')

    def test_the_expected_services_are_present(self):
        services = set(self.compose()['services'])
        self.assertEqual(services, {'prometheus', 'alertmanager', 'grafana',
                                    'blackbox', 'pve-exporter', 'nut-exporter', 'peanut'})

    def test_every_published_port_stays_on_loopback(self):
        for name, service in self.compose()['services'].items():
            for mapping in service.get('ports', []):
                self.assertTrue(mapping.startswith('${BIND_ADDRESS:-127.0.0.1}:'), f'{name}: {mapping}')

    def test_the_secret_encryption_values_are_not_in_env_example(self):
        text = (STACK / '.env.example').read_text(encoding='utf-8')
        for forbidden in ('GRAFANA_ADMIN_PASSWORD=', 'NUT_PASSWORD=', 'GRAFANA_OIDC_CLIENT_SECRET='):
            self.assertNotIn(forbidden, text)


class PrometheusTests(unittest.TestCase):
    def test_blackbox_covers_every_service_record_in_dns(self):
        targets = load(STACK / 'prometheus/blackbox-targets.yml')
        actual = {url.split('//', 1)[1].split('/', 1)[0].split(':')[0]
                  for group in targets for url in group['targets']}
        expected = {f'{name}.{ZONE}' for name, record in DNS['records'].items()
                    if 'upstream' in record}
        self.assertTrue(expected <= actual, expected - actual)
        # Records without an upstream (pve, awx) and the game portal are also probed.
        allowed = {f'{name}.{ZONE}' for name in DNS['records']} | KNOWN_OUTSIDE_DNS
        for host in actual - expected:
            self.assertIn(host, allowed, host)

    def test_every_blackbox_target_is_https(self):
        targets = load(STACK / 'prometheus/blackbox-targets.yml')
        for group in targets:
            for url in group['targets']:
                self.assertTrue(url.startswith('https://'), url)

    def test_the_alert_rules_cover_probes_and_certificates(self):
        rules = load(STACK / 'prometheus/alerts.yml')
        expressions = [rule['expr'] for group in rules['groups'] for rule in group['rules']]
        self.assertTrue(any('probe_success' in expr for expr in expressions))
        self.assertTrue(any('probe_ssl_earliest_cert_expiry' in expr for expr in expressions))

    def test_prometheus_sends_alerts_to_alertmanager(self):
        config = load(STACK / 'prometheus/prometheus.yml')
        self.assertEqual(config['alerting']['alertmanagers'][0]['static_configs'][0]['targets'],
                         ['alertmanager:9093'])

    def test_the_nut_job_reads_the_ups_metrics_path(self):
        config = load(STACK / 'prometheus/prometheus.yml')
        job = next(j for j in config['scrape_configs'] if j['job_name'] == 'nut')
        self.assertEqual(job['metrics_path'], '/ups_metrics')

    def test_the_alert_rules_cover_the_ups(self):
        rules = load(STACK / 'prometheus/alerts.yml')
        expressions = [rule['expr'] for group in rules['groups'] for rule in group['rules']]
        self.assertTrue(any('network_ups_tools_ups_status' in expr for expr in expressions))

    def test_the_alert_rules_cover_the_node_exporters(self):
        # 5台から node_* を集めているのに規則が無い、を防ぐ。
        rules = load(STACK / 'prometheus/alerts.yml')
        alerts = {rule['alert']: rule for group in rules['groups'] for rule in group['rules']}
        for name, metric in (
                ('NodeExporterDown', 'up{job="node"}'),
                ('NodeFilesystemAlmostFull', 'node_filesystem_avail_bytes'),
                ('NodeMemoryLow', 'node_memory_MemAvailable_bytes'),
                ('NodeOOMKill', 'node_vmstat_oom_kill'),
                ('NodeSystemdUnitFailed', 'node_systemd_unit_state'),
                ('NodeRebooted', 'node_boot_time_seconds')):
            self.assertIn(name, alerts)
            self.assertIn(metric, alerts[name]['expr'], name)

    def test_the_alert_rules_cover_the_backup_age_and_absence(self):
        rules = load(STACK / 'prometheus/alerts.yml')
        alerts = {rule['alert']: rule for group in rules['groups'] for rule in group['rules']}
        self.assertIn('backup_last_success_timestamp_seconds', alerts['CloudBackupStale']['expr'])
        self.assertIn('absent(', alerts['CloudBackupMetricMissing']['expr'])
        self.assertTrue(alerts['CloudBackupStale']['for'] == '15m')

    def test_the_watchdog_alert_is_always_firing(self):
        rules = load(STACK / 'prometheus/alerts.yml')
        alerts = {rule['alert']: rule for group in rules['groups'] for rule in group['rules']}
        self.assertEqual(alerts['Watchdog']['expr'], 'vector(1)')
        self.assertEqual(alerts['Watchdog']['labels']['severity'], 'none')


class AlertmanagerTests(unittest.TestCase):
    def test_the_deadman_switch_is_rendered_only_with_a_ping_url(self):
        spec = importlib.util.spec_from_file_location('monitoring_manage', STACK / 'manage.py')
        monitoring = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(monitoring)
        template = (STACK / 'alertmanager/alertmanager.yml.template').read_text(encoding='utf-8')
        self.assertIn('${WATCHDOG_PING_URL}', template)
        self.assertIn('alertname = Watchdog', template)
        configured = string.Template(template).substitute(
            {'WATCHDOG_PING_URL': 'https://hc-ping.com/example', 'ALERT_EMAIL': 'a@example.com',
             'SMTP_HOST': 'smtp', 'SMTP_PORT': '587', 'SMTP_FROM': 'f@example.com',
             'SMTP_USERNAME': 'u', 'SMTP_PASSWORD': 'p', 'SMTP_REQUIRE_TLS': 'true'})
        self.assertIn('hc-ping.com', configured)
        disabled = monitoring.without_watchdog(configured)
        self.assertNotIn('hc-ping.com', disabled)
        # 宛先は残す。Watchdog がメールへ流れると12時間ごとに誤通知になる。
        self.assertIn('name: deadman', disabled)
        self.assertIn('alertname = Watchdog', disabled)
        self.assertIn('name: email', disabled)


class GrafanaTests(unittest.TestCase):
    def test_the_datasource_uid_matches_the_dashboard(self):
        datasource = load(STACK / 'grafana/provisioning/datasources/prometheus.yml')
        uid = datasource['datasources'][0]['uid']
        dashboard = json.loads(
            (STACK / 'grafana/provisioning/dashboards/overview.json').read_text(encoding='utf-8'))
        for panel in dashboard['panels']:
            self.assertEqual(panel['datasource']['uid'], uid, panel['title'])

    def test_the_dashboard_provider_points_at_the_mounted_path(self):
        provider = load(STACK / 'grafana/provisioning/dashboards/default.yml')
        self.assertEqual(provider['providers'][0]['options']['path'],
                         '/etc/grafana/provisioning/dashboards')

    def test_the_dashboard_shows_the_ups(self):
        dashboard = json.loads(
            (STACK / 'grafana/provisioning/dashboards/overview.json').read_text(encoding='utf-8'))
        titles = [panel['title'] for panel in dashboard['panels']]
        self.assertTrue(any('UPS' in title for title in titles), titles)


class IdentityClientTests(unittest.TestCase):
    def test_grafana_gets_an_oidc_redirect(self):
        spec = importlib.util.spec_from_file_location(
            'identity_configure', ROOT / 'stacks/identity/configure.py')
        identity = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(identity)
        self.assertEqual(identity.grafana_redirect(ZONE),
                         f'https://grafana.{ZONE}/login/generic_oauth')


if __name__ == '__main__':
    unittest.main()
