import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('identity_attributes', Path(__file__).resolve().parents[1] / 'stacks/hub/identity_attributes.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.user = {'email': 'owner@example.test', 'attributes': {'email_verified': True, 'other': 'keep'}}

    def test_reconcile_preserves_existing_verification(self):
        result = module.attributes_for({'email': self.user['email']}, self.user)
        self.assertTrue(result['email_verified'])
        self.assertEqual(result['other'], 'keep')

    def test_changed_email_requires_new_verification(self):
        self.assertFalse(module.attributes_for({'email': 'new@example.test'}, self.user)['email_verified'])

    def test_new_user_is_unverified(self):
        self.assertFalse(module.attributes_for({'email': 'new@example.test'}, None)['email_verified'])

    def test_explicit_revocation_is_respected(self):
        self.assertFalse(module.attributes_for({'email': self.user['email'], 'email_verified': False}, self.user)['email_verified'])

    def test_only_boolean_true_counts_as_confirmation(self):
        self.assertFalse(module.attributes_for({'email': self.user['email'], 'email_verified': 'true'}, self.user)['email_verified'])


if __name__ == '__main__':
    unittest.main()
