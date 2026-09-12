#!/usr/bin/env python3
"""Reconcile the Authentik objects the cloud portal needs. Standard library only.

Runs on the identity VM against http://localhost:9000 with the bootstrap token.
Idempotent: prints CHANGED for every object it creates or corrects, OK otherwise.
"""
import json
import os
from pathlib import Path
import secrets
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
BASE = os.environ.get('AUTHENTIK_URL', 'http://localhost:9000') + '/api/v3/'
GROUPS = ('users', 'admins')
CLIENT = 'cloud'
AUTHORIZATION_FLOW = 'default-provider-authorization-implicit-consent'
INVALIDATION_FLOW = 'default-provider-invalidation-flow'
SIGNING_KEY = 'authentik Self-signed Certificate'
# Email OTP is a second factor that survives a lost passkey: the login flow's
# authenticator validation stage accepts the `email` device class, so a passkey
# holder who loses the key can still prove themselves with a code sent to them.
EMAIL_SETUP_FLOW = 'default-authenticator-email-setup'
RECOVERY_FLOW = 'default-recovery-flow'
# 12 characters matches the invitation flow and the portal's own policy.
MIN_PASSWORD = 12
PASSWORD_POLICY = '''data = request.context.get("prompt_data", {})
if len(data.get("password", "")) < 12:
    ak_message("パスワードは12文字以上にしてください。")
    return False
return True'''


def redirect_uri(portal_url):
    """Return the single strict redirect URI for the portal, refusing guesses."""
    if not portal_url.startswith(('http://', 'https://')):
        raise ValueError('CLOUD_PORTAL_URL must be an absolute http(s) URL')
    return portal_url.rstrip('/') + '/auth/callback'


def provider_body(flows, mappings, signing_key, credential, portal_url):
    """Build the OAuth2 provider the cloud portal logs in through.

    sub_mode is user_uuid, not hashed_user_id: the hashed form is derived per
    provider, so recreating this provider would give every account a new sub
    and orphan all of their resources in the cloud API's database.
    """
    return {
        'name': CLIENT,
        'authorization_flow': flows[AUTHORIZATION_FLOW],
        'invalidation_flow': flows[INVALIDATION_FLOW],
        'client_type': 'confidential',
        'client_id': credential['client_id'],
        'client_secret': credential['client_secret'],
        'grant_types': ['authorization_code', 'refresh_token'],
        # redirect_uri_type is echoed back by the API; omitting it reports drift forever.
        'redirect_uris': [{'matching_mode': 'strict', 'url': redirect_uri(portal_url),
                           'redirect_uri_type': 'authorization'}],
        'property_mappings': sorted(mappings),
        'signing_key': signing_key,
        'sub_mode': 'user_uuid',
        'include_claims_in_id_token': True,
    }


def drifted(current, desired):
    """Return the desired keys whose current value differs."""
    def normal(value):
        return sorted(value, key=json.dumps) if isinstance(value, list) else value
    return sorted(key for key, value in desired.items()
                  if key != 'client_secret' and normal(current.get(key)) != normal(value))


