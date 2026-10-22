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
                                    'blackbox', 'pve-exporter', 'nut-exporter', 'peanut',
                                    'loki', 'alloy', 'canary'})

    def test_every_published_port_stays_on_loopback(self):
        # 例外は Alloy の syslog（1514/udp）だけ。Flint 3 からログを受けるため LAN に開ける。
        for name, service in self.compose()['services'].items():
            for mapping in service.get('ports', []):
                if name == 'alloy' and mapping.endswith(':1514:1514/udp'):
                    continue
                self.assertTrue(mapping.startswith('${BIND_ADDRESS:-127.0.0.1}:'), f'{name}: {mapping}')

    def test_every_service_is_pinned(self):
        import json
        lock = json.loads((STACK / 'compose.lock.yaml').read_text(encoding='utf-8'))['services']
        self.assertEqual(set(lock), set(self.compose()['services']))
        for name, entry in lock.items():
            self.assertIn('@sha256:', entry['image'], name)

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

    def test_the_game_job_scrapes_the_portal_exporter_over_https(self):
        config = load(STACK / 'prometheus/prometheus.yml')
        job = next(j for j in config['scrape_configs'] if j['job_name'] == 'game')
        self.assertEqual(job['scheme'], 'https')
        self.assertEqual(job['metrics_path'], '/metrics')
        self.assertEqual(job['authorization']['credentials_file'],
                         '/etc/prometheus-secrets/game_metrics_token')
        # Caddy は Host ヘッダで振り分ける。IP を target にすると空の 200 が返る。
        self.assertEqual(job['static_configs'][0]['targets'], ['play.apextox.dpdns.org:443'])

    def test_the_game_token_is_mounted_only_into_prometheus(self):
        services = load(STACK / 'compose.yaml')['services']
        self.assertIn(
            './secrets/game_metrics_token:/etc/prometheus-secrets/game_metrics_token:ro',
            services['prometheus']['volumes'])
        for name, service in services.items():
            if name == 'prometheus':
                continue
            self.assertNotIn('game_metrics_token', ' '.join(service.get('volumes', [])))

    def test_the_alert_rules_cover_the_ups(self):
        rules = load(STACK / 'prometheus/alerts.yml')
        expressions = [rule['expr'] for group in rules['groups'] for rule in group['rules']]
        self.assertTrue(any('network_ups_tools_ups_status' in expr for expr in expressions))

    def test_the_alert_rules_cover_the_proxmox_node_memory(self):
        rules = load(STACK / 'prometheus/alerts.yml')
        alerts = {rule['alert']: rule for group in rules['groups'] for rule in group['rules']}
        self.assertIn('pve_memory_usage_bytes', alerts['ProxmoxNodeMemoryHigh']['expr'])
        self.assertIn('pve_memory_size_bytes', alerts['ProxmoxNodeMemoryHigh']['expr'])

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

    def test_the_proxmox_host_is_scraped_for_node_metrics(self):
        # HDD/NVMeのデバイス別I/OとSMARTはホストのnode_exporterからしか取れない。
        targets = load(STACK / 'prometheus/node-targets.yml')
        hosts = {target for group in targets for target in group['targets']}
        self.assertIn('192.168.10.10:9100', hosts)

    def test_the_alert_rules_cover_the_bulk_disk_and_smart(self):
        rules = load(STACK / 'prometheus/alerts.yml')
        alerts = {rule['alert']: rule for group in rules['groups'] for rule in group['rules']}
        for name, metric in (
                ('BulkDiskUnmounted', 'absent(node_filesystem_avail_bytes'),
                ('BulkDiskAlmostFull', 'node_filesystem_avail_bytes'),
                ('SmartDeviceUnhealthy', 'smartmon_device_smart_healthy'),
                ('SmartDeviceInactive', 'smartmon_device_active'),
                ('SmartSectorErrors', 'smartmon_current_pending_sector_raw_value'),
                ('SmartCableErrors', 'smartmon_udma_crc_error_count_raw_value'),
                ('SmartTemperatureHigh', 'smartmon_temperature_celsius_raw_value'),
                ('SmartCollectorStale', 'smartmon_smartctl_run'),
                ('NvmeWearHigh', 'nvme_percentage_used_ratio')):
            self.assertIn(name, alerts)
            self.assertIn(metric, alerts[name]['expr'], name)
        # 汎用の15%規則と /srv/bulk で二重に鳴らさない。
        self.assertIn('mountpoint!="/srv/bulk"', alerts['NodeFilesystemAlmostFull']['expr'])

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
    def manage(self):
        spec = importlib.util.spec_from_file_location('monitoring_manage', STACK / 'manage.py')
        monitoring = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(monitoring)
        return monitoring

    def rendered(self):
        template = (STACK / 'alertmanager/alertmanager.yml.template').read_text(encoding='utf-8')
        return string.Template(template).substitute(WATCHDOG_PING_URL='https://hc-ping.com/example')

    def test_the_deadman_switch_is_rendered_only_with_a_ping_url(self):
        configured = self.rendered()
        self.assertIn('hc-ping.com', configured)
        disabled = self.manage().without_watchdog(configured)
        self.assertNotIn('hc-ping.com', disabled)
        # 宛先は残す。Watchdog が Discord へ流れると 1 時間ごとに誤通知になる。
        self.assertIn('name: deadman', disabled)
        self.assertIn('alertname = Watchdog', disabled)

    def test_alerts_go_to_discord_and_info_goes_nowhere(self):
        config = yaml.safe_load(self.rendered())
        route = config['route']
        self.assertEqual(route['receiver'], 'discord')
        by_matcher = {tuple(r['matchers']): r for r in route['routes']}
        self.assertEqual(by_matcher[('severity = info',)]['receiver'], 'silent')
        self.assertEqual(by_matcher[('severity = critical',)]['repeat_interval'], '4h')
        self.assertEqual(route['repeat_interval'], '24h')
        discord = next(r for r in config['receivers'] if r['name'] == 'discord')['discord_configs'][0]
        # URL は秘密値。設定に直接書かず、ファイルで渡す。
        self.assertEqual(discord['webhook_url_file'], '/etc/alertmanager/discord_webhook_url')
        self.assertTrue(discord['send_resolved'])
        self.assertNotIn('email', self.rendered())

    def test_without_a_webhook_nothing_is_sent(self):
        config = yaml.safe_load(self.manage().without_discord(self.rendered()))
        self.assertNotIn('discord', [r['name'] for r in config['receivers']])
        self.assertEqual(config['route']['receiver'], 'silent')

    def test_every_alert_has_a_known_severity_and_the_texts_the_message_uses(self):
        rules = load(STACK / 'prometheus/alerts.yml')
        for group in rules['groups']:
            for rule in group['rules']:
                if rule['alert'] == 'Watchdog':
                    continue
                self.assertIn(rule['labels']['severity'], ('critical', 'warning', 'info'), rule['alert'])
                for key in ('panel', 'summary', 'description'):
                    self.assertTrue(rule['annotations'].get(key), f"{rule['alert']}: {key}")
                # 「どこ」は通知の文が付ける。IP アドレスを summary に入れない。
                self.assertNotIn('$labels.instance', rule['annotations']['summary'], rule['alert'])

    def test_a_short_outage_does_not_notify(self):
        rules = load(STACK / 'prometheus/alerts.yml')
        alerts = {rule['alert']: rule for group in rules['groups'] for rule in group['rules']}
        for name in ('ServiceProbeFailed', 'NodeExporterDown', 'ProxmoxGuestDown'):
            self.assertEqual(alerts[name]['for'], '10m', name)
        self.assertEqual(alerts['UpsOnBattery']['for'], '5m')

    def test_the_message_template_is_installed_next_to_the_config(self):
        self.assertIn('/etc/alertmanager/notify.tmpl', self.rendered())
        template = (STACK / 'alertmanager/notify.tmpl').read_text(encoding='utf-8')
        for name in ('shake.title', 'shake.message', 'shake.where'):
            self.assertIn(f'define "{name}"', template)


