#!/usr/bin/env python3
"""Check the volume and security-group paths against a real deployment.

Three answers no unit test gives:

  * a volume really appears inside the guest as
    /dev/disk/by-id/virtio-<serial> after AttachVolume, survives a resize,
    and disappears after DetachVolume;
  * a security group really filters traffic -- SSH stays reachable, a port
    that is not allowed times out, and adding and removing the rule flips it;
  * Terminate and DeleteVolume leave no VM, disk or address behind.

    export SHAKECLOUD_ACCESS_KEY=$(ssh -i ~/.ssh/id_ed25519_pve \\
      debian@192.168.10.205 sudo cat /opt/cloud-stack/secrets/bootstrap_admin_key)
    sops exec-env platform/sops/cloudapi.sops.yaml 'python3 tools/verify-volumes.py'

The API key does the creating; the Proxmox and NetBox credentials are only
read, to check from the other side that what the API claims is really there.
Exit status is non-zero if anything failed, so an unattended runner can gate on
it. Everything is cleaned up even when a check fails.
"""
import argparse
import errno
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import requests
import urllib3
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API = 'https://cloud.apextox.dpdns.org'
SSH_KEY = Path.home() / '.ssh/id_ed25519_pve'
# The port the listener opens inside the guest, and the only one the security
# group under test does not allow at first.
PROBE_PORT = 8000


def judge(seen):
    """Return everything wrong with a run. Empty means it passed.

    Kept apart from the network so its judgement can be tested without hardware
    (tests/test_verify_volumes.py). Reading a blocked port as open, or a
    leftover disk as cleaned up, would be worse than no check at all.
    """
    problems = []
    if seen.get('state') != 'running':
        problems.append(f"the instance never reached running: {seen.get('state')} {seen.get('state_reason', '')}".strip())
    if not seen.get('address'):
        problems.append('no address was allocated')
    if not seen.get('logged_in'):
        problems.append('could not log in over SSH: cloud-init did not apply the seed ISO')

    # Security groups: SSH must stay reachable; the unlisted port must be
    # blocked, become reachable when its rule is added, and be blocked again
    # once the rule is revoked.
    if not seen.get('firewall_in_sync'):
        problems.append('the firewall never reported in-sync after a security group change')
    if seen.get('ssh_open') is not True:
        problems.append('SSH was not reachable with the security group applied')
    if seen.get('probe_blocked') is not True:
        problems.append('a port the security group does not allow was reachable')
    if seen.get('probe_allowed') is not True:
        problems.append('the port stayed blocked after its ingress rule was added')
    if seen.get('probe_blocked_again') is not True:
        problems.append('the port stayed reachable after its ingress rule was revoked')

    # Volumes: visible in the guest when attached, gone when detached, and
    # deleted.
    if seen.get('volume_state_created') != 'available':
        problems.append(f"the volume did not become available: {seen.get('volume_state_created')}")
    if seen.get('device_seen') is not True:
        problems.append(f"the guest never saw /dev/disk/by-id/virtio-{seen.get('serial', '')}")
    if seen.get('volume_state_detached') != 'available':
        problems.append(f"the volume did not return to available: {seen.get('volume_state_detached')}")
    if seen.get('volume_state_deleted') != 'deleted':
        problems.append(f"the volume did not reach deleted: {seen.get('volume_state_deleted')}")

    if seen.get('final_state') != 'terminated':
        problems.append(f"the instance did not reach terminated: {seen.get('final_state')}")
    for name, label in (('leftover_vms', 'VMs'), ('leftover_holder_disks', 'disks on the holder'),
                        ('leftover_addresses', 'NetBox addresses')):
        if seen.get(name):
            problems.append(f'{label} left behind after terminate: {seen[name]}')
    return problems


