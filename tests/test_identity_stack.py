import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'stacks/identity'
SPEC = importlib.util.spec_from_file_location('identity_configure', SOURCE / 'configure.py')
configure = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(configure)

FLOWS = {configure.AUTHORIZATION_FLOW: 'auth', configure.INVALIDATION_FLOW: 'inval'}
CREDENTIAL = {'client_id': 'cloud', 'client_secret': 's'}


class ProviderTests(unittest.TestCase):
    def body(self, url='http://192.0.2.5:8080'):
        return configure.provider_body(FLOWS, ['b', 'a'], 'key', CREDENTIAL, url)

    def test_subject_survives_recreating_the_provider(self):
        # hashed_user_id is derived per provider; recreating it would orphan
        # every account's resources in the cloud API database.
        self.assertEqual(self.body()['sub_mode'], 'user_uuid')

    def test_redirect_is_a_single_strict_uri_without_trailing_slash_doubling(self):
        self.assertEqual(self.body('http://192.0.2.5:8080/')['redirect_uris'],
                         [{'matching_mode': 'strict', 'url': 'http://192.0.2.5:8080/auth/callback',
                           'redirect_uri_type': 'authorization'}])

    def test_a_missing_portal_url_is_refused_rather_than_guessed(self):
        with self.assertRaises(ValueError):
            self.body('')

    def test_unchanged_provider_reports_no_drift_even_with_reordered_lists(self):
        current = dict(self.body(), property_mappings=['a', 'b'], client_secret='not echoed')
        self.assertEqual(configure.drifted(current, self.body()), [])

    def test_a_loosened_redirect_is_detected_as_drift(self):
        current = dict(self.body(), redirect_uris=[{'matching_mode': 'regex', 'url': '.*'}])
        self.assertEqual(configure.drifted(current, self.body()), ['redirect_uris'])


class InventoryNameTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_no_ansible_group_shares_a_name_with_a_declared_host(self):
        # A host and a group with the same name make nb_inventory raise
        # "can't add group to itself" and the whole inventory fails to load.
        import yaml
        tags = yaml.safe_load((self.ROOT / 'platform/terraform/tags.yaml').read_text())['tags']
        hosts = yaml.safe_load((self.ROOT / 'platform/terraform/hosts.yaml').read_text())['hosts']
        groups = {tag['ansible_group'] for tag in tags.values() if tag['ansible_group']}
        self.assertEqual(groups & set(hosts), set())


if __name__ == '__main__':
    unittest.main()
