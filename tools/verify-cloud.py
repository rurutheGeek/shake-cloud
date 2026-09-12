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


def ensure_vm_in_cloud_pool(api, site, vmid):
    """Create vmid in the cloud pool unless it already exists.

    volume_reassign and vm_firewall each need one or two throwaway VMs, and
    must work when run alone (`--probe volume_reassign`) as well as after
    pool_boundary, which already creates PROBE_VMID but only *tries* to
    create PROBE_VMID-1 (in the platform pool, where it is refused). Checking
    first makes both call patterns safe to repeat.
    """
    node = site['node_name']
    response = api.call('GET', f'/nodes/{node}/qemu/{vmid}/config')
    if response.status_code == 200:
        return True, ''
    body = {'vmid': vmid, 'name': 'shakecloud-probe', 'memory': 512, 'cores': 1,
            'net0': f"virtio,bridge={site['network']['bridge']},firewall=1", 'pool': 'cloud'}
    created = api.call('POST', f"/nodes/{node}/qemu", data=body)
    if created.status_code != 200:
        return False, f'create VM {vmid} HTTP {created.status_code}: {created.text[:200]}'
    finished, detail = api.wait_task(node, created.json().get('data'))
    if not finished:
        return False, f'create VM {vmid} task failed: {detail}'
    return True, ''


def probe_volume_reassign(api, site, probe):
    """Can a detached disk be held on one VM and handed to another?

    Every Proxmox disk belongs to some VM, and the only operation that
    changes which VM is move_disk. A DetachVolume with nowhere to put the
    disk cannot exist, so this probe walks the exact sequence DetachVolume
    and AttachVolume would use: allocate, detach (unlink), reassign to
    another VM (move_disk), reassign back, then destroy for good.
    """
    node = site['node_name']
    store = site['storage']['vm_disks']
    instance, holder = PROBE_VMID, PROBE_VMID - 1

    for vmid in (holder, instance):
        ok, detail = ensure_vm_in_cloud_pool(api, site, vmid)
        if not ok:
            return probe.record(False, detail)

    response = api.call('POST', f'/nodes/{node}/qemu/{holder}/config',
                        data={'scsi0': f'{store}:1,discard=on'})
    if response.status_code != 200:
        return probe.record(False, f'allocate disk HTTP {response.status_code}: {response.text[:200]}')
    upid = response.json().get('data')
    if upid:
        finished, detail = api.wait_task(node, upid)
        if not finished:
            return probe.record(False, f'allocate disk task failed: {detail}')

    config = api.call('GET', f'/nodes/{node}/qemu/{holder}/config').json()['data']
    if 'scsi0' not in config:
        return probe.record(False, f'holder has no scsi0 after allocation: {config}')
    volid = config['scsi0'].split(',')[0]

    # Detach without force: the disk must survive as an unusedN with the same volid.
    response = api.call('PUT', f'/nodes/{node}/qemu/{holder}/unlink', data={'idlist': 'scsi0'})
    if response.status_code != 200:
        return probe.record(False, f'unlink scsi0 HTTP {response.status_code}: {response.text[:200]}')
    config = api.call('GET', f'/nodes/{node}/qemu/{holder}/config').json()['data']
    unused_key = next((key for key, value in config.items()
                       if key.startswith('unused') and value.split(',')[0] == volid), None)
    if unused_key is None:
        return probe.record(False, f'unlinked disk {volid} did not reappear as unusedN: {config}')

    # Hand it to the other VM.
    response = api.call('POST', f'/nodes/{node}/qemu/{holder}/move_disk',
                        data={'disk': unused_key, 'target-vmid': instance, 'target-disk': 'unused0'})
    if response.status_code != 200:
        return probe.record(False, f'move_disk to instance HTTP {response.status_code}: {response.text[:200]}')
    finished, detail = api.wait_task(node, response.json().get('data'))
    if not finished:
        return probe.record(False, f'move_disk to instance task failed: {detail}')
    config = api.call('GET', f'/nodes/{node}/qemu/{instance}/config').json()['data']
    if not config.get('unused0', '').startswith(f'{store}:vm-{instance}-'):
        return probe.record(False, f'instance config missing the reassigned disk: {config}')

    # Move it back to the holder.
    response = api.call('POST', f'/nodes/{node}/qemu/{instance}/move_disk',
                        data={'disk': 'unused0', 'target-vmid': holder, 'target-disk': unused_key})
    if response.status_code != 200:
        return probe.record(False, f'move_disk back HTTP {response.status_code}: {response.text[:200]}')
    finished, detail = api.wait_task(node, response.json().get('data'))
    if not finished:
        return probe.record(False, f'move_disk back task failed: {detail}')
    config = api.call('GET', f'/nodes/{node}/qemu/{holder}/config').json()['data']
    if unused_key not in config:
        return probe.record(False, f'disk did not return to the holder as {unused_key}: {config}')
    final_volid = config[unused_key].split(',')[0]

    # Destroy it for good, as DeleteVolume would.
    response = api.call('PUT', f'/nodes/{node}/qemu/{holder}/unlink',
                        data={'idlist': unused_key, 'force': 1})
    if response.status_code != 200:
        return probe.record(False, f'force unlink HTTP {response.status_code}: {response.text[:200]}')
    config = api.call('GET', f'/nodes/{node}/qemu/{holder}/config').json()['data']
    if unused_key in config:
        return probe.record(False, f'{unused_key} still in the holder config after force unlink')
    content = api.call('GET', f'/nodes/{node}/storage/{store}/content',
                       params={'content': 'images', 'vmid': holder})
    if content.status_code != 200:
        return probe.record(False, f'storage content list HTTP {content.status_code}: {content.text[:200]}')
    if final_volid in [v.get('volid') for v in content.json().get('data', [])]:
        return probe.record(False, f'{final_volid} still on storage after force unlink')

    return probe.record(True, f'allocate -> unlink -> move_disk -> move back -> force unlink all worked '
                              f'({volid} -> {final_volid})')


