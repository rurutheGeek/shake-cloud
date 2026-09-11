#!/usr/bin/env python3
"""Check that the real Proxmox host supports what the cloud API design assumes.

Every probe answers one question no document can: whether *this* Proxmox
version grants a pool-scoped token the operation the design depends on. The
answers decide implementation choices, so a wrong guess costs rework. Run this
before building against the assumptions, and again after any PVE upgrade.

Run it with the cloudapi@pve token, never with root@pam: root would pass every
probe and tell you nothing about what the scoped account can do.

    export PROXMOX_VE_ENDPOINT=https://192.0.2.10:8006
    export PROXMOX_VE_API_TOKEN='cloudapi@pve!cloudapi=<uuid>'
    python3 tools/verify-cloud.py

Exit status is non-zero if any probe fails, so an unattended runner can gate
on it. Use --json for a machine-readable report.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import time

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'platform/terraform/site.yaml'

# A VMID inside the cloud pool that no instance will ever be given, so a probe
# left behind by a crash cannot collide with a real one.
PROBE_VMID = 5999


class Probe:
    """One question, its answer, and what a failure means for the design."""

    def __init__(self, name, question, on_failure):
        self.name = name
        self.question = question
        self.on_failure = on_failure
        self.passed = None
        self.detail = ''

    def record(self, passed, detail=''):
        self.passed = passed
        self.detail = detail
        return passed


class Proxmox:
    def __init__(self, endpoint, token, verify):
        self.base = endpoint.rstrip('/') + '/api2/json'
        self.session = requests.Session()
        self.session.headers['Authorization'] = f'PVEAPIToken={token}'
        self.session.verify = verify
        if not verify:
            # A self-signed certificate is the documented state of this host,
            # so the warning is noise that buries the probe results.
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def call(self, method, path, **kwargs):
        return self.session.request(method, self.base + path, timeout=60, **kwargs)

    def wait_task(self, node, upid, timeout=180):
        """Poll a UPID to completion.

        Proxmox answers 200 with a UPID for asynchronous work; the HTTP status
        says the task started, not that it finished or succeeded.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = self.call('GET', f'/nodes/{node}/tasks/{upid}/status')
            if response.status_code != 200:
                return False, f'task status HTTP {response.status_code}'
            data = response.json()['data']
            if data.get('status') == 'stopped':
                exit_status = data.get('exitstatus')
                return exit_status == 'OK', f'exitstatus={exit_status}'
            time.sleep(2)
        return False, 'task did not finish in time'


def probe_node_status(api, site, probe):
    """Admission control reads free RAM here, and the path is outside the pool."""
    node = site['node_name']
    response = api.call('GET', f'/nodes/{node}/status')
    if response.status_code != 200:
        return probe.record(False, f'HTTP {response.status_code}')
    memory = response.json().get('data', {}).get('memory', {})
    if 'free' not in memory:
        return probe.record(False, 'response carried no memory.free')
    return probe.record(True, f"free={memory['free']} total={memory.get('total')}")


def probe_image_lifecycle(api, site, probe):
    """Upload an ISO and delete it again.

    Deleting storage content is the half that needs Datastore.Allocate: an
    uploaded ISO is not owned by a VM, so VM.Config.Disk cannot remove it. If
    the delete fails, every per-instance seed ISO becomes immortal.
    """
    node = site['node_name']
    store = site['storage']['cloud_images']
    name = f'shakecloud-probe-{secrets.token_hex(4)}.iso'
    payload = secrets.token_bytes(64 * 1024)

    response = api.call('POST', f'/nodes/{node}/storage/{store}/upload',
                        data={'content': 'iso'},
                        files={'filename': (name, payload, 'application/octet-stream')})
    if response.status_code != 200:
        return probe.record(False, f'upload HTTP {response.status_code}: {response.text[:200]}')
    upid = response.json().get('data')
    finished, detail = api.wait_task(node, upid)
    if not finished:
        return probe.record(False, f'upload task failed: {detail}')

    volume = f'{store}:iso/{name}'
    response = api.call('DELETE', f'/nodes/{node}/storage/{store}/content/{volume}')
    if response.status_code != 200:
        return probe.record(False, f'upload worked but delete returned '
                                   f'HTTP {response.status_code}: {response.text[:200]}')
    return probe.record(True, 'upload and delete both succeeded')


def probe_pool_boundary(api, site, probe):
    """The cloud pool must accept a VM and the platform pool must refuse one.

    A pass here is the evidence that the ownership boundary is enforced by
    ACLs rather than by convention.
    """
    node = site['node_name']
    body = {'vmid': PROBE_VMID, 'name': 'shakecloud-probe', 'memory': 512, 'cores': 1,
            'net0': f"virtio,bridge={site['network']['bridge']},firewall=1"}

    allowed = api.call('POST', f'/nodes/{node}/qemu', data={**body, 'pool': 'cloud'})
    if allowed.status_code != 200:
        return probe.record(False, f'cloud pool refused the VM: HTTP '
                                   f'{allowed.status_code}: {allowed.text[:200]}')
    finished, detail = api.wait_task(node, allowed.json().get('data'))
    if not finished:
        return probe.record(False, f'create task failed: {detail}')

    denied = api.call('POST', f'/nodes/{node}/qemu',
                      data={**body, 'vmid': PROBE_VMID - 1, 'pool': 'platform'})
    if denied.status_code != 403:
        return probe.record(False, f'platform pool answered HTTP {denied.status_code}, '
                                   'expected 403; the boundary is not enforced')
    return probe.record(True, 'cloud pool accepted, platform pool returned 403')


