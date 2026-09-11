"""Check the probe script's judgement without touching a Proxmox host.

The probes exist to answer questions about real hardware, but *how they read
an answer* is ordinary logic and has to be right: a probe that reports PASS on
a 403, or that calls the boundary intact when the platform pool accepted a VM,
is worse than no probe at all.
"""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('verify_cloud', ROOT / 'tools/verify-cloud.py')
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)

SITE = {'node_name': 'node1',
        'storage': {'vm_disks': 'local-lvm', 'cloud_images': 'cloud-images'},
        'network': {'bridge': 'vmbr0'}}


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return {'data': self._payload}

    def close(self):
        pass


class FakeApi:
    """Answers calls from a scripted list, in order."""

    def __init__(self, responses, task_ok=True):
        self.responses = list(responses)
        self.task_ok = task_ok
        self.calls = []

    def call(self, method, path, **kwargs):
        self.calls.append((method, path))
        return self.responses.pop(0)

    def wait_task(self, node, upid, timeout=180):
        return self.task_ok, 'exitstatus=OK' if self.task_ok else 'exitstatus=failed'


def probe(name):
    return verify.Probe(name, 'question', 'consequence')


class NodeStatusTests(unittest.TestCase):
    def test_a_forbidden_response_is_a_failure(self):
        # 403 here means the Sys.Audit ACL on /nodes/<node> is missing, which
        # is exactly what the probe exists to catch.
        result = probe('node_status')
        verify.probe_node_status(FakeApi([FakeResponse(403)]), SITE, result)
        self.assertFalse(result.passed)

    def test_a_response_without_free_memory_is_a_failure(self):
        # A 200 that carries no usable number would let admission control ship
        # with nothing to compare against.
        result = probe('node_status')
        verify.probe_node_status(FakeApi([FakeResponse(200, {'memory': {}})]), SITE, result)
        self.assertFalse(result.passed)

    def test_free_memory_passes(self):
        result = probe('node_status')
        verify.probe_node_status(
            FakeApi([FakeResponse(200, {'memory': {'free': 1, 'total': 2}})]), SITE, result)
        self.assertTrue(result.passed)


class ImageLifecycleTests(unittest.TestCase):
    def test_an_upload_that_cannot_be_deleted_is_a_failure(self):
        # The whole point of this probe. Upload succeeding is not enough:
        # without Datastore.Allocate every seed ISO becomes immortal.
        result = probe('image_lifecycle')
        api = FakeApi([FakeResponse(200, 'UPID:x'), FakeResponse(403)])
        verify.probe_image_lifecycle(api, SITE, result)
        self.assertFalse(result.passed)
        self.assertIn('delete', result.detail)

    def test_upload_and_delete_both_succeeding_passes(self):
        result = probe('image_lifecycle')
        api = FakeApi([FakeResponse(200, 'UPID:x'), FakeResponse(200)])
        verify.probe_image_lifecycle(api, SITE, result)
        self.assertTrue(result.passed)

    def test_a_failed_upload_task_is_a_failure_even_though_http_was_200(self):
        # Proxmox answers 200 with a UPID for asynchronous work; the status
        # code says the task started, not that it worked.
        result = probe('image_lifecycle')
        api = FakeApi([FakeResponse(200, 'UPID:x')], task_ok=False)
        verify.probe_image_lifecycle(api, SITE, result)
        self.assertFalse(result.passed)


class PoolBoundaryTests(unittest.TestCase):
    def test_the_platform_pool_accepting_a_vm_is_a_failure(self):
        # If the platform pool answers anything but 403, the user-facing
        # delete API can reach the platform VMs and must not be exposed.
        result = probe('pool_boundary')
        api = FakeApi([FakeResponse(200, 'UPID:x'), FakeResponse(200, 'UPID:y')])
        verify.probe_pool_boundary(api, SITE, result)
        self.assertFalse(result.passed)
        self.assertIn('403', result.detail)

    def test_cloud_accepted_and_platform_refused_passes(self):
        result = probe('pool_boundary')
        api = FakeApi([FakeResponse(200, 'UPID:x'), FakeResponse(403)])
        verify.probe_pool_boundary(api, SITE, result)
        self.assertTrue(result.passed)

    def test_the_cloud_pool_refusing_a_vm_is_a_failure(self):
        result = probe('pool_boundary')
        api = FakeApi([FakeResponse(403)])
        verify.probe_pool_boundary(api, SITE, result)
        self.assertFalse(result.passed)


class ConsoleAuthTests(unittest.TestCase):
    def test_only_a_websocket_upgrade_counts_as_success(self):
        # 200 on the upgrade path is not an upgrade; only 101 is.
        result = probe('console_auth')
        api = FakeApi([FakeResponse(200, {'port': '5900', 'ticket': 't'}),
                       FakeResponse(200)])
        verify.probe_console_auth(api, SITE, result)
        self.assertFalse(result.passed)

    def test_an_unauthorised_upgrade_is_a_failure(self):
        result = probe('console_auth')
        api = FakeApi([FakeResponse(200, {'port': '5900', 'ticket': 't'}),
                       FakeResponse(401)])
        verify.probe_console_auth(api, SITE, result)
        self.assertFalse(result.passed)

    def test_a_101_passes(self):
        result = probe('console_auth')
        api = FakeApi([FakeResponse(200, {'port': '5900', 'ticket': 't'}),
                       FakeResponse(101)])
        verify.probe_console_auth(api, SITE, result)
        self.assertTrue(result.passed)


class RunnerTests(unittest.TestCase):
    def test_a_raising_probe_fails_instead_of_stopping_the_run(self):
        # One unreachable endpoint must not hide the other three answers.
        original = verify.PROBES
        verify.PROBES = [('boom', lambda *a: 1 / 0, 'q', 'c')] + list(original)
        try:
            results = verify.run(FakeApi([FakeResponse(200, {'memory': {'free': 1}})]),
                                 SITE, only={'boom', 'node_status'})
        finally:
            verify.PROBES = original
        self.assertEqual([r.name for r in results], ['boom', 'node_status'])
        self.assertFalse(results[0].passed)
        self.assertIn('ZeroDivisionError', results[0].detail)
        self.assertTrue(results[1].passed)

    def test_the_probe_vmids_sit_inside_the_cloud_pool_range(self):
        # A probe that landed outside 5000-5999 would be created where the
        # token has no rights, and the failure would look like a real answer.
        import yaml
        pools = yaml.safe_load(
            (ROOT / 'platform/terraform/pools.yaml').read_text(encoding='utf-8'))['pools']
        for vmid in (verify.PROBE_VMID, verify.PROBE_VMID - 1):
            self.assertGreaterEqual(vmid, pools['cloud']['vmid_from'])
            self.assertLessEqual(vmid, pools['cloud']['vmid_to'])


if __name__ == '__main__':
    unittest.main()
