"""Guard the credential boundary that `tools/tf` draws for service modules.

I05 gives each service its own S3 state and says a service run must not see the
credentials that build the foundation (Proxmox, NetBox, Cloudflare). A shell
script cannot be type-checked, so the real script is run inside a fake repo
with a fake `sops` and a fake `terraform` that records the environment it was
given. Nothing here reaches the network, real SOPS keys, or a state bucket.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TF = ROOT / 'tools/tf'

FAKE_TERRAFORM = '''#!/usr/bin/env python3
import json, os, sys
out = os.environ.get("FAKE_TF_OUT")
if out:
    with open(out, "w") as fh:
        json.dump({"args": sys.argv[1:], "env": dict(os.environ)}, fh)
'''

FAKE_SOPS = '''#!/usr/bin/env python3
import json, os, sys
values = json.loads(os.environ["FAKE_SOPS_VALUES"])
args = sys.argv[1:]
key = json.loads(args[args.index("--extract") + 1])[0]
name = os.path.basename(args[-1])
if name not in values or key not in values[name]:
    sys.exit(1)
print(values[name][key])
'''

S3 = {
    'AWS_ACCESS_KEY_ID': 'state-id',
    'AWS_SECRET_ACCESS_KEY': 'state-secret',
    'AWS_ENDPOINT_URL_S3': 'https://state.example',
    'AWS_REGION': 'auto',
    'TF_STATE_BUCKET': 'state-bucket',
}

# Credentials that belong to the foundation, never to a service run.
FOUNDATION = (
    'PROXMOX_VE_ENDPOINT',
    'PROXMOX_VE_API_TOKEN',
    'PROXMOX_VE_USERNAME',
    'PROXMOX_VE_PASSWORD',
    'PROXMOX_VE_INSECURE',
    'NETBOX_SERVER_URL',
    'NETBOX_API_TOKEN',
    'CLOUDFLARE_API_TOKEN',
    'TF_VAR_cloudflare_dns_api_token',
)

PROXMOX = {
    'PROXMOX_VE_ENDPOINT': 'https://pve.example',
    'PROXMOX_VE_INSECURE': 'true',
    'PROXMOX_VE_API_TOKEN': 'pve-token',
}

SERVICES = {
    'SHAKECLOUD_ACCESS_KEY': 'sca_service',
    'SHAKECLOUD_ENDPOINT': 'https://cloud.example',
}


class TfHarness:
    """Run tools/tf with fake sops/terraform and return what terraform saw."""

    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix='tf-test-'))
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        (self.temp / 'tools').mkdir()
        shutil.copy(TF, self.temp / 'tools/tf')
        (self.temp / 'tools/tf').chmod(0o755)
        self.bin = self.temp / 'bin'
        self.bin.mkdir()
        self.write_exe(self.bin / 'terraform', FAKE_TERRAFORM)
        self.write_exe(self.bin / 'sops', FAKE_SOPS)
        self.sops_values = {}

    def write_exe(self, path, body):
        path.write_text(body, encoding='utf-8')
        path.chmod(0o755)

    def module(self, name, files):
        directory = self.temp / 'platform/terraform' / name
        directory.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            (directory / filename).write_text(content, encoding='utf-8')

    def sops(self, values):
        (self.temp / 'platform/sops').mkdir(parents=True, exist_ok=True)
        for name in values:
            (self.temp / 'platform/sops' / name).write_text('encrypted', encoding='utf-8')
        self.sops_values = values

    def run_tf(self, module, *args, env=None):
        out = self.temp / 'terraform-env.json'
        environment = os.environ.copy()
        # The host's own shell must not decide the outcome of a test.
        for name in (*FOUNDATION, *S3, 'SHAKECLOUD_ACCESS_KEY', 'SHAKECLOUD_ENDPOINT'):
            environment.pop(name, None)
        environment.update({
            'PATH': f'{self.bin}:{environment["PATH"]}',
            'SOPS': str(self.bin / 'sops'),
            'FAKE_TF_OUT': str(out),
            'FAKE_SOPS_VALUES': json.dumps(self.sops_values),
        })
        if env:
            environment.update(env)
        result = subprocess.run(
            [str(self.temp / 'tools/tf'), module, *args],
            capture_output=True, text=True, env=environment, cwd=self.temp,
        )
        seen = json.loads(out.read_text(encoding='utf-8')) if out.exists() else None
        return result, seen


class ServiceCredentialTests(TfHarness, unittest.TestCase):
    """I05: only the state backend and the service's own key reach a service."""

    def setUp(self):
        super().setUp()
        self.module('services/media', {'main.tf': 'provider "shakecloud" {}\n'})

    def test_a_service_gets_state_and_cloud_credentials_only(self):
        self.sops({'s3.sops.yaml': S3, 'services.sops.yaml': SERVICES})
        result, seen = self.run_tf('services/media', 'plan')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(seen['args'],
                         ['-chdir=platform/terraform/services/media', 'plan'])
        env = seen['env']
        for name, value in S3.items():
            if name != 'TF_STATE_BUCKET':  # the bucket goes to -backend-config
                self.assertEqual(env[name], value, name)
        self.assertEqual(env['SHAKECLOUD_ACCESS_KEY'], 'sca_service')
        self.assertEqual(env['SHAKECLOUD_ENDPOINT'], 'https://cloud.example')
        for name in FOUNDATION:
            self.assertNotIn(name, env, name)

    def test_the_environment_supplies_the_key_until_sops_has_it(self):
        self.sops({'s3.sops.yaml': S3})
        result, seen = self.run_tf('services/media', 'plan',
                                   env={'SHAKECLOUD_ACCESS_KEY': 'sca_env'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(seen['env']['SHAKECLOUD_ACCESS_KEY'], 'sca_env')

    def test_sops_wins_over_an_inherited_environment_key(self):
        self.sops({'s3.sops.yaml': S3, 'services.sops.yaml': SERVICES})
        result, seen = self.run_tf('services/media', 'plan',
                                   env={'SHAKECLOUD_ACCESS_KEY': 'sca_stale'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(seen['env']['SHAKECLOUD_ACCESS_KEY'], 'sca_service')

    def test_foundation_credentials_are_stripped_from_an_inherited_environment(self):
        self.sops({'s3.sops.yaml': S3, 'services.sops.yaml': SERVICES})
        env = {name: f'leaked-{name}' for name in FOUNDATION}
        result, seen = self.run_tf('services/media', 'plan', env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in FOUNDATION:
            self.assertNotIn(name, seen['env'], name)

    def test_a_declared_cloudflare_provider_gets_the_dns_token(self):
        self.module('services/media', {'versions.tf': 'provider "cloudflare" {}\n'})
        self.sops({
            's3.sops.yaml': S3,
            'services.sops.yaml': SERVICES,
            'cloudflare-dns.sops.yaml': {'CLOUDFLARE_DNS_API_TOKEN': 'dns-token'},
        })
        result, seen = self.run_tf('services/media', 'plan')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(seen['env']['CLOUDFLARE_API_TOKEN'], 'dns-token')

    def test_a_module_without_cloudflare_gets_no_dns_token(self):
        self.sops({'s3.sops.yaml': S3, 'services.sops.yaml': SERVICES})
        result, seen = self.run_tf('services/media', 'plan')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('CLOUDFLARE_API_TOKEN', seen['env'])

    def test_a_plan_without_a_key_stops_before_terraform_runs(self):
        self.sops({'s3.sops.yaml': S3})
        result, seen = self.run_tf('services/media', 'plan')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SHAKECLOUD_ACCESS_KEY', result.stderr)
        self.assertIsNone(seen, 'terraform must not run without a service key')

    def test_an_apply_without_a_key_stops_before_terraform_runs(self):
        self.sops({'s3.sops.yaml': S3})
        result, seen = self.run_tf('services/media', 'apply')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SHAKECLOUD_ACCESS_KEY', result.stderr)
        self.assertIsNone(seen)

    def test_init_without_a_key_still_runs_and_gets_the_state_bucket(self):
        self.sops({'s3.sops.yaml': S3})
        result, seen = self.run_tf('services/media', 'init')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('SHAKECLOUD_ACCESS_KEY', result.stderr)
        self.assertEqual(seen['args'],
                         ['-chdir=platform/terraform/services/media', 'init',
                          '-backend-config=bucket=state-bucket'])

    def test_validate_without_a_key_still_runs(self):
        self.sops({'s3.sops.yaml': S3})
        result, seen = self.run_tf('services/media', 'validate')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNotNone(seen)


class ExistingModuleTests(TfHarness, unittest.TestCase):
    """The new branch must not change what the other modules receive."""

    def test_10_platform_still_gets_proxmox_and_netbox(self):
        self.module('10-platform', {'main.tf': 'provider "proxmox" {}\n'})
        self.sops({
            's3.sops.yaml': S3,
            'proxmox.sops.yaml': PROXMOX,
            'netbox.sops.yaml': {
                'NETBOX_SERVER_URL': 'http://netbox.example',
                'NETBOX_API_TOKEN': 'netbox-token',
            },
        })
        result, seen = self.run_tf('10-platform', 'plan')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(seen['args'], ['-chdir=platform/terraform/10-platform', 'plan'])
        self.assertEqual(seen['env']['PROXMOX_VE_API_TOKEN'], 'pve-token')
        self.assertEqual(seen['env']['NETBOX_API_TOKEN'], 'netbox-token')
        self.assertNotIn('SHAKECLOUD_ACCESS_KEY', seen['env'])

    def test_05_seed_still_gets_proxmox_and_not_netbox(self):
        self.module('05-seed', {'main.tf': 'provider "proxmox" {}\n'})
        self.sops({'s3.sops.yaml': S3, 'proxmox.sops.yaml': PROXMOX})
        result, seen = self.run_tf('05-seed', 'plan')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(seen['env']['PROXMOX_VE_API_TOKEN'], 'pve-token')
        self.assertNotIn('NETBOX_API_TOKEN', seen['env'])
        self.assertNotIn('SHAKECLOUD_ACCESS_KEY', seen['env'])

    def test_20_dns_still_gets_the_dns_token_and_the_state_bucket(self):
        self.module('20-dns', {'main.tf': 'provider "cloudflare" {}\n'})
        self.sops({
            's3.sops.yaml': S3,
            'cloudflare-dns.sops.yaml': {'CLOUDFLARE_DNS_API_TOKEN': 'dns-token'},
        })
        result, seen = self.run_tf('20-dns', 'plan')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(seen['env']['CLOUDFLARE_API_TOKEN'], 'dns-token')
        self.assertEqual(seen['env']['TF_VAR_state_bucket'], 'state-bucket')
        self.assertNotIn('PROXMOX_VE_API_TOKEN', seen['env'])

    def test_00_bootstrap_still_gets_the_root_credentials(self):
        self.module('00-bootstrap', {'main.tf': 'provider "proxmox" {}\n'})
        self.sops({
            's3.sops.yaml': S3,
            'proxmox-root.sops.yaml': {
                **PROXMOX,
                'PROXMOX_VE_USERNAME': 'root@pam',
                'PROXMOX_VE_PASSWORD': 'root-password',
            },
            'cloudflare-dns.sops.yaml': {'CLOUDFLARE_DNS_API_TOKEN': 'dns-token'},
        })
        result, seen = self.run_tf('00-bootstrap', 'plan')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(seen['env']['PROXMOX_VE_USERNAME'], 'root@pam')
        self.assertEqual(seen['env']['PROXMOX_VE_PASSWORD'], 'root-password')
        self.assertEqual(seen['env']['TF_VAR_cloudflare_dns_api_token'], 'dns-token')
        self.assertNotIn('PROXMOX_VE_API_TOKEN', seen['env'])

    def test_state_store_still_gets_only_its_own_cloudflare_token(self):
        self.module('state-store', {'main.tf': 'provider "cloudflare" {}\n'})
        self.sops({'cloudflare.sops.yaml': {'CLOUDFLARE_API_TOKEN': 'r2-token'}})
        result, seen = self.run_tf('state-store', 'apply')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(seen['args'], ['-chdir=platform/terraform/state-store', 'apply'])
        self.assertEqual(seen['env']['CLOUDFLARE_API_TOKEN'], 'r2-token')
        # state-store creates the bucket, so it never reads the S3 backend.
        self.assertNotIn('AWS_ACCESS_KEY_ID', seen['env'])


class InvocationTests(TfHarness, unittest.TestCase):
    def test_an_unknown_module_is_rejected_before_sops_runs(self):
        result, seen = self.run_tf('services/nope', 'plan')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('そんなモジュールは無い', result.stderr)
        self.assertIsNone(seen)

    def test_the_service_module_is_found_below_services(self):
        self.module('services/media', {'main.tf': ''})
        self.sops({'s3.sops.yaml': S3, 'services.sops.yaml': SERVICES})
        result, seen = self.run_tf('services/media', 'plan')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('-chdir=platform/terraform/services/media', seen['args'])


class SourceTests(unittest.TestCase):
    """The text is the contract; a shell script has no types to lean on."""

    def setUp(self):
        self.text = TF.read_text(encoding='utf-8')
        start = self.text.index('elif [[ "$module" == services/* ]]')
        self.branch = self.text[start:self.text.index('\nelse\n', start)]

    def test_the_services_branch_decrypts_no_foundation_secret_file(self):
        for name in ('proxmox.sops.yaml', 'proxmox-root.sops.yaml', 'netbox.sops.yaml',
                     'cloudflare.sops.yaml', 'k8s.sops.yaml'):
            self.assertNotIn(name, self.branch, name)

    def test_the_services_branch_exports_no_foundation_credentials(self):
        # CLOUDFLARE_ is exported only inside the DNS-provider branch, so it is
        # checked there by the functional test, not by this blanket rule.
        for name in ('PROXMOX_VE', 'NETBOX_'):
            self.assertNotRegex(self.branch, rf'export[^\n]*{name}')

    def test_the_service_key_has_a_sops_home_with_an_environment_fallback(self):
        self.assertIn('services.sops.yaml', self.branch)
        self.assertIn('SHAKECLOUD_ACCESS_KEY', self.branch)
        self.assertIn('unset', self.branch)

    def test_init_only_adds_the_backend_bucket(self):
        self.assertIn('-backend-config="bucket=${TF_STATE_BUCKET}"', self.text)

    def test_the_legacy_modules_keep_their_sops_files(self):
        rest = self.text.replace(self.branch, '')
        for name in ('cloudflare.sops.yaml', 'proxmox.sops.yaml',
                     'proxmox-root.sops.yaml', 'netbox.sops.yaml',
                     'cloudflare-dns.sops.yaml'):
            self.assertIn(name, rest, name)


if __name__ == '__main__':
    unittest.main()