class Cloud:
    """The cloud API. Every call raises on a non-2xx status."""

    def __init__(self, base, key):
        self.base = base.rstrip('/')
        self.headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}

    def call(self, method, path, body=None):
        response = requests.request(method, self.base + path, headers=self.headers,
                                    json=body, timeout=60)
        response.raise_for_status()
        return response.json() if response.content else {}

    # instances
    def create_instance(self, image, instance_type, public_key):
        return self.call('POST', '/v1/instances', {
            'image_id': image, 'instance_type': instance_type, 'root_disk_gib': 10,
            'user_data': '#cloud-config\nssh_authorized_keys:\n  - ' + public_key + '\n',
            'tags': {'Name': 'verify-volumes'},
            'client_token': 'verify-volumes-' + str(int(time.time())),
        })['instance']

    def get_instance(self, iid):
        return self.call('GET', f'/v1/instances/{iid}')['instance']

    def delete_instance(self, iid):
        return self.call('DELETE', f'/v1/instances/{iid}')['instance']

    def set_groups(self, iid, group_ids):
        return self.call('PUT', f'/v1/instances/{iid}/security-groups',
                         {'security_group_ids': group_ids})['instance']

    def wait_instance(self, iid, until, tries=72):
        instance = self.get_instance(iid)
        for _ in range(tries):
            instance = self.get_instance(iid)
            if instance['state'] in until:
                return instance
            time.sleep(5)
        return instance

    def wait_firewall(self, iid, tries=40):
        instance = self.get_instance(iid)
        for _ in range(tries):
            instance = self.get_instance(iid)
            if instance.get('firewall_state') == 'in-sync':
                return instance
            time.sleep(3)
        return instance

    # security groups
    def create_group(self, name):
        return self.call('POST', '/v1/security-groups',
                         {'group_name': name, 'description': 'verify-volumes'})['security_group']

    def add_ingress(self, gid, rule):
        return self.call('POST', f'/v1/security-groups/{gid}/ingress',
                         {'rules': [rule]})['security_group']

    def revoke_rule(self, gid, rule_id):
        return self.call('DELETE', f'/v1/security-groups/{gid}/rules/{rule_id}')['security_group']

    def delete_group(self, gid):
        self.call('DELETE', f'/v1/security-groups/{gid}')

    # volumes
    def create_volume(self, size_gib):
        return self.call('POST', '/v1/volumes', {
            'size_gib': size_gib, 'client_token': 'verify-vol-' + str(int(time.time())),
            'tags': {'Name': 'verify-volumes'},
        })['volume']

    def get_volume(self, vid):
        return self.call('GET', f'/v1/volumes/{vid}')['volume']

    def attach_volume(self, vid, iid):
        return self.call('POST', f'/v1/volumes/{vid}/attach', {'instance_id': iid})['volume']

    def detach_volume(self, vid):
        return self.call('POST', f'/v1/volumes/{vid}/detach', {})['volume']

    def resize_volume(self, vid, size_gib):
        return self.call('PATCH', f'/v1/volumes/{vid}', {'size_gib': size_gib})['volume']

    def delete_volume(self, vid):
        return self.call('DELETE', f'/v1/volumes/{vid}')['volume']

    def wait_volume(self, vid, predicate, tries=80):
        volume = self.get_volume(vid)
        for _ in range(tries):
            volume = self.get_volume(vid)
            if predicate(volume):
                return volume
            time.sleep(3)
        return volume


class Backend:
    """Read-only views of Proxmox and NetBox, to check the API's claims."""

    def __init__(self, node):
        self.node_name = node
        self.proxmox = requests.Session()
        self.proxmox.verify = os.environ.get('PROXMOX_VE_INSECURE', '').lower() not in ('1', 'true', 'yes')
        if not self.proxmox.verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.proxmox.headers['Authorization'] = 'PVEAPIToken=' + os.environ['PROXMOX_VE_API_TOKEN']
        self.base = os.environ['PROXMOX_VE_ENDPOINT'].rstrip('/') + '/api2/json'
        self.netbox = os.environ['NETBOX_SERVER_URL'].rstrip('/')
        self.netbox_headers = {'Authorization': 'Bearer ' + os.environ['NETBOX_API_TOKEN'],
                               'Accept': 'application/json'}

    def pve(self, path):
        response = self.proxmox.get(self.base + path, timeout=30)
        response.raise_for_status()
        return response.json().get('data') or []

    def vms(self, name):
        return [vm for vm in self.pve('/cluster/resources?type=vm') if vm.get('name') == name]

    def holder_disks(self, vmid):
        """Volume IDs the holder has as disks. The test compares before and
        after, so volumes that belong to anyone else do not count as leftovers."""
        response = self.proxmox.get(f'{self.base}/nodes/{self.node_name}/qemu/{vmid}/config', timeout=30)
        if response.status_code != 200:
            return []
        data = response.json().get('data') or {}
        return sorted({str(data[key]).split(',')[0] for key in data
                       if key.startswith(('virtio', 'scsi', 'sata', 'ide', 'unused'))})

    def addresses(self, instance_id):
        response = requests.get(f'{self.netbox}/api/ipam/ip-addresses/?description={instance_id}',
                                headers=self.netbox_headers, timeout=30)
        response.raise_for_status()
        return [(a['address'], a['dns_name']) for a in response.json()['results']]


def holder_vmid():
    """The volume holder's VMID, from site.yaml, so it is not hard-coded twice."""
    try:
        site = yaml.safe_load((ROOT / 'platform/terraform/site.yaml').read_text(encoding='utf-8'))
        return int(site['volume_holder_vmid'])
    except (OSError, KeyError, TypeError, ValueError):
        return 5997


