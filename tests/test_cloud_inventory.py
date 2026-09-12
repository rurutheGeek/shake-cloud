"""Check the cloud dynamic inventory against fixtures, never the live API.

The inventory decides which cloud VMs Ansible may deploy to. A bug that adds
a stopped instance, a foreign account's instance, or a stale address from a
replaced VM would deploy to the wrong machine, and Ansible reports no error
for a host that is simply absent. The instances here are dicts shaped like the
`instances` array of GET /v1/instances; the API is never contacted.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'inventory_cloud', ROOT / 'platform/ansible/inventory.cloud.py')
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)

ACCOUNT = '123456789012'
OTHER_ACCOUNT = '999999999999'
KEY = 'sca_' + 'a' * 20 + '.' + 'B' * 43
MEDIA = 'i-a06df9a2dfd1ce6db'
OLD = 'i-00000000000000001'
REPLACEMENT = 'i-00000000000000002'
FOREIGN = 'i-00000000000000003'
ADDRESS = '192.168.10.101'


def instance(instance_id=MEDIA, account=ACCOUNT, state='running',
             address=ADDRESS, name='media-01', **extra):
    value = {
        'instance_id': instance_id,
        'account_id': account,
        'state': state,
        'private_ip_address': address,
        'tags': {'Name': name},
    }
    value.update(extra)
    return value


def declaration(instances=None, account=ACCOUNT):
    if instances is None:
        instances = {MEDIA: ['media']}
    return {'account_id': account, 'instances': instances}


class ManagedHostsTests(unittest.TestCase):
    """Only declared, running, addressable, settled instances are emitted."""

    def hosts(self, *instances, declared=None, account=ACCOUNT):
        return inventory.managed_hosts(list(instances), declaration(declared, account))

    def test_a_running_declared_instance_is_emitted(self):
        self.assertEqual(
            self.hosts(instance()),
            {MEDIA: {'ansible_host': ADDRESS, 'ansible_user': 'debian', 'cloud_name': 'media-01'}})

    def test_the_connection_user_is_the_images_cloud_init_user(self):
        # The Debian cloud image creates `debian`; without this Ansible would
        # try to log in as whoever runs the playbook.
        self.assertEqual(self.hosts(instance())[MEDIA]['ansible_user'], 'debian')

    def test_a_stopped_instance_is_not_emitted(self):
        self.assertEqual(self.hosts(instance(state='stopped')), {})

    def test_a_deleted_or_unsettled_instance_is_not_emitted(self):
        for state in ('terminated', 'shutting-down', 'pending', 'stopping'):
            self.assertEqual(self.hosts(instance(state=state)), {}, state)

    def test_an_instance_without_an_address_is_not_emitted(self):
        for address in (None, '', '   '):
            self.assertEqual(self.hosts(instance(address=address)), {}, repr(address))

    def test_a_display_name_does_not_decide_membership(self):
        # Two VMs are called media-01; only the declared id may be deployed to.
        impostor = instance(instance_id=FOREIGN)
        self.assertEqual(list(self.hosts(instance(), impostor)), [MEDIA])

    def test_an_instance_of_another_account_is_not_emitted(self):
        self.assertEqual(self.hosts(instance(account=OTHER_ACCOUNT)), {})

    def test_an_undeclared_id_is_not_emitted(self):
        self.assertEqual(self.hosts(instance(), declared={OLD: ['media']}), {})

    def test_a_transitioning_instance_is_not_emitted(self):
        # pending_action is the lifecycle operation still running; a firewall
        # push is the other transition that writes to the guest.
        for pending in ('launch', 'start', 'stop', 'reboot', 'terminate'):
            self.assertEqual(self.hosts(instance(pending_action=pending)), {}, pending)
        self.assertEqual(self.hosts(instance(firewall_state='applying')), {})

    def test_a_settled_instance_is_emitted(self):
        self.assertIn(MEDIA, self.hosts(instance(pending_action='', firewall_state='in-sync')))

    def test_a_reused_address_belongs_to_the_new_id_only(self):
        # The old VM is terminated and the replacement got the same address.
        old = instance(instance_id=OLD, state='terminated')
        new = instance(instance_id=REPLACEMENT)
        hosts = self.hosts(old, new, declared={OLD: ['media'], REPLACEMENT: ['media']})
        self.assertEqual(list(hosts), [REPLACEMENT])
        self.assertEqual(hosts[REPLACEMENT]['ansible_host'], ADDRESS)

    def test_two_declared_ids_that_share_an_address_stay_separate_hosts(self):
        # The host key is the id, never the address and never the name.
        declared = {OLD: ['media'], REPLACEMENT: ['media']}
        hosts = self.hosts(instance(instance_id=OLD), instance(instance_id=REPLACEMENT), declared=declared)
        self.assertEqual(sorted(hosts), sorted([OLD, REPLACEMENT]))

    def test_cloud_name_is_optional_and_does_not_leak_the_raw_tags(self):
        without_tags = instance()
        del without_tags['tags']
        self.assertEqual(self.hosts(without_tags), {MEDIA: {'ansible_host': ADDRESS, 'ansible_user': 'debian'}})


class BuildInventoryTests(unittest.TestCase):
    def test_list_assigns_hosts_to_declared_groups_and_meta_hostvars(self):
        declared = {MEDIA: ['media', 'lab'], OLD: ['lab']}
        hosts = inventory.managed_hosts(
            [instance(), instance(instance_id=OLD, address='192.168.10.102')], declaration(declared))
        result = inventory.build_inventory(hosts, declaration(declared))
        self.assertEqual(result['media'], [MEDIA])
        self.assertEqual(sorted(result['lab']), sorted([MEDIA, OLD]))
        self.assertEqual(result['_meta']['hostvars'][MEDIA]['ansible_host'], ADDRESS)

    def test_no_group_is_emitted_when_nothing_matches(self):
        self.assertEqual(inventory.build_inventory({}, declaration()),
                         {'_meta': {'hostvars': {}}})


class DeclarationTests(unittest.TestCase):
    def write(self, directory, text, name='cloud-inventory.yml'):
        path = Path(directory) / name
        path.write_text(text, encoding='utf-8')
        return path

    def test_a_valid_declaration_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, 'account_id: "123456789012"\n'
                                   'instances:\n  i-a06df9a2dfd1ce6db: [media]\n')
            self.assertEqual(inventory.load_declaration(path), declaration())

    def test_invalid_yaml_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, 'account_id: [\n')
            with self.assertRaises(inventory.InventoryError):
                inventory.load_declaration(path)

    def test_a_missing_account_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, 'instances:\n  i-a06df9a2dfd1ce6db: [media]\n')
            with self.assertRaises(inventory.InventoryError):
                inventory.load_declaration(path)

    def test_a_bad_instance_id_is_an_error(self):
        for bad in ('media-01', 'i-NOTHEX', 42):
            with tempfile.TemporaryDirectory() as tmp:
                path = self.write(tmp, yaml.safe_dump(
                    {'account_id': ACCOUNT, 'instances': {bad: ['media']}}))
                with self.assertRaises(inventory.InventoryError, msg=repr(bad)):
                    inventory.load_declaration(path)

    def test_an_empty_group_list_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, yaml.safe_dump(
                {'account_id': ACCOUNT, 'instances': {MEDIA: []}}))
            with self.assertRaises(inventory.InventoryError):
                inventory.load_declaration(path)

    def test_an_unknown_key_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, yaml.safe_dump(
                {'account_id': ACCOUNT, 'accounts': {}, 'instances': {MEDIA: ['media']}}))
            with self.assertRaises(inventory.InventoryError):
                inventory.load_declaration(path)

    def test_a_group_outside_the_netbox_vocabulary_is_refused(self):
        with self.assertRaises(inventory.InventoryError):
            inventory.validate_groups(declaration({MEDIA: ['mediia']}), {'media'})

    def test_the_checked_in_declaration_uses_the_netbox_group_vocabulary(self):
        # The declaration is the deployment target list; it must stay valid
        # against the inventory it is merged with.
        loaded = inventory.load_declaration(ROOT / 'platform/ansible/cloud-inventory.yml')
        allowed = inventory.load_allowed_groups(ROOT / 'platform/ansible/inventory.netbox.yml')
        inventory.validate_groups(loaded, allowed)
        self.assertIn(MEDIA, loaded['instances'])
        self.assertEqual(loaded['instances'][MEDIA], ['media'])


class Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FetchTests(unittest.TestCase):
    def test_the_request_authenticates_and_filters_by_account(self):
        seen = {}

        def opener(request, timeout=None):
            seen['url'] = request.full_url
            seen['authorization'] = request.get_header('Authorization')
            seen['timeout'] = timeout
            return Response(json.dumps({'instances': [instance()]}).encode())

        instances = inventory.fetch_instances('https://cloud.example.test/', KEY, ACCOUNT, opener=opener)
        self.assertEqual(instances, [instance()])
        self.assertEqual(seen['url'],
                         'https://cloud.example.test/v1/instances?account_id=' + ACCOUNT)
        self.assertEqual(seen['authorization'], 'Bearer ' + KEY)
        self.assertNotIn(KEY, seen['url'])
        self.assertEqual(seen['timeout'], inventory.HTTP_TIMEOUT_SECONDS)

    def test_an_http_error_is_an_inventory_error(self):
        def opener(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 401, 'Unauthorized', {}, None)

        with self.assertRaises(inventory.InventoryError) as caught:
            inventory.fetch_instances('https://cloud.example.test', KEY, ACCOUNT, opener=opener)
        self.assertIn('401', str(caught.exception))

    def test_a_network_error_is_an_inventory_error(self):
        def opener(request, timeout=None):
            raise urllib.error.URLError('name resolution failed')

        with self.assertRaises(inventory.InventoryError):
            inventory.fetch_instances('https://cloud.example.test', KEY, ACCOUNT, opener=opener)

    def test_an_invalid_json_response_is_an_inventory_error(self):
        def opener(request, timeout=None):
            return Response(b'<html>bad gateway</html>')

        with self.assertRaises(inventory.InventoryError):
            inventory.fetch_instances('https://cloud.example.test', KEY, ACCOUNT, opener=opener)

    def test_a_response_without_an_instances_list_is_an_error(self):
        def opener(request, timeout=None):
            return Response(b'{"error": "nope"}')

        with self.assertRaises(inventory.InventoryError):
            inventory.fetch_instances('https://cloud.example.test', KEY, ACCOUNT, opener=opener)

    def test_a_malformed_instance_entry_is_an_error(self):
        def opener(request, timeout=None):
            return Response(b'{"instances": ["not-an-object"]}')

        with self.assertRaises(inventory.InventoryError):
            inventory.fetch_instances('https://cloud.example.test', KEY, ACCOUNT, opener=opener)

    def test_the_key_never_appears_in_an_error(self):
        def opener(request, timeout=None):
            raise urllib.error.URLError('boom')

        with self.assertRaises(inventory.InventoryError) as caught:
            inventory.fetch_instances('https://cloud.example.test', KEY, ACCOUNT, opener=opener)
        self.assertNotIn(KEY, str(caught.exception))


class MainTests(unittest.TestCase):
    """Exercise --list and --host the way Ansible calls them."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.declaration_path = self.write('cloud-inventory.yml', {
            'account_id': ACCOUNT, 'instances': {MEDIA: ['media']}})
        self.netbox_path = self.write('inventory.netbox.yml', {
            'groups': {'media': "'media-stack' in tags"}})
        patcher = mock.patch.multiple(
            inventory,
            DECLARATION_FILE=self.declaration_path,
            NETBOX_INVENTORY=self.netbox_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, name, data):
        path = Path(self.tmp.name) / name
        path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
        return path

    def run_main(self, argv=('--list',), env=None):
        values = {'SHAKECLOUD_ACCESS_KEY': KEY,
                  'SHAKECLOUD_ENDPOINT': 'https://cloud.example.test'}
        for name, value in (env or {}).items():
            if value is None:
                values.pop(name, None)
            else:
                values[name] = value
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, values, clear=True):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = inventory.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_list_emits_the_declared_host_and_group(self):
        with mock.patch.object(inventory, 'fetch_instances', return_value=[instance()]):
            code, out, err = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(err, '')
        self.assertEqual(json.loads(out), {
            '_meta': {'hostvars': {MEDIA: {
                'ansible_host': ADDRESS, 'ansible_user': 'debian', 'cloud_name': 'media-01'}}},
            'media': [MEDIA],
        })

    def test_host_emits_only_the_requested_host_variables(self):
        with mock.patch.object(inventory, 'fetch_instances', return_value=[instance()]):
            code, out, err = self.run_main(('--host', MEDIA))
        self.assertEqual(code, 0)
        self.assertEqual(err, '')
        self.assertEqual(json.loads(out), {'ansible_host': ADDRESS, 'ansible_user': 'debian', 'cloud_name': 'media-01'})

    def test_host_is_empty_for_a_host_that_may_not_be_deployed_to(self):
        for value in (instance(state='stopped'), instance(pending_action='reboot')):
            with mock.patch.object(inventory, 'fetch_instances', return_value=[value]):
                code, out, _ = self.run_main(('--host', MEDIA))
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out), {})

    def test_host_is_empty_for_an_unknown_host(self):
        with mock.patch.object(inventory, 'fetch_instances', return_value=[instance()]):
            code, out, _ = self.run_main(('--host', FOREIGN))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {})

    def test_a_missing_key_fails_without_output(self):
        code, out, err = self.run_main(env={'SHAKECLOUD_ACCESS_KEY': ''})
        self.assertEqual(code, 1)
        self.assertEqual(out, '')
        self.assertIn('SHAKECLOUD_ACCESS_KEY', err)

    def test_a_malformed_key_fails_without_output(self):
        code, out, _ = self.run_main(env={'SHAKECLOUD_ACCESS_KEY': 'not-a-key'})
        self.assertEqual(code, 1)
        self.assertEqual(out, '')

    def test_an_api_failure_fails_without_output_and_without_the_key(self):
        def failing(*args, **kwargs):
            raise inventory.InventoryError('GET /v1/instances failed: HTTP 503')

        with mock.patch.object(inventory, 'fetch_instances', failing):
            code, out, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(out, '')
        self.assertIn('503', err)
        self.assertNotIn(KEY, err)

    def test_an_unknown_group_in_the_declaration_fails(self):
        self.declaration_path.write_text(yaml.safe_dump(
            {'account_id': ACCOUNT, 'instances': {MEDIA: ['mediia']}}), encoding='utf-8')
        with mock.patch.object(inventory, 'fetch_instances', return_value=[instance()]):
            code, out, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(out, '')
        self.assertIn('mediia', err)

    def test_the_api_is_read_on_every_run(self):
        with mock.patch.object(inventory, 'fetch_instances', return_value=[instance()]) as fetch:
            self.run_main()
            self.run_main()
        self.assertEqual(fetch.call_count, 2)

    def test_the_endpoint_can_be_overridden_and_defaults_to_the_public_one(self):
        with mock.patch.object(inventory, 'fetch_instances', return_value=[]) as fetch:
            self.run_main(env={'SHAKECLOUD_ENDPOINT': 'https://alt.example.test/'})
        self.assertEqual(fetch.call_args.args[0], 'https://alt.example.test/')
        with mock.patch.object(inventory, 'fetch_instances', return_value=[]) as fetch:
            self.run_main(env={'SHAKECLOUD_ENDPOINT': None})
        self.assertEqual(fetch.call_args.args[0], inventory.DEFAULT_ENDPOINT)


if __name__ == '__main__':
    unittest.main()
