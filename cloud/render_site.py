#!/usr/bin/env python3
"""Render the API's site file from the Terraform declarations.

The cloud API needs the node name, storage names, network, images, sizes and
limits. All of those already exist as declarations under platform/terraform,
and copying them into a second file by hand would let the two drift. This turns
them into the one JSON file cloud/api/internal/site reads.

    python3 cloud/render_site.py platform/terraform > site.json

The cloud_api Ansible role runs it on the control machine and installs the
result on cloud-01.
"""
import argparse
import json
from pathlib import Path
import sys

import yaml


def load(directory, name):
    return yaml.safe_load((Path(directory) / name).read_text(encoding='utf-8'))


def render(directory):
    site = load(directory, 'site.yaml')
    pools = load(directory, 'pools.yaml')
    network = load(directory, 'network.yaml')
    images = load(directory, 'images.yaml')
    flavors = load(directory, 'flavors.yaml')
    cloud = load(directory, 'cloud.yaml')

    unmeasured = [name for name, value in {
        'node_name': site['node_name'],
        'storage.vm_disks': site['storage']['vm_disks'],
        'storage.cloud_images': site['storage']['cloud_images'],
        'network.bridge': site['network']['bridge'],
        'network.gateway': site['network']['gateway'],
    }.items() if value == 'UNMEASURED']
    if unmeasured:
        raise SystemExit(f'site.yaml still has unmeasured values: {", ".join(unmeasured)}. '
                         'Run the survey and tools/site-yaml.py first.')

    store = site['storage']['cloud_images']
    shared = {f'img-{name}': {'name': name, 'volume': f'{store}:import/{image["file_name"]}'}
              for name, image in images['images'].items() if image.get('shared_with_cloud')}
    if not shared:
        raise SystemExit('no image in images.yaml has shared_with_cloud: true; '
                         'the cloud API cannot create disks from images it cannot read')

    # The holder VM must live where the cloud API's own ACLs reach, and must not
    # be a VMID the allocator already treats as reserved for something else.
    vmid_from, vmid_to = pools['pools']['cloud']['vmid_from'], pools['pools']['cloud']['vmid_to']
    holder = cloud['volume_holder_vmid']
    if not (vmid_from <= holder <= vmid_to):
        raise SystemExit(f'volume_holder_vmid {holder} is outside the cloud pool range '
                         f'{vmid_from}-{vmid_to}; fix cloud.yaml')
    if holder in cloud['probe_vmids']:
        raise SystemExit(f'volume_holder_vmid {holder} collides with a probe VMID '
                         f'{cloud["probe_vmids"]}; fix cloud.yaml')

    return {
        'node': site['node_name'],
        'pool': 'cloud',
        'vmid_from': pools['pools']['cloud']['vmid_from'],
        'vmid_to': pools['pools']['cloud']['vmid_to'],
        'probe_vmids': cloud['probe_vmids'],
        'volume_holder_vmid': holder,
        'storage': {'vm_disks': site['storage']['vm_disks'], 'images': store},
        'network': {
            'bridge': site['network']['bridge'],
            'gateway': site['network']['gateway'],
            'dns_servers': site['network']['dns_servers'],
            # The cloud API allocates from this range; Terraform only creates it.
            'ip_range_start': network['cloud']['range_start'],
            # After the VLAN cut, the API tags new instances with this; null (0 in
            # Go) means untagged, as before. See docs/operations/vlan.md.
            'vlan_id': network['vlan']['cloud']['vlan_id'],
            # Whether the bridge passes VLAN tags. The API refuses to start with
            # a cloud VLAN on a bridge that cannot carry it.
            'bridge_vlan_aware': site['network']['bridge_vlan_aware'],
        },
        'images': shared,
        'instance_types': {name: {'cpu_cores': flavor['cpu_cores'],
                                  'memory_mib': flavor['memory_mib'],
                                  'memory_min_mib': flavor['memory_min_mib']}
                           for name, flavor in flavors['flavors'].items()},
        'limits': {
            'account_quota': cloud['account_quota'],
            'root_disk_gib': cloud['root_disk_gib'],
            'volume_size_gib': cloud['volume_size_gib'],
            'capacity': cloud['capacity'],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('directory', nargs='?', default=str(Path(__file__).resolve().parent.parent / 'platform/terraform'))
    args = parser.parse_args()
    json.dump(render(args.directory), sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