class GrafanaTests(unittest.TestCase):
    def dashboards(self):
        return {path.name: json.loads(path.read_text(encoding='utf-8'))
                for path in sorted((STACK / 'grafana/provisioning/dashboards').glob('*.json'))}

    def test_the_datasource_uid_matches_the_dashboards(self):
        datasource = load(STACK / 'grafana/provisioning/datasources/prometheus.yml')
        uid = datasource['datasources'][0]['uid']
        for name, dashboard in self.dashboards().items():
            for panel in dashboard['panels']:
                self.assertEqual(panel['datasource']['uid'], uid, f'{name}: {panel["title"]}')

    def test_the_dashboard_provider_points_at_the_mounted_path(self):
        provider = load(STACK / 'grafana/provisioning/dashboards/default.yml')
        self.assertEqual(provider['providers'][0]['options']['path'],
                         '/etc/grafana/provisioning/dashboards')

    def test_the_dashboard_shows_the_ups(self):
        dashboard = self.dashboards()['overview.json']
        titles = [panel['title'] for panel in dashboard['panels']]
        self.assertTrue(any('UPS' in title for title in titles), titles)

    def test_the_vm_memory_dashboard_shows_guests_over_time(self):
        dashboard = self.dashboards()['vm-memory.json']
        expressions = [target['expr'] for panel in dashboard['panels'] for target in panel['targets']]
        self.assertTrue(any('pve_memory_usage_bytes' in expr for expr in expressions))
        self.assertTrue(any('pve_memory_size_bytes' in expr for expr in expressions))
        # VMID だけでは人が判断できないので、名前を pve_guest_info から引く。
        self.assertTrue(any('pve_guest_info' in expr for expr in expressions))

    def test_the_host_dashboard_shows_io_and_temperatures(self):
        dashboard = self.dashboards()['host.json']
        expressions = [target['expr'] for panel in dashboard['panels'] for target in panel['targets']]
        for fragment in ('node_disk_read_bytes_total', 'node_disk_written_bytes_total',
                         'node_cpu_scaling_frequency_hertz', 'node_hwmon_temp_celsius',
                         'node_network_receive_bytes_total', 'node_filesystem_avail_bytes'):
            self.assertTrue(any(fragment in expr for expr in expressions), fragment)

    def test_the_storage_dashboard_shows_the_bulk_disk_and_smart(self):
        dashboard = self.dashboards()['storage.json']
        expressions = [target['expr'] for panel in dashboard['panels'] for target in panel['targets']]
        for fragment in ('mountpoint="/srv/bulk"', 'smartmon_device_smart_healthy',
                         'smartmon_temperature_celsius_raw_value',
                         'smartmon_udma_crc_error_count_raw_value',
                         'nvme_percentage_used_ratio', 'pve_disk_usage_bytes',
                         'nvme_data_units_written_total', 'smartmon_load_cycle_count_raw_value',
                         'smartmon_start_stop_count_raw_value'):
            self.assertTrue(any(fragment in expr for expr in expressions), fragment)

    def test_the_overview_links_and_shows_the_bulk_disk(self):
        dashboard = self.dashboards()['overview.json']
        titles = [panel['title'] for panel in dashboard['panels']]
        self.assertIn('6TB HDD 使用率', titles)
        self.assertIn('6TB HDD SMART', titles)
        urls = [link['url'] for link in dashboard.get('links', [])]
        self.assertIn('/d/shakelab-host', urls)
        self.assertIn('/d/shakelab-storage', urls)

    def test_the_overview_node_panels_do_not_mix_in_guests(self):
        # pve_* は同じメトリクス名でゲストにも生える。絞らないと凡例が instance だらけになる。
        dashboard = self.dashboards()['overview.json']
        for panel in dashboard['panels']:
            if not panel['title'].startswith('Proxmox ノード'):
                continue
            for target in panel['targets']:
                self.assertIn('node/', target['expr'], panel['title'])


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