def probe_vm_firewall(api, site, probe):
    """Can the scoped token write a VM's firewall, and where does a rule land?

    Security groups will be implemented as per-VM Proxmox firewall rules
    rewritten on every change. If the token cannot write them, security
    groups cannot be enforced. If Proxmox inserts a rule posted without
    `pos` somewhere other than the top, the rewrite logic must post rules
    in reverse order or every group ends up backwards.
    """
    node = site['node_name']
    vmid = PROBE_VMID

    ok, detail = ensure_vm_in_cloud_pool(api, site, vmid)
    if not ok:
        return probe.record(False, detail)

    response = api.call('PUT', f'/nodes/{node}/qemu/{vmid}/firewall/options',
                        data={'enable': 1, 'policy_in': 'DROP', 'policy_out': 'ACCEPT'})
    if response.status_code != 200:
        return probe.record(False, f'set firewall options HTTP {response.status_code}: {response.text[:200]}')

    response = api.call('POST', f'/nodes/{node}/qemu/{vmid}/firewall/rules',
                        data={'type': 'in', 'action': 'ACCEPT', 'comment': 'probe-a'})
    if response.status_code != 200:
        return probe.record(False, f'insert rule a HTTP {response.status_code}: {response.text[:200]}')
    response = api.call('POST', f'/nodes/{node}/qemu/{vmid}/firewall/rules',
                        data={'type': 'in', 'action': 'ACCEPT', 'comment': 'probe-b'})
    if response.status_code != 200:
        return probe.record(False, f'insert rule b HTTP {response.status_code}: {response.text[:200]}')

    rules = api.call('GET', f'/nodes/{node}/qemu/{vmid}/firewall/rules')
    if rules.status_code != 200:
        return probe.record(False, f'list rules HTTP {rules.status_code}: {rules.text[:200]}')
    by_pos = {rule['pos']: rule for rule in rules.json().get('data', [])}
    ordering_ok = by_pos.get(0, {}).get('comment') == 'probe-b'
    ordering_detail = '' if ordering_ok else (
        f'expected probe-b at pos 0, got {sorted((p, r.get("comment")) for p, r in by_pos.items())}')

    ipset_ok, ipset_detail = True, ''
    response = api.call('POST', f'/nodes/{node}/qemu/{vmid}/firewall/ipset', data={'name': 'ipfilter-net0'})
    if response.status_code != 200:
        ipset_ok = False
        ipset_detail = f'create ipset HTTP {response.status_code}: {response.text[:200]}'
    else:
        response = api.call('POST', f'/nodes/{node}/qemu/{vmid}/firewall/ipset/ipfilter-net0',
                            data={'cidr': '192.0.2.10'})
        if response.status_code != 200:
            ipset_ok = False
            ipset_detail = f'add ipset entry HTTP {response.status_code}: {response.text[:200]}'

    # The datacenter firewall is out of this token's ACL scope by design (it
    # is Terraform's job, not the cloud API's), so a 403 here is expected and
    # must not fail the probe -- only reported for the human reading --json.
    dc_detail = []
    cluster = api.call('GET', '/cluster/firewall/options')
    if cluster.status_code == 200:
        dc_detail.append(f"datacenter enable={cluster.json().get('data', {}).get('enable')}")
    else:
        dc_detail.append(f'datacenter options HTTP {cluster.status_code} (informational only)')
    node_options = api.call('GET', f'/nodes/{node}/firewall/options')
    if node_options.status_code == 200:
        value = node_options.json().get('data', {}).get('nf_conntrack_allow_invalid')
        dc_detail.append(f'node nf_conntrack_allow_invalid={value}')
    else:
        dc_detail.append(f'node options HTTP {node_options.status_code} (informational only)')

    # Clean up regardless of outcome: entry, ipset, rules highest pos first
    # (deleting shifts lower positions), then the options that were set.
    if ipset_ok:
        api.call('DELETE', f'/nodes/{node}/qemu/{vmid}/firewall/ipset/ipfilter-net0/192.0.2.10')
        api.call('DELETE', f'/nodes/{node}/qemu/{vmid}/firewall/ipset/ipfilter-net0')
    for pos in sorted(by_pos, reverse=True):
        api.call('DELETE', f'/nodes/{node}/qemu/{vmid}/firewall/rules/{pos}')
    api.call('PUT', f'/nodes/{node}/qemu/{vmid}/firewall/options',
            data={'delete': 'enable,policy_in,policy_out'})

    detail = '; '.join(dc_detail)
    if not ordering_ok:
        return probe.record(False, f'{ordering_detail}; {detail}')
    if not ipset_ok:
        return probe.record(False, f'{ipset_detail}; {detail}')
    return probe.record(True, f'options, rule ordering (probe-b at pos 0) and ipset all worked; {detail}')


def cleanup(api, site):
    node = site['node_name']
    for vmid in (PROBE_VMID, PROBE_VMID - 1):
        api.call('DELETE', f'/nodes/{node}/qemu/{vmid}',
                params={'purge': 1, 'destroy-unreferenced-disks': 1})


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
    ('volume_reassign', probe_volume_reassign,
     'Can a detached disk be held on one VM and handed to another with move_disk?',
     'Volumes cannot be detached without a VM to hold them; redesign before shipping volumes.'),
    ('vm_firewall', probe_vm_firewall,
     'Can the scoped token write a VM\'s firewall, and does a rule posted without pos land at the top?',
     'Security groups cannot be enforced; or, if only the ordering differs, '
     'the API writes rules in the wrong order.'),
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
