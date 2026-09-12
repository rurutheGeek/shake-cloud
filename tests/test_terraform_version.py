"""Keep one Terraform CLI version on CI and on the developer VMs.

A saved plan can only be applied by the CLI version that wrote it, so a drift
between CI and an operator's machine turns "plan then apply" into a version
error. `.terraform-version` is the single source: CI reads it and the devbox
role installs the same release.
"""
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class TerraformVersionTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / '.terraform-version'
        self.assertTrue(self.path.exists(), '.terraform-version must pin the CLI version')
        self.version = self.path.read_text(encoding='utf-8').strip()

    def test_the_pin_is_an_exact_release(self):
        self.assertRegex(self.version, r'^\d+\.\d+\.\d+$', self.version)

    def test_ci_reads_the_pin_instead_of_repeating_it(self):
        workflow_path = ROOT / '.github' / 'workflows' / 'validate.yml'
        text = workflow_path.read_text(encoding='utf-8')
        self.assertIn('.terraform-version', text,
                      'CI must read the pin so the two cannot drift')
        workflow = yaml.safe_load(text)
        steps = workflow['jobs']['validate']['steps']
        setup = [step for step in steps
                 if str(step.get('uses', '')).startswith('hashicorp/setup-terraform')]
        self.assertEqual(len(setup), 1, 'expected exactly one setup-terraform step')
        value = str(setup[0]['with']['terraform_version'])
        # An expression that reads the file, not a hardcoded release.
        self.assertNotRegex(value, r'^\d', f'CI repeats the version literally: {value}')

    def test_devbox_installs_the_pin(self):
        defaults_path = ROOT / 'platform' / 'ansible' / 'roles' / 'devbox' / 'defaults' / 'main.yml'
        defaults = yaml.safe_load(defaults_path.read_text(encoding='utf-8'))
        self.assertEqual(str(defaults['devbox_terraform_version']), self.version,
                         'the devbox role must install the pinned version')


if __name__ == '__main__':
    unittest.main()
