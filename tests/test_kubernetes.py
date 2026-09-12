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

    def test_the_power_helper_reads_the_declaration(self):
        # It must not hardcode VMIDs; reading hosts.yaml keeps the two in step.
        helper = (ROOT / 'tools/k8s').read_text()
        self.assertIn('hosts.yaml', helper)
        self.assertIn('k8s-cp', helper)
        self.assertIn('k8s-worker', helper)


if __name__ == '__main__':
    unittest.main()
