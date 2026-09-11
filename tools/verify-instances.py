#!/usr/bin/env python3
"""Create an instance through the API, log into it, terminate it, and check that
nothing is left behind.

This is the end-to-end question no unit test can answer: whether the seed ISO
this deployment builds actually configures a real guest, and whether a terminate
releases the VM, its disk, the ISO and the address on real hardware. Run it
after changing cloud/api, after a Proxmox upgrade, and before trusting a fresh
deployment.

    export SHAKECLOUD_ACCESS_KEY=$(ssh -i ~/.ssh/id_ed25519_pve \\
      debian@192.168.10.205 sudo cat /opt/cloud-stack/secrets/bootstrap_admin_key)
    sops exec-env platform/sops/cloudapi.sops.yaml 'python3 tools/verify-instances.py'

The API key does the creating; the Proxmox and NetBox credentials are only read,
to check from the other side that what the API claims is really there. Exit
status is non-zero if anything failed, so an unattended runner can gate on it.

The instance is terminated even when a check fails, so a bad run does not leave
a VM behind.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

import requests
import urllib3

DEFAULT_API = 'https://cloud.apextox.dpdns.org'
SSH_KEY = Path.home() / '.ssh/id_ed25519_pve'


def judge(seen):
    """Return everything that is wrong with a run. Empty means it passed.

    Kept apart from the calls so its judgement can be tested without hardware
    (tests/test_verify_instances.py): a check that reads a leftover VM or a
    failed login as success would be worse than no check at all.
    """
    problems = []
    if seen.get('state') != 'running':
        problems.append(f"the instance never reached running: {seen.get('state')} {seen.get('state_reason', '')}".strip())
    if not seen.get('address'):
        problems.append('no address was allocated')
    if not seen.get('netbox_addresses'):
        problems.append('NetBox holds no address for the instance')
    if not seen.get('vm'):
        problems.append('Proxmox holds no VM for the instance')
    if not seen.get('seed_iso'):
        problems.append('the seed ISO is missing')
    if not seen.get('logged_in'):
        problems.append('could not log in over SSH: cloud-init did not apply the seed ISO')
    elif seen.get('guest_address') and seen['guest_address'] != seen.get('address'):
        problems.append(f"the guest has {seen['guest_address']}, not the allocated {seen['address']}")
    if seen.get('final_state') != 'terminated':
        problems.append(f"the instance did not reach terminated: {seen.get('final_state')}")
    for name, label in (('leftover_vms', 'VMs'), ('leftover_isos', 'seed ISOs'),
                        ('leftover_disks', 'disks'), ('leftover_addresses', 'NetBox addresses')):
        if seen.get(name):
            problems.append(f'{label} left behind after terminate: {seen[name]}')
    return problems


class Cloud:
    def __init__(self, base, key):
        self.base = base.rstrip('/')
        self.headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}

    def post(self, path, body):
        response = requests.post(self.base + path, headers=self.headers, json=body, timeout=60)
        response.raise_for_status()
        return response.json()['instance']

    def get(self, instance_id):
        response = requests.get(f'{self.base}/v1/instances/{instance_id}', headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json()['instance']

    def delete(self, instance_id):
        response = requests.delete(f'{self.base}/v1/instances/{instance_id}', headers=self.headers, timeout=60)
        response.raise_for_status()
        return response.json()['instance']

    def wait(self, instance_id, until, tries=72):
        state, instance = None, self.get(instance_id)
        for _ in range(tries):
            instance = self.get(instance_id)
            if instance['state'] != state:
                state = instance['state']
                print(f"      state: {state} {instance.get('private_ip_address', '')} {instance.get('state_reason', '')}".rstrip())
            if state in until:
                return instance
            time.sleep(5)
        return instance


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
        self.netbox_headers = {'Authorization': 'Bearer ' + os.environ['NETBOX_API_TOKEN'], 'Accept': 'application/json'}

    def pve(self, path):
        response = self.proxmox.get(self.base + path, timeout=30)
        response.raise_for_status()
        return response.json().get('data') or []

    def vms(self, name):
        return [vm for vm in self.pve('/cluster/resources?type=vm') if vm.get('name') == name]

    def isos(self, instance_id):
        return [v['volid'] for v in self.pve(f'/nodes/{self.node_name}/storage/cloud-images/content?content=iso')
                if instance_id in v['volid']]

    def disks(self, vmid):
        return [v['volid'] for v in self.pve(f'/nodes/{self.node_name}/storage/local-lvm/content')
                if f'vm-{vmid}-disk' in v['volid']]

    def addresses(self, instance_id):
        response = requests.get(f'{self.netbox}/api/ipam/ip-addresses/?description={instance_id}',
                                headers=self.netbox_headers, timeout=30)
        response.raise_for_status()
        return [(a['address'], a['dns_name']) for a in response.json()['results']]


def login(address, tries=48):
    """Return the guest's own view of itself, or None if it never answered."""
    command = ['ssh', '-i', str(SSH_KEY), '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null',
               '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', f'debian@{address.split("/")[0]}',
               'hostname; hostname -I; ip route show default; cloud-init status']
    for _ in range(tries):
        finished = subprocess.run(command, capture_output=True, text=True, timeout=40)
        if finished.returncode == 0:
            return finished.stdout.strip()
        time.sleep(5)
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--api', default=os.environ.get('SHAKECLOUD_API', DEFAULT_API))
    parser.add_argument('--node', default='apextox', help='Proxmox node name, for the storage checks')
    parser.add_argument('--image', default='img-debian13')
    parser.add_argument('--instance-type', default='small')
    parser.add_argument('--keep', action='store_true', help='leave the instance running (for debugging)')
    args = parser.parse_args()

    key = os.environ.get('SHAKECLOUD_ACCESS_KEY')
    if not key:
        raise SystemExit('Set SHAKECLOUD_ACCESS_KEY (the bootstrap admin key or any access key)')
    if not SSH_KEY.exists():
        raise SystemExit(f'{SSH_KEY} is missing; the login check needs the key whose public half goes into user-data')

    cloud, backend = Cloud(args.api, key), Backend(args.node)
    public_key = (SSH_KEY.with_suffix('.pub')).read_text(encoding='utf-8').strip()

    seen = {}
    instance = cloud.post('/v1/instances', {
        'image_id': args.image, 'instance_type': args.instance_type, 'root_disk_gib': 10,
        'user_data': '#cloud-config\nssh_authorized_keys:\n  - ' + public_key + '\n',
        'tags': {'Name': 'verify-instances'},
        'client_token': 'verify-' + str(int(time.time())),
    })
    instance_id = instance['instance_id']
    print(f'created {instance_id} (mac {instance["mac_address"]})')
    try:
        running = cloud.wait(instance_id, ('running', 'terminated'))
        seen['state'] = running['state']
        seen['state_reason'] = running.get('state_reason', '')
        seen['address'] = running.get('private_ip_address', '')

        vms = backend.vms(instance_id)
        seen['vm'] = vms
        seen['seed_iso'] = backend.isos(instance_id)
        seen['netbox_addresses'] = backend.addresses(instance_id)
        print(f'  proxmox: {[(vm["vmid"], vm["status"], vm["pool"]) for vm in vms]}')
        print(f'  seed ISO: {seen["seed_iso"]}')
        print(f'  netbox: {seen["netbox_addresses"]}')

        if seen['address']:
            guest = login(seen['address'])
            seen['logged_in'] = guest is not None
            if guest:
                print('  logged in:\n    ' + guest.replace('\n', '\n    '))
                fields = guest.split('\n')
                seen['guest_address'] = (fields[1].split() or [''])[0] + '/' + seen['address'].split('/')[1]
    finally:
        if args.keep:
            print(f'--keep: leaving {instance_id} running')
        else:
            cloud.delete(instance_id)
            final = cloud.wait(instance_id, ('terminated',))
            seen['final_state'] = final['state']
            seen['leftover_vms'] = [vm['vmid'] for vm in backend.vms(instance_id)]
            seen['leftover_isos'] = backend.isos(instance_id)
            seen['leftover_disks'] = backend.disks(vms[0]['vmid']) if seen.get('vm') else []
            seen['leftover_addresses'] = backend.addresses(instance_id)

    if args.keep:
        return 0
    problems = judge(seen)
    for problem in problems:
        print('FAIL: ' + problem)
    print('PASS: an instance was created, logged into, terminated, and left nothing behind' if not problems
          else f'FAIL: {len(problems)} problem(s)')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
