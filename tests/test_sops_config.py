"""Guard the SOPS configuration against the two mistakes that broke first use.

sops searches for .sops.yaml upward from the working directory, so a config
placed inside platform/sops/ is never found when commands are run from the
repository root. And path_regex is evaluated against an absolute path, which
uses backslashes on Windows.
"""
from pathlib import Path
import re
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class SopsConfigTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / '.sops.yaml'
        self.assertTrue(self.path.exists(),
                        '.sops.yaml must sit at the repository root; sops does not '
                        'look inside platform/sops/ when run from the root')
        self.config = yaml.safe_load(self.path.read_text(encoding='utf-8'))

    def test_creation_rule_matches_both_path_separators(self):
        patterns = [rule['path_regex'] for rule in self.config['creation_rules']]
        posix = 'platform/sops/proxmox-root.sops.yaml'
        windows = r'C:\repo\platform\sops\proxmox-root.sops.yaml'
        self.assertTrue(any(re.search(p, posix) for p in patterns), posix)
        self.assertTrue(any(re.search(p, windows) for p in patterns), windows)

    def test_the_config_file_itself_is_not_matched(self):
        # Otherwise sops would try to encrypt its own configuration.
        patterns = [rule['path_regex'] for rule in self.config['creation_rules']]
        for candidate in ('.sops.yaml', 'platform/sops/.sops.yaml.example'):
            self.assertFalse(any(re.search(p, candidate) for p in patterns), candidate)

    def test_a_real_age_recipient_is_configured(self):
        for rule in self.config['creation_rules']:
            recipient = rule['age']
            self.assertTrue(recipient.startswith('age1'), recipient)
            self.assertNotIn('REPLACE', recipient)
            self.assertGreater(len(recipient), 50, 'age public keys are 62 characters')

    def test_the_example_stays_in_sync_with_the_real_pattern(self):
        example = yaml.safe_load((ROOT / '.sops.yaml.example').read_text(encoding='utf-8'))
        self.assertEqual([rule['path_regex'] for rule in example['creation_rules']],
                         [rule['path_regex'] for rule in self.config['creation_rules']])


if __name__ == '__main__':
    unittest.main()
