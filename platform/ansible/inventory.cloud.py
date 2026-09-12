#!/usr/bin/env python3
"""Ansible dynamic inventory for shake-cloud instances (I03).

Reads GET /v1/instances on every run and emits only the cloud VMs that are
explicitly declared in cloud-inventory.yml. Nothing is cached, so a VM that
was deleted, stopped or re-created cannot be reached through a stale address.
The API is read-only here; this script never creates, starts or deletes.

    export SHAKECLOUD_ACCESS_KEY='sca_<id>.<secret>'
    ansible-inventory -i platform/ansible/inventory.netbox.yml \\
        -i platform/ansible/inventory.cloud.py --graph

A host is the instance_id (stable across renames and IP reuse); ansible_host
is private_ip_address and ansible_user is debian, the user the Debian cloud
image's cloud-init creates. tags.Name is reported as cloud_name for display
only and never decides group membership: group assignment comes from the
checked-in declaration. Failures print to stderr and exit non-zero rather than
fall back to any cached answer.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

import yaml

DEFAULT_ENDPOINT = 'https://cloud.apextox.dpdns.org'
HERE = Path(__file__).resolve().parent
DECLARATION_FILE = HERE / 'cloud-inventory.yml'
NETBOX_INVENTORY = HERE / 'inventory.netbox.yml'
HTTP_TIMEOUT_SECONDS = 30

INSTANCE_ID = re.compile(r'^i-[0-9a-f]{17}$')
ACCOUNT_ID = re.compile(r'^[0-9]{12}$')
ACCESS_KEY = re.compile(r'^sca_[a-z2-7]{20}\.[A-Za-z0-9_-]{43}$')


class InventoryError(Exception):
    """A problem the operator can fix. The message never carries the key."""


def load_mapping(path):
    try:
        text = Path(path).read_text(encoding='utf-8')
    except OSError as error:
        raise InventoryError(f'{path}: cannot read: {error}') from error
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise InventoryError(f'{path}: invalid YAML: {error}') from error


def load_declaration(path):
    """Return the account and instance->groups mapping, or raise.

    The declaration is what makes deployment targets explicit; a typo in it
    must stop the run instead of silently targeting nothing.
    """
    data = load_mapping(path)
    if not isinstance(data, dict):
        raise InventoryError(f'{path}: must be a mapping with account_id and instances')
    unknown = sorted(set(data) - {'account_id', 'instances'})
    if unknown:
        raise InventoryError(f'{path}: unknown key(s): {", ".join(unknown)}')
    account_id = data.get('account_id')
    if not isinstance(account_id, str) or not ACCOUNT_ID.match(account_id):
        raise InventoryError(f'{path}: account_id must be 12 digits')
    instances = data.get('instances')
    if not isinstance(instances, dict) or not instances:
        raise InventoryError(f'{path}: instances must be a non-empty mapping of instance id to groups')
    cleaned = {}
    for instance_id, groups in instances.items():
        if not isinstance(instance_id, str) or not INSTANCE_ID.match(instance_id):
            raise InventoryError(f'{path}: {instance_id!r} is not an instance id (i-<17 hex>)')
        if not isinstance(groups, list) or not groups:
            raise InventoryError(f'{path}: {instance_id}: groups must be a non-empty list')
        for group in groups:
            if not isinstance(group, str) or not group.strip():
                raise InventoryError(f'{path}: {instance_id}: group names must be non-empty strings')
        cleaned[instance_id] = list(dict.fromkeys(groups))
    return {'account_id': account_id, 'instances': cleaned}


def load_allowed_groups(path):
    """The group vocabulary is the one inventory.netbox.yml declares."""
    data = load_mapping(path)
    groups = data.get('groups') if isinstance(data, dict) else None
    if not isinstance(groups, dict) or not groups:
        raise InventoryError(f'{path}: no groups: mapping to validate group names against')
    return set(groups)


def validate_groups(declaration, allowed):
    for instance_id, groups in declaration['instances'].items():
        for group in groups:
            if group not in allowed:
                raise InventoryError(
                    f'group {group!r} for {instance_id} is not declared in inventory.netbox.yml: groups:')


def parse_instances(payload):
    try:
        data = json.loads(payload)
    except (TypeError, ValueError) as error:
        raise InventoryError(f'the API response is not valid JSON: {error}') from error
    if not isinstance(data, dict) or not isinstance(data.get('instances'), list):
        raise InventoryError('the API response has no instances list')
    for instance in data['instances']:
        if not isinstance(instance, dict):
            raise InventoryError('the API response contains a malformed instance entry')
    return data['instances']


def fetch_instances(endpoint, access_key, account_id, opener=urllib.request.urlopen):
    """GET /v1/instances for one account. The key rides in a header only."""
    query = urllib.parse.urlencode({'account_id': account_id})
    url = endpoint.rstrip('/') + '/v1/instances?' + query
    request = urllib.request.Request(url, headers={
        'Authorization': 'Bearer ' + access_key,
        'Accept': 'application/json',
    })
    try:
        with opener(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        raise InventoryError(f'GET /v1/instances failed: HTTP {error.code} {error.reason}') from error
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise InventoryError(f'GET /v1/instances failed: {error}') from error
    return parse_instances(payload)


def managed_hosts(instances, declaration):
    """The subset of instances that may be deployed to, keyed by instance_id.

    Every condition is conjunctive: running, an address, no lifecycle action
    in flight, no firewall change in flight, the declared account and an
    explicitly declared id. The display name is never consulted.
    """
    declared = declaration['instances']
    account_id = declaration['account_id']
    hosts = {}
    for instance in instances:
        instance_id = instance.get('instance_id')
        if not isinstance(instance_id, str) or instance_id not in declared:
            continue
        if instance.get('account_id') != account_id:
            continue
        if instance.get('state') != 'running':
            continue
        address = instance.get('private_ip_address')
        if not isinstance(address, str) or not address.strip():
            continue
        if instance.get('pending_action') or instance.get('firewall_state') == 'applying':
            continue
        # The image is the Debian genericcloud one; cloud-init's user is debian.
        host = {'ansible_host': address.strip(), 'ansible_user': 'debian'}
        tags = instance.get('tags')
        name = tags.get('Name') if isinstance(tags, dict) else None
        if isinstance(name, str) and name.strip():
            host['cloud_name'] = name.strip()
        hosts[instance_id] = host
    return hosts


def build_inventory(hosts, declaration):
    groups = {}
    for instance_id in hosts:
        for group in declaration['instances'][instance_id]:
            groups.setdefault(group, []).append(instance_id)
    inventory = {'_meta': {'hostvars': hosts}}
    inventory.update(groups)
    return inventory


def gather(declaration_path, netbox_path, endpoint, access_key, opener=urllib.request.urlopen):
    declaration = load_declaration(declaration_path)
    validate_groups(declaration, load_allowed_groups(netbox_path))
    instances = fetch_instances(endpoint, access_key, declaration['account_id'], opener=opener)
    return declaration, managed_hosts(instances, declaration)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Ansible dynamic inventory for shake-cloud instances.')
    parser.add_argument('--list', action='store_true', help='emit the whole inventory as JSON (the default)')
    parser.add_argument('--host', help='emit the variables for one host as JSON')
    args = parser.parse_args(argv)

    access_key = os.environ.get('SHAKECLOUD_ACCESS_KEY', '').strip()
    endpoint = (os.environ.get('SHAKECLOUD_ENDPOINT') or DEFAULT_ENDPOINT).strip()
    try:
        if not access_key:
            raise InventoryError('set SHAKECLOUD_ACCESS_KEY to a sca_<id>.<secret> access key')
        if not ACCESS_KEY.match(access_key):
            raise InventoryError('SHAKECLOUD_ACCESS_KEY is not in the sca_<id>.<secret> form')
        declaration, hosts = gather(DECLARATION_FILE, NETBOX_INVENTORY, endpoint, access_key)
        if args.host is not None:
            output = hosts.get(args.host, {})
        else:
            output = build_inventory(hosts, declaration)
    except InventoryError as error:
        print(f'inventory.cloud: {error}', file=sys.stderr)
        return 1
    json.dump(output, sys.stdout)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
