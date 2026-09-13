import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'stacks/identity'
SPEC = importlib.util.spec_from_file_location('identity_configure', SOURCE / 'configure.py')
configure = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(configure)

INVITE_SPEC = importlib.util.spec_from_file_location('identity_invitations', SOURCE / 'invitations.py')
invitations = importlib.util.module_from_spec(INVITE_SPEC)
INVITE_SPEC.loader.exec_module(invitations)

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


class FakeIdentityAPI:
    """Enough of the Authentik API for the invitation tool."""

    def __init__(self, users=(), pending=(), groups=('users',)):
        self.users = list(users)
        self.pending = list(pending)
        self.groups = [{'name': name, 'pk': 'group-' + name} for name in groups]
        self.flows = [{'slug': invitations.SLUG, 'pk': 'flow'}]
        self.calls = []

    def rows(self, path):
        if path.startswith('core/groups/'):
            return self.groups
        if path.startswith('core/users/'):
            return self.users
        if path.startswith('stages/invitation/invitations/'):
            return self.pending
        if path.startswith('flows/instances/'):
            return self.flows
        return []

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == 'POST' and path == 'stages/invitation/invitations/':
            return {'name': body['name'], 'pk': 'itok-1', 'used_by': [], 'fixed_data': body['fixed_data']}
        return {'pk': 'obj'}

    def ensure(self, path, identifiers, values):
        return {'pk': identifiers.get('name') or identifiers.get('slug') or 'obj',
                'slug': identifiers.get('slug', 'obj')}


class InvitationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.original_root = invitations.ROOT
        invitations.ROOT = Path(self.directory.name)
        self.addCleanup(lambda: setattr(invitations, 'ROOT', self.original_root))

    def created(self, api):
        return next(body for method, path, body in api.calls
                    if method == 'POST' and path == 'stages/invitation/invitations/')

    def test_an_invitation_fixes_the_identity_and_is_unverified_by_default(self):
        api = FakeIdentityAPI()
        path = invitations.invite(api, 'alice', 'alice@example.org', name='Alice')
        created = self.created(api)
        # The username and email come from the invitation, not the invitee.
        self.assertEqual(created['fixed_data']['username'], 'alice')
        self.assertEqual(created['fixed_data']['email'], 'alice@example.org')
        self.assertFalse(created['fixed_data']['attributes']['email_verified'])
        self.assertTrue(created['single_use'])
        # The link is saved to a 0600 file, not printed.
        saved = path.read_text()
        self.assertIn('/if/flow/' + invitations.SLUG + '/?itoken=itok-1', saved)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_email_verified_only_with_explicit_confirmation(self):
        api = FakeIdentityAPI()
        invitations.invite(api, 'bob', 'bob@example.org', email_owner_confirmed=True)
        self.assertTrue(self.created(api)['fixed_data']['attributes']['email_verified'])

    def test_a_bad_username_or_email_is_refused(self):
        api = FakeIdentityAPI()
        for username, email in [('has space', 'a@b.org'), ('ok', 'not-an-email')]:
            with self.assertRaises(ValueError):
                invitations.invite(api, username, email)

    def test_an_existing_account_is_refused(self):
        api = FakeIdentityAPI(users=[{'username': 'alice', 'email': 'alice@example.org'}])
        with self.assertRaises(ValueError):
            invitations.invite(api, 'alice', 'other@example.org')

    def test_an_unused_invitation_for_the_same_person_is_refused(self):
        api = FakeIdentityAPI(pending=[{'pk': 'x', 'used_by': [],
                                            'fixed_data': {'username': 'alice', 'email': 'alice@example.org'}}])
        with self.assertRaises(ValueError):
            invitations.invite(api, 'alice', 'other@example.org')

    def test_configure_needs_the_target_group_to_exist(self):
        api = FakeIdentityAPI(groups=('admins',))
        with self.assertRaises(SystemExit):
            invitations.configure(api, 'users')

    def test_revoke_deletes_the_invitation_and_its_saved_link(self):
        api = FakeIdentityAPI(pending=[{'pk': 'itok-1', 'name': 'cloud-abc', 'used_by': [],
                                            'fixed_data': {}}])
        directory = Path(self.directory.name) / 'runtime' / 'invitations'
        directory.mkdir(parents=True)
        (directory / 'cloud-abc.json').write_text('{}')
        invitations.revoke(api, 'cloud-abc')
        self.assertTrue(any(method == 'DELETE' for method, _, _ in api.calls))
        self.assertFalse((directory / 'cloud-abc.json').exists())


class FakeSMTP:
    """Records the SMTP conversation instead of opening a socket."""

    instances = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port = host, port
        self.calls = []
        FakeSMTP.instances.append(self)

    def ehlo(self):
        self.calls.append('ehlo')

    def starttls(self, context=None):
        self.calls.append('starttls')

    def login(self, username, password):
        self.calls.append(('login', username))

    def send_message(self, message):
        self.calls.append(('send', message))

    def quit(self):
        self.calls.append('quit')