class API:
    def __init__(self, token):
        self.token = token

    def call(self, method, path, body=None):
        request = urllib.request.Request(
            BASE + path, method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                content = response.read()
        except urllib.error.HTTPError as error:
            # Field names only: bodies can echo secrets back.
            try:
                fields = list(json.loads(error.read()))
            except ValueError:
                fields = []
            raise RuntimeError(f'{method} {path.split("?")[0]}: HTTP {error.code}; fields: {fields}') from None
        return json.loads(content) if content else None

    def rows(self, path):
        separator = '&' if '?' in path else '?'
        return self.call('GET', f'{path}{separator}page_size=1000')['results']

    def ensure(self, path, identifiers, values):
        """Create the object, or correct it in place, and return it."""
        matches = [row for row in self.rows(path)
                   if all(row.get(key) == value for key, value in identifiers.items())]
        if len(matches) > 1:
            raise RuntimeError(f'ambiguous {path}: {identifiers}')
        payload = {**identifiers, **values}
        if matches:
            key = matches[0]['slug'] if path == 'flows/instances/' else matches[0]['pk']
            return self.call('PATCH', path + str(key) + '/', payload)
        return self.call('POST', path, payload)


def wait_until_ready(api, attempts=60):
    """The worker applies the default blueprints after the API already answers."""
    for _ in range(attempts):
        try:
            slugs = {row['slug'] for row in api.rows('flows/instances/')}
            if {AUTHORIZATION_FLOW, INVALIDATION_FLOW} <= slugs:
                return
        except (OSError, RuntimeError):
            pass
        time.sleep(5)
    raise SystemExit('Authentik did not finish applying its default blueprints')


def credential():
    path = ROOT / 'secrets' / 'oidc-cloud.json'
    if not path.exists():
        with path.open('x') as file:
            json.dump({'client_id': CLIENT, 'client_secret': secrets.token_urlsafe(48)}, file)
        path.chmod(0o600)
    return json.loads(path.read_text())


def configure_email_authenticator(api):
    """Offer Email OTP as an enrolable factor, so a lost passkey is not a lockout.

    The authentication flow already accepts the `email` device class; this adds
    the setup flow Authentik needs for people to enrol it. The code is sent with
    the SMTP settings from `.env`, the same ones invitations use.
    """
    created = not api.rows(f'flows/instances/?slug={EMAIL_SETUP_FLOW}')
    flow = api.ensure('flows/instances/', {'slug': EMAIL_SETUP_FLOW}, {
        'name': 'Email MFA setup', 'title': 'メール確認コードを設定',
        'designation': 'stage_configuration', 'authentication': 'require_authenticated'})
    stage = api.ensure('stages/authenticator/email/', {'name': EMAIL_SETUP_FLOW}, {
        'configure_flow': flow['pk'], 'friendly_name': 'メール',
        'use_global_settings': True, 'subject': 'shake-cloud の確認コード',
        'token_expiry': 'minutes=5'})
    api.ensure('flows/bindings/', {'target': flow['pk'], 'order': 10}, {
        'stage': stage['pk'], 'evaluate_on_plan': False, 're_evaluate_policies': True})
    print(('CHANGED: ' if created else 'OK: ') + f'Email authenticator setup ({EMAIL_SETUP_FLOW})')


def configure_recovery(api):
    """Self-service password reset by email, linked from the login page.

    This recovers the password only. A person who has an MFA factor enrolled
    still passes the authentication flow's validation stage; that is why the
    Email authenticator above matters for passkey holders.
    """
    created = not api.rows(f'flows/instances/?slug={RECOVERY_FLOW}')
    flow = api.ensure('flows/instances/', {'slug': RECOVERY_FLOW}, {
        'name': 'Password recovery', 'title': 'パスワードの再設定',
        'designation': 'recovery', 'authentication': 'require_unauthenticated'})
    identification = api.ensure('stages/identification/', {'name': RECOVERY_FLOW + '-identification'}, {
        'user_fields': ['email', 'username'], 'case_insensitive_matching': True,
        'show_matched_user': False, 'pretend_user_exists': False})
    email = api.ensure('stages/email/', {'name': RECOVERY_FLOW + '-email'}, {
        'use_global_settings': True, 'template': 'email/password_reset.html',
        'subject': 'shake-cloud のパスワード再設定', 'token_expiry': 'minutes=30'})
    fields = [api.ensure('stages/prompt/prompts/', {'name': RECOVERY_FLOW + '-' + key}, {
        'field_key': key, 'label': label, 'type': 'password', 'required': True, 'order': order})['pk']
        for order, (key, label) in enumerate([('password', '新しいパスワード（12文字以上）'),
                                              ('password_repeat', '新しいパスワード（確認）')])]
    policy = api.ensure('policies/expression/', {'name': RECOVERY_FLOW + '-validate'}, {
        'expression': PASSWORD_POLICY, 'execution_logging': False})
    prompt = api.ensure('stages/prompt/stages/', {'name': RECOVERY_FLOW + '-prompt'}, {
        'fields': fields, 'validation_policies': [policy['pk']]})
    write = api.ensure('stages/user_write/', {'name': RECOVERY_FLOW + '-write'}, {
        'user_creation_mode': 'never_create', 'user_type': 'internal',
        'create_users_as_inactive': False, 'user_path_template': 'users'})
    login = api.ensure('stages/user_login/', {'name': RECOVERY_FLOW + '-login'}, {})
    for order, stage in [(10, identification), (20, email), (30, prompt), (40, write), (50, login)]:
        api.ensure('flows/bindings/', {'target': flow['pk'], 'order': order}, {
            'stage': stage['pk'], 'evaluate_on_plan': False, 're_evaluate_policies': True})
    # The login page only offers recovery when the brand names the flow.
    for brand in api.rows('core/brands/'):
        if not brand.get('default') or brand.get('flow_recovery') == flow['pk']:
            continue
        key = brand.get('brand_uuid') or brand.get('pk')
        api.call('PATCH', f'core/brands/{key}/', {'flow_recovery': flow['pk']})
        print('CHANGED: brand points at the recovery flow')
    print(('CHANGED: ' if created else 'OK: ') + f'password recovery flow ({RECOVERY_FLOW})')


def main():
    api = API(os.environ['AUTHENTIK_TOKEN'])
    wait_until_ready(api)

    groups = {}
    for name in GROUPS:
        found = api.rows(f'core/groups/?name={name}')
        if found:
            groups[name] = found[0]
            print(f'OK: group {name}')
        else:
            groups[name] = api.call('POST', 'core/groups/', {'name': name})
            print(f'CHANGED: created group {name}')

    admin = api.rows('core/users/?username=akadmin')[0]
    if groups['admins']['pk'] not in admin['groups']:
        api.call('PATCH', f"core/users/{admin['pk']}/",
                 {'groups': admin['groups'] + [groups['admins']['pk']]})
        print('CHANGED: akadmin joined admins')

    flows = {row['slug']: row['pk'] for row in api.rows('flows/instances/')}
    # profile carries the groups claim the API uses to recognise admins.
    mappings = [row['pk'] for row in api.rows('propertymappings/provider/scope/')
                if row.get('managed', '') and row['scope_name'] in ('openid', 'email', 'profile')]
    keys = [row['pk'] for row in api.rows('crypto/certificatekeypairs/') if row['name'] == SIGNING_KEY]
    if not keys:
        raise SystemExit(f'Signing key not found: {SIGNING_KEY}')
    desired = provider_body(flows, mappings, keys[0], credential(), os.environ['CLOUD_PORTAL_URL'])

    existing = [row for row in api.rows('providers/oauth2/') if row['name'] == CLIENT]
    if not existing:
        provider = api.call('POST', 'providers/oauth2/', desired)
        print(f'CHANGED: created OIDC provider {CLIENT}')
    else:
        provider = existing[0]
        changes = drifted(provider, desired)
        if changes:
            provider = api.call('PATCH', f"providers/oauth2/{provider['pk']}/", desired)
            print(f'CHANGED: corrected OIDC provider {CLIENT}: {changes}')
        else:
            print(f'OK: OIDC provider {CLIENT}')

    applications = [row for row in api.rows('core/applications/') if row['slug'] == CLIENT]
    app_body = {'name': 'shake-cloud', 'slug': CLIENT, 'provider': provider['pk'],
                'meta_launch_url': os.environ['CLOUD_PORTAL_URL'],
                'policy_engine_mode': 'any'}
    if not applications:
        application = api.call('POST', 'core/applications/', app_body)
        print(f'CHANGED: created application {CLIENT}')
    elif drifted(applications[0], app_body):
        application = api.call('PATCH', f'core/applications/{CLIENT}/', app_body)
        print(f'CHANGED: corrected application {CLIENT}')
    else:
        application = applications[0]
        print(f'OK: application {CLIENT}')

    # Only members of these groups may log in; an application with no binding
    # would admit every Authentik user, including people invited for media only.
    bindings = api.rows(f"policies/bindings/?target={application['pk']}")
    for order, name in enumerate(GROUPS):
        if any(row.get('group') == groups[name]['pk'] for row in bindings):
            print(f'OK: {name} may use {CLIENT}')
        else:
            api.call('POST', 'policies/bindings/', {'target': application['pk'],
                                                    'group': groups[name]['pk'], 'order': order})
            print(f'CHANGED: {name} may use {CLIENT}')

    # Recovery needs an address on the administrator account; SMTP_FROM is the
    # mailbox we know reaches a human when the passkey is gone.
    admin_email = os.environ.get('CLOUD_ADMIN_EMAIL', '').strip()
    if admin_email and admin.get('email') != admin_email:
        api.call('PATCH', f"core/users/{admin['pk']}/", {'email': admin_email})
        print(f'CHANGED: akadmin email set to {admin_email}')
    elif admin_email:
        print('OK: akadmin email')

    configure_email_authenticator(api)
    configure_recovery(api)


if __name__ == '__main__':
    main()
