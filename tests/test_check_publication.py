import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'check_publication', Path(__file__).resolve().parents[1] / 'tools' / 'check-publication.py')
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)


def hit(text):
    return bool(cp.CREDENTIAL.search(text.encode()))


class CredentialPatternTest(unittest.TestCase):
    def test_detects_real_formats(self):
        for text in [
            'tskey-auth-' + 'kAbCdE1CNTRL-' + 'a' * 20,
            'sca_' + 'abcdefghij234567abcd' + '.' + 'A' * 43,
            'github_pat_' + 'A' * 30,
            'https://discord.com/api/webhooks/123456789012345678/' + 'a' * 40,
            'M' + 'A' * 23 + '.' + 'abcdef' + '.' + 'B' * 27,
            'xoxb-' + '1234567890-abcdefghij',
            'AKIA' + 'ABCDEFGHIJKLMNOP',
            'postgres://app:' + 'Sup3rS3cretPw@db.internal:5432/app',
            'ghp_' + 'a' * 36,
        ]:
            self.assertTrue(hit(text), text)

    def test_ignores_placeholders(self):
        for text in [
            'sca_example.secret',
            'postgres://postgres:postgres@localhost:5432/postgres',
            'postgres://user:password@host/db',
            'postgres://user:${DB_PASSWORD}@host/db',
            'https://user:<password>@host/',
            'https://host/path:80',
            'tskey-auth-',
        ]:
            self.assertFalse(hit(text), text)


class SopsTest(unittest.TestCase):
    def test_all_encrypted(self):
        self.assertEqual(cp.sops_plaintext('a: ENC[x]\nb:\n  - ENC[y]\nc: ""\nsops:\n  version: 3.9\n'), [])

    def test_one_plaintext_rejected(self):
        self.assertEqual(cp.sops_plaintext('a: ENC[x]\nb:\n  c: plain\nsops:\n  mac: ENC[z]\n'), ['b.c'])

    def test_plain_list_item_rejected(self):
        self.assertEqual(cp.sops_plaintext('a:\n  - ENC[x]\n  - oops\n'), ['a[1]'])


if __name__ == '__main__':
    unittest.main()