class MailTests(unittest.TestCase):
    def test_no_smtp_host_means_no_email(self):
        self.assertIsNone(invitations.smtp_settings({}, None))

    def test_settings_pick_starttls_or_ssl_from_the_port(self):
        starttls = invitations.smtp_settings(
            {'SMTP_HOST': 'smtp.example.org', 'SMTP_FROM': 'cloud@example.org'}, None)
        self.assertEqual((starttls['port'], starttls['security']), (587, 'starttls'))
        implicit = invitations.smtp_settings(
            {'SMTP_HOST': 'smtp.example.org', 'SMTP_FROM': 'cloud@example.org', 'SMTP_PORT': '465'}, None)
        self.assertEqual(implicit['security'], 'ssl')

    def test_a_host_without_a_sender_is_refused(self):
        with self.assertRaises(SystemExit):
            invitations.smtp_settings({'SMTP_HOST': 'smtp.example.org'}, None)

    def test_the_message_carries_the_link(self):
        settings = invitations.smtp_settings(
            {'SMTP_HOST': 'smtp.example.org', 'SMTP_FROM': 'cloud@example.org'}, None)
        message = invitations.build_message(settings, 'alice', 'alice@example.org',
                                            'https://auth.example.org/if/flow/x/?itoken=t', '2026-09-12T00:00:00Z')
        self.assertEqual(message['To'], 'alice <alice@example.org>')
        self.assertIn('cloud@example.org', message['From'])
        self.assertIn('https://auth.example.org/if/flow/x/?itoken=t', message.get_content())

    def test_deliver_starts_tls_logs_in_and_sends(self):
        settings = invitations.smtp_settings(
            {'SMTP_HOST': 'smtp.example.org', 'SMTP_FROM': 'cloud@example.org',
             'SMTP_USERNAME': 'user', 'SMTP_PASSWORD': 'secret'}, None)
        message = invitations.build_message(settings, 'alice', 'alice@example.org', 'https://x/y', 'soon')
        original = invitations.smtplib.SMTP
        invitations.smtplib.SMTP = FakeSMTP
        self.addCleanup(lambda: setattr(invitations.smtplib, 'SMTP', original))

        invitations.deliver(settings, message)
        calls = FakeSMTP.instances[-1].calls
        self.assertIn('starttls', calls)
        self.assertIn(('login', 'user'), calls)
        self.assertTrue(any(isinstance(call, tuple) and call[0] == 'send' for call in calls))


class FakeScopeAPI:
    def __init__(self, existing=()):
        self.existing = list(existing)
        self.calls = []

    def rows(self, path):
        return list(self.existing)

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == 'POST':
            return dict(body, pk='new')
        return dict(body, pk='old')


class ScopeMappingTests(unittest.TestCase):
    """Vaultwarden and Kavita need email_verified=True from the provider."""

    def test_a_missing_verified_email_mapping_is_created(self):
        api = FakeScopeAPI()
        mapping = configure.ensure_scope_mapping(
            api, configure.VERIFIED_EMAIL_MAPPING, 'email',
            configure.VERIFIED_EMAIL_EXPRESSION)
        self.assertEqual(mapping['pk'], 'new')
        self.assertEqual(api.calls[0][0], 'POST')
        self.assertIn('"email_verified": True', api.calls[0][2]['expression'])

    def test_a_drifted_mapping_is_corrected(self):
        api = FakeScopeAPI([{'pk': 'old', 'name': configure.VERIFIED_EMAIL_MAPPING,
                             'scope_name': 'email', 'expression': 'return {}'}])
        configure.ensure_scope_mapping(api, configure.VERIFIED_EMAIL_MAPPING, 'email',
                                       configure.VERIFIED_EMAIL_EXPRESSION)
        method, path, _ = api.calls[0]
        self.assertEqual(method, 'PATCH')
        self.assertIn('/old/', path)

    def test_a_matching_mapping_is_left_alone(self):
        api = FakeScopeAPI([{'pk': 'same', 'name': configure.VERIFIED_EMAIL_MAPPING,
                             'scope_name': 'email',
                             'expression': configure.VERIFIED_EMAIL_EXPRESSION}])
        configure.ensure_scope_mapping(api, configure.VERIFIED_EMAIL_MAPPING, 'email',
                                       configure.VERIFIED_EMAIL_EXPRESSION)
        self.assertEqual(api.calls, [])

    def test_the_provider_mappings_prefer_the_verified_email(self):
        text = (SOURCE / 'configure.py').read_text(encoding='utf-8')
        self.assertIn("'openid', 'profile', 'offline_access'", text)
        self.assertIn("mappings.append(verified_email['pk'])", text)


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
