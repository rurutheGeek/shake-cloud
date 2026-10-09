"""Guard the Kubernetes declaration, versions and the cluster shape.

Kubernetes is greenfield here, so nothing else checks these. The version
lockstep with Cilium and the CIDR choice are the two mistakes that would only
surface after a cluster is built.
"""
from pathlib import Path
import ipaddress
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class KubernetesTests(unittest.TestCase):
    def setUp(self):
        self.hosts = yaml.safe_load((ROOT / 'platform/terraform/hosts.yaml').read_text())['hosts']
        self.vars = yaml.safe_load((ROOT / 'platform/ansible/k8s-vars.yml').read_text())
        self.plays = yaml.safe_load((ROOT / 'platform/ansible/kubernetes.yml').read_text())

    def test_the_nodes_are_declared_in_the_platform_pool(self):
        expected = {
            'k8s-cp-01': (200, 'k8s-cp'),
            'k8s-worker-01': (210, 'k8s-worker'),
            'k8s-worker-02': (211, 'k8s-worker'),
        }
        for name, (vm_id, tag) in expected.items():
            host = self.hosts[name]
            self.assertEqual(host['vm_id'], vm_id)
            self.assertEqual(host['pool'], 'platform')
            self.assertIn(tag, host['tags'])

    def test_the_workers_have_data_disks_and_the_spare_stays_down(self):
        self.assertGreater(self.hosts['k8s-worker-01']['data_disk_gib'], 0)
        self.assertGreater(self.hosts['k8s-worker-02']['data_disk_gib'], 0)
        # The spare worker is created but not started, so it costs no RAM.
        self.assertIs(self.hosts['k8s-worker-02']['started'], False)

    def test_the_kubernetes_version_is_one_cilium_supports(self):
        # Cilium 1.20 is e2e-tested through Kubernetes 1.36. Moving to 1.37
        # before Cilium catches up would leave the CNI unsupported.
        self.assertEqual(self.vars['k8s_minor'], '1.36')
        self.assertRegex(self.vars['k8s_version'], r'^1\.36\.\d+$')

    def test_the_cluster_cidrs_avoid_the_lan(self):
        lan = ipaddress.ip_network('192.168.10.0/24')
        pods = ipaddress.ip_network(self.vars['k8s_pod_cidr'])
        services = ipaddress.ip_network(self.vars['k8s_service_cidr'])
        self.assertFalse(pods.overlaps(lan))
        self.assertFalse(services.overlaps(lan))
        self.assertFalse(pods.overlaps(services))

    def test_the_playbook_prepares_creates_and_joins(self):
        roles = [role for play in self.plays for role in play['roles']]
        for role in ('k8s_node', 'k8s_control_plane', 'k8s_join'):
            self.assertIn(role, roles)
        control = [play for play in self.plays if 'k8s_cp' in play['hosts'] and 'k8s_worker' not in play['hosts']]
        self.assertTrue(control, 'the control plane needs its own play')

    def test_cilium_replaces_kube_proxy(self):
        control_plane = (ROOT / 'platform/ansible/roles/k8s_control_plane/tasks/main.yml').read_text()
        self.assertIn('skip-phases=addon/kube-proxy', control_plane)
        values = (ROOT / 'platform/ansible/roles/k8s_control_plane/templates/cilium-values.yaml.j2').read_text()
        self.assertIn('kubeProxyReplacement: true', values)
        self.assertIn('ipam:', values)

    def test_the_addons_are_version_pinned(self):
        defaults = yaml.safe_load((ROOT / 'platform/ansible/roles/k8s_addons/defaults/main.yml').read_text())
        self.assertRegex(defaults['k8s_local_path_version'], r'^v0\.0\.\d+$')
        self.assertRegex(defaults['k8s_metallb_version'], r'^\d+\.\d+\.\d+$')
        self.assertRegex(defaults['k8s_cert_manager_version'], r'^v\d+\.\d+\.\d+$')

    def test_metallb_uses_the_declared_network_range(self):
        network = yaml.safe_load((ROOT / 'platform/terraform/network.yaml').read_text())
        self.assertIn('metallb', network)
        defaults = (ROOT / 'platform/ansible/roles/k8s_addons/defaults/main.yml').read_text()
        self.assertIn('network.yaml', defaults)
        pool = (ROOT / 'platform/ansible/roles/k8s_addons/templates/metallb-pool.yaml.j2').read_text()
        self.assertIn('IPAddressPool', pool)
        self.assertIn('L2Advertisement', pool)

    def test_the_power_helper_reads_the_declaration(self):
        # It must not hardcode VMIDs; reading hosts.yaml keeps the two in step.
        helper = (ROOT / 'tools/k8s').read_text()
        self.assertIn('hosts.yaml', helper)
        self.assertIn('k8s-cp', helper)
        self.assertIn('k8s-worker', helper)


class NetworkPolicyTests(unittest.TestCase):
    """The namespaces the cloud API fills must not accept random pod traffic."""

    def load(self, path):
        return list(yaml.safe_load_all((ROOT / path).read_text()))

    def test_both_namespaces_deny_ingress_by_default(self):
        functions = self.load('platform/flux/apps/functions-network-policy.yaml')[0]
        databases = self.load('platform/flux/apps/databases/network-policy.yaml')[0]
        for policy, namespace in ((functions, 'functions'), (databases, 'databases')):
            self.assertEqual(policy['metadata']['namespace'], namespace)
            self.assertEqual(policy['spec']['podSelector'], {})
            self.assertEqual(policy['spec']['policyTypes'], ['Ingress'])

    def test_functions_accept_only_the_data_plane(self):
        policy = self.load('platform/flux/apps/functions-network-policy.yaml')[0]
        sources = policy['spec']['ingress'][0]['from']
        self.assertIn({'podSelector': {}}, sources)
        self.assertIn({'namespaceSelector': {'matchLabels': {
            'kubernetes.io/metadata.name': 'knative-serving'}}}, sources)

    def test_databases_accept_only_cluster_clients(self):
        policy = self.load('platform/flux/apps/databases/network-policy.yaml')[0]
        rule = policy['spec']['ingress'][0]
        self.assertIn({'podSelector': {}}, rule['from'])
        self.assertIn({'namespaceSelector': {'matchLabels': {
            'kubernetes.io/metadata.name': 'functions'}}}, rule['from'])
        self.assertEqual(rule['ports'], [{'protocol': 'TCP', 'port': 5432}])

    def test_the_cnpg_operator_can_read_instance_status(self):
        # Without this the operator cannot reconcile the clusters it created.
        policy = self.load('platform/flux/apps/databases/network-policy.yaml')[0]
        rule = policy['spec']['ingress'][1]
        self.assertEqual(rule['from'], [{'namespaceSelector': {'matchLabels': {
            'kubernetes.io/metadata.name': 'cnpg-system'}}}])
        self.assertEqual(rule['ports'], [{'protocol': 'TCP', 'port': 8000}])

    def test_flux_applies_the_functions_policy(self):
        root = yaml.safe_load((ROOT / 'platform/flux/kustomization.yaml').read_text())
        self.assertIn('apps/functions-network-policy.yaml', root['resources'])


if __name__ == '__main__':
    unittest.main()