def probe_console_auth(api, site, probe):
    """Does vncwebsocket accept an API token, or does it demand a ticket?

    This is the least predictable assumption in the design. A 401 here means
    the web console needs PVEAuthCookie, which means cloudapi@pve needs a
    password set the way platform/ansible/roles/pve_users already does it.
    """
    node = site['node_name']
    response = api.call('POST', f'/nodes/{node}/qemu/{PROBE_VMID}/vncproxy',
                        data={'websocket': 1, 'generate-password': 1})
    if response.status_code != 200:
        return probe.record(False, f'vncproxy HTTP {response.status_code}: {response.text[:200]}')
    data = response.json()['data']

    upgrade = api.call(
        'GET', f'/nodes/{node}/qemu/{PROBE_VMID}/vncwebsocket',
        params={'port': data['port'], 'vncticket': data['ticket']},
        headers={'Connection': 'Upgrade', 'Upgrade': 'websocket',
                 'Sec-WebSocket-Version': '13', 'Sec-WebSocket-Protocol': 'binary',
                 'Sec-WebSocket-Key': secrets.token_urlsafe(16)},
        stream=True, allow_redirects=False)
    upgrade.close()
    if upgrade.status_code == 101:
        return probe.record(True, 'API token accepted on the websocket upgrade')
    return probe.record(False, f'websocket upgrade returned HTTP {upgrade.status_code}; '
                               'the console needs ticket authentication')


def cleanup(api, site):
    node = site['node_name']
    for vmid in (PROBE_VMID, PROBE_VMID - 1):
        api.call('DELETE', f'/nodes/{node}/qemu/{vmid}', params={'purge': 1})


PROBES = [
    ('node_status', probe_node_status,
     'Can a pool-scoped token read the node\'s free memory?',
     'Admission control cannot see real capacity. Grant CloudApiNodeAudit on /nodes/<node>.'),
    ('image_lifecycle', probe_image_lifecycle,
     'Can it upload an ISO to the cloud image store and delete it again?',
     'Per-instance seed ISOs accumulate. Fall back to an admin-side prune job.'),
    ('pool_boundary', probe_pool_boundary,
     'Does the cloud pool accept a VM while the platform pool refuses one?',
     'The ownership boundary is not enforced. Do not expose the API to users.'),
    ('console_auth', probe_console_auth,
     'Does vncwebsocket accept an API token?',
     'Give cloudapi@pve a password and use ticket auth, as roles/pve_users already does.'),
]


def run(api, site, only=None):
    results = []
    for name, function, question, on_failure in PROBES:
        if only and name not in only:
            continue
        probe = Probe(name, question, on_failure)
        try:
            function(api, site, probe)
        except Exception as error:  # a probe must never mask the others
            probe.record(False, f'{type(error).__name__}: {error}')
        results.append(probe)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--json', action='store_true', help='machine-readable report')
    parser.add_argument('--probe', action='append', help='run only the named probe')
    parser.add_argument('--keep', action='store_true', help='leave the probe VMs behind')
    args = parser.parse_args()

    endpoint = os.environ.get('PROXMOX_VE_ENDPOINT')
    token = os.environ.get('PROXMOX_VE_API_TOKEN')
    if not (endpoint and token):
        raise SystemExit('Set PROXMOX_VE_ENDPOINT and PROXMOX_VE_API_TOKEN '
                         '(use the cloudapi@pve token, not root@pam)')
    if token.startswith('root@pam'):
        raise SystemExit('Refusing to run as root@pam: root passes every probe and '
                         'tells you nothing about the scoped account')

    site = yaml.safe_load(SITE.read_text(encoding='utf-8'))
    insecure = os.environ.get('PROXMOX_VE_INSECURE', '').lower() in ('1', 'true', 'yes')
    api = Proxmox(endpoint, token, verify=not insecure)

    results = run(api, site, only=set(args.probe) if args.probe else None)
    if not args.keep:
        cleanup(api, site)

    if args.json:
        print(json.dumps([{'name': p.name, 'passed': p.passed, 'detail': p.detail,
                           'question': p.question, 'on_failure': p.on_failure}
                          for p in results], ensure_ascii=False, indent=2))
    else:
        for probe in results:
            print(f"{'PASS' if probe.passed else 'FAIL'}: {probe.name} -- {probe.question}")
            print(f'      {probe.detail}')
            if not probe.passed:
                print(f'      consequence: {probe.on_failure}')
    return 0 if all(p.passed for p in results) else 1


if __name__ == '__main__':
    sys.exit(main())