class CanaryTests(unittest.TestCase):
    def test_the_decoy_address_is_outside_every_allocated_range(self):
        import ipaddress
        network = yaml.safe_load((ROOT / 'platform/terraform/network.yaml').read_text(encoding='utf-8'))
        env = dict(line.split('=', 1) for line in (STACK / '.env.example').read_text(encoding='utf-8').splitlines()
                   if line.startswith('CANARY_ADDRESS='))
        address = ipaddress.ip_address(env['CANARY_ADDRESS'])
        for name in ('infrastructure', 'dhcp', 'management', 'metallb', 'cloud'):
            section = network.get(name) or {}
            if 'range_start' not in section:
                continue
            start = ipaddress.ip_interface(section['range_start']).ip
            end = ipaddress.ip_interface(section['range_end']).ip
            self.assertFalse(start <= address <= end, name)

    def test_the_rule_alerts_through_alertmanager_with_the_panel_text(self):
        rules = load(STACK / 'loki/rules/fake/canary.yml')
        rule = rules['groups'][0]['rules'][0]
        self.assertEqual(rule['labels']['severity'], 'critical')
        for key in ('panel', 'summary', 'description'):
            self.assertIn(key, rule['annotations'])
        loki = load(STACK / 'loki/config.yaml')
        self.assertEqual(loki['ruler']['alertmanager_url'], 'http://alertmanager:9093')

    def test_the_decoy_runs_unprivileged_and_read_only(self):
        service = load(STACK / 'compose.yaml')['services']['canary']
        self.assertTrue(service['read_only'])
        self.assertEqual(service['cap_drop'], ['ALL'])
        self.assertNotIn('ports', service)

    def test_a_touch_is_written_as_one_json_line(self):
        import asyncio
        import contextlib
        import io
        spec = importlib.util.spec_from_file_location('canary', STACK / 'canary/canary.py')
        canary = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(canary)

        async def touch():
            server = await asyncio.start_server(canary.handler(22), '127.0.0.1', 0)
            port = server.sockets[0].getsockname()[1]
            reader, writer = await asyncio.open_connection('127.0.0.1', port)
            banner = await reader.readline()
            writer.write(b'probe\n')
            await writer.drain()
            writer.close()
            await asyncio.sleep(0.2)
            server.close()
            return banner

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            banner = asyncio.run(touch())
        self.assertTrue(banner.startswith(b'SSH-2.0-'))
        event = json.loads(out.getvalue().strip().splitlines()[-1])
        self.assertEqual((event['event'], event['port'], event['src']), ('touch', 22, '127.0.0.1'))