def ssh(address, command, timeout=40):
    argv = ['ssh', '-i', str(SSH_KEY), '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null',
            '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', f'debian@{address}'] + command
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def login(address, tries=48):
    """Wait until the guest answers SSH, and return True once it does."""
    for _ in range(tries):
        if ssh(address, ['true']).returncode == 0:
            return True
        time.sleep(5)
    return False


def port_state(host, port, timeout=6):
    """open / refused / timeout for a TCP connection.

    'refused' means the packet reached the guest, which replied with RST; a
    dropped rule gives 'timeout'. That is the difference a security group makes.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return 'open'
    except socket.timeout:
        return 'timeout'
    except OSError as error:
        return 'refused' if error.errno == errno.ECONNREFUSED else 'timeout'


def wait_port(address, port, wanted, tries=8):
    """Poll a port until it reaches the wanted state, or give up.

    Proxmox applies a rule rewrite as a short insert-then-delete sequence, so a
    connection can briefly succeed while both the old and new rules exist. A
    few seconds of polling distinguishes that transient window from a rule that
    never takes effect.
    """
    state = 'timeout'
    for _ in range(tries):
        state = port_state(address, port)
        if wanted(state):
            return state, True
        time.sleep(2)
    return state, False


def start_listener(address, port):
    # One string, not sh -c: OpenSSH joins separate arguments with spaces, so a
    # sh -c passed as two arguments would lose its quoted command.
    command = (f'nohup python3 -m http.server {port} --bind 0.0.0.0 '
               f'>/tmp/verify-volumes-http.log 2>&1 & sleep 1; echo started')
    return ssh(address, [command]).returncode == 0


def guest_has_device(address, serial, tries=10):
    # Hotplug is not instantaneous, so give the guest a moment to see it.
    for _ in range(tries):
        result = ssh(address, [f'ls /dev/disk/by-id/virtio-{serial} 2>/dev/null'])
        if result.returncode == 0 and serial in result.stdout:
            return True
        time.sleep(2)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--api', default=os.environ.get('SHAKECLOUD_API', DEFAULT_API))
    parser.add_argument('--node', default='apextox', help='Proxmox node name')
    parser.add_argument('--image', default='img-debian13')
    parser.add_argument('--instance-type', default='small')
    parser.add_argument('--holder-vmid', type=int, default=None,
                        help='the volume holder VMID; defaults to the one in platform/terraform/site.yaml')
    parser.add_argument('--keep', action='store_true', help='leave the instance running (for debugging)')
    args = parser.parse_args()
    if args.holder_vmid is None:
        args.holder_vmid = holder_vmid()

    key = os.environ.get('SHAKECLOUD_ACCESS_KEY')
    if not key:
        raise SystemExit('Set SHAKECLOUD_ACCESS_KEY (the bootstrap admin key or any access key)')
    if not SSH_KEY.exists():
        raise SystemExit(f'{SSH_KEY} is missing; the login and listener checks need it')

    public_key = SSH_KEY.with_suffix('.pub').read_text(encoding='utf-8').strip()
    cloud, backend = Cloud(args.api, key), Backend(args.node)

    seen = {}
    instance = cloud.create_instance(args.image, args.instance_type, public_key)
    instance_id = instance['instance_id']
    print(f"created {instance_id}")
    volume_id = group_id = rule_id = None
    baseline_disks = set()
    try:
        running = cloud.wait_instance(instance_id, ('running', 'terminated'))
        seen['state'] = running['state']
        seen['state_reason'] = running.get('state_reason', '')
        seen['address'] = (running.get('private_ip_address') or '').split('/')[0]
        print(f"  state: {running['state']} {running.get('private_ip_address', '')} {running.get('state_reason', '')}".rstrip())
        if seen['address']:
            seen['logged_in'] = login(seen['address'])
            print(f"  logged in: {seen['logged_in']}")

        if seen['logged_in']:
            start_listener(seen['address'], PROBE_PORT)
            subnet = '.'.join(seen['address'].split('.')[:3]) + '.0/24'

            # A group that allows SSH from the LAN and nothing else.
            group = cloud.create_group('verify-volumes')
            group_id = group['group_id']
            cloud.add_ingress(group_id, {'protocol': 'tcp', 'from_port': 22, 'to_port': 22,
                                         'cidr': subnet, 'description': 'ssh'})
            cloud.set_groups(instance_id, [group_id])
            synced = cloud.wait_firewall(instance_id)
            seen['firewall_in_sync'] = synced.get('firewall_state') == 'in-sync'
            print(f"  firewall: {synced.get('firewall_state')}")

            time.sleep(3)
            seen['ssh_open'] = ssh(seen['address'], ['true']).returncode == 0
            # With policy_in DROP the unlisted port times out; if it stays open,
            # the group is not filtering at all.
            state, blocked = wait_port(seen['address'], PROBE_PORT, lambda s: s != 'open')
            seen['probe_blocked'] = blocked
            print(f"  {PROBE_PORT} with ssh-only group: {state}")

            cloud.add_ingress(group_id, {'protocol': 'tcp', 'from_port': PROBE_PORT, 'to_port': PROBE_PORT,
                                         'cidr': subnet, 'description': 'probe'})
            synced = cloud.wait_firewall(instance_id)
            state, allowed = wait_port(seen['address'], PROBE_PORT, lambda s: s == 'open')
            seen['probe_allowed'] = allowed
            print(f"  {PROBE_PORT} after allowing it: {state}")

            group = cloud.call('GET', f'/v1/security-groups/{group_id}')['security_group']
            rule_id = next(r['rule_id'] for r in group['ingress'] if r.get('from_port') == PROBE_PORT)
            cloud.revoke_rule(group_id, rule_id)
            rule_id = None
            cloud.wait_firewall(instance_id)
            state, blocked = wait_port(seen['address'], PROBE_PORT, lambda s: s != 'open')
            seen['probe_blocked_again'] = blocked
            print(f"  {PROBE_PORT} after revoking it: {state}")

        # A volume attached to the running instance, grown, detached, deleted.
        baseline_disks = set(backend.holder_disks(args.holder_vmid))
        volume = cloud.create_volume(1)
        volume_id = volume['volume_id']
        seen['serial'] = volume['serial']
        print(f"  volume {volume_id} (serial {seen['serial']})")
        created = cloud.wait_volume(volume_id, lambda v: v['state'] in ('available', 'error'))
        seen['volume_state_created'] = created['state']

        if created['state'] == 'available' and seen.get('logged_in'):
            cloud.attach_volume(volume_id, instance_id)
            attached = cloud.wait_volume(volume_id, lambda v: (v.get('attachment') or {}).get('state') == 'attached')
            seen['device_seen'] = guest_has_device(seen['address'], seen['serial'])
            print(f"  attached: {(attached.get('attachment') or {}).get('state')} device_seen={seen['device_seen']}")

            resized = cloud.resize_volume(volume_id, 2)
            cloud.wait_volume(volume_id, lambda v: v['state'] == 'in-use' and not v.get('modification_state'))
            print(f"  resized to {resized.get('size_gib')} GiB")

            cloud.detach_volume(volume_id)
            detached = cloud.wait_volume(volume_id, lambda v: v['state'] == 'available' and not v.get('attachment'))
            seen['volume_state_detached'] = detached['state']

        if seen['volume_state_created'] == 'available':
            cloud.delete_volume(volume_id)
            deleted = cloud.wait_volume(volume_id, lambda v: v['state'] in ('deleted', 'error'))
            seen['volume_state_deleted'] = deleted['state']
    finally:
        # A volume has to be off an instance before it or the instance can go,
        # so it is cleaned up first; the group can only be deleted once the
        # instance that uses it is gone.
        if volume_id and seen.get('volume_state_deleted') != 'deleted':
            try:
                volume = cloud.get_volume(volume_id)
                if (volume.get('attachment') or {}).get('state') in ('attached', 'attaching'):
                    cloud.detach_volume(volume_id)
                    cloud.wait_volume(volume_id, lambda v: v['state'] == 'available' and not v.get('attachment'))
                cloud.delete_volume(volume_id)
                cloud.wait_volume(volume_id, lambda v: v['state'] == 'deleted')
            except Exception as error:
                print(f'  could not delete the volume: {error}')
        if args.keep:
            print(f'--keep: leaving {instance_id} running')
        else:
            try:
                cloud.delete_instance(instance_id)
                final = cloud.wait_instance(instance_id, ('terminated',))
                seen['final_state'] = final['state']
                seen['leftover_vms'] = [vm['vmid'] for vm in backend.vms(instance_id)]
                seen['leftover_holder_disks'] = sorted(set(backend.holder_disks(args.holder_vmid)) - baseline_disks)
                seen['leftover_addresses'] = backend.addresses(instance_id)
            except Exception as error:
                seen.setdefault('final_state', f'cleanup failed: {error}')
                print(f'  cleanup failed: {error}')
        if group_id:
            try:
                cloud.delete_group(group_id)
            except Exception as error:  # cleanup must not hide the real result
                print(f'  could not delete the security group: {error}')

    if args.keep:
        return 0
    problems = judge(seen)
    for problem in problems:
        print('FAIL: ' + problem)
    print('PASS: a volume and a security group worked end to end and left nothing behind'
          if not problems else f'FAIL: {len(problems)} problem(s)')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
