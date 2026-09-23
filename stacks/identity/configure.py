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
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
BASE = os.environ.get('AUTHENTIK_URL', 'http://localhost:9000') + '/api/v3/'
GROUPS = ('users', 'admins')
CLIENT = 'cloud'
# Media SSO. Nextcloud, Kavita and FreshRSS accept OIDC natively; Navidrome,
# MeTube and KHInsider get Forward Auth through the embedded outpost and keep
# their own authentication on the API paths.
MEDIA_OIDC_CLIENTS = {'nextcloud': '/apps/user_oidc/code', 'kavita': '/signin-oidc',
                      'freshrss': '/i/oidc/'}
MEDIA_PROXY_PROVIDERS = ('navidrome', 'metube', 'khinsider')
MEDIA_APPLICATIONS = {'nextcloud': 'Nextcloud', 'kavita': 'Kavita',
                      'freshrss': 'FreshRSS',
                      'navidrome': 'Navidrome', 'metube': 'MeTube',
                      'khinsider': 'KHInsider'}
MEDIA_OUTPOST = 'Embedded'
# The service entry point lives on services-01, not media-01, but it is an
# OIDC client of the same identity and is reachable by every invited person.
HOMARR = 'homarr'
HOMARR_REDIRECT_PATH = '/api/auth/callback/oidc'
# The monitoring portal. Grafana maps the groups claim to Admin/Viewer itself.
GRAFANA = 'grafana'
GRAFANA_REDIRECT_PATH = '/login/generic_oauth'
# Vaultwarden is a native OIDC client. The callback is generated from its
# DOMAIN (https://vault.<zone>), and offline_access/refresh tokens keep the
# Bitwarden session alive.
VAULTWARDEN = 'vaultwarden'
VAULTWARDEN_HOST = 'vault'
VAULTWARDEN_REDIRECT_PATH = '/identity/connect/oidc-signin'
# Home Assistant has no native OIDC. The community oidc_auth integration is a
# public client (PKCE, no secret) and HA is served at ha.<zone>, not the slug.
HOME_ASSISTANT = 'home-assistant'
HOME_ASSISTANT_HOST = 'ha'
HOME_ASSISTANT_REDIRECT_PATH = '/auth/oidc/callback'
# CUPS runs on services-01. The status page is a browser tool like the media
# proxies, so it goes through Forward Auth too; printing itself stays on the
# plain IPP port (631) and the /admin paths are blocked at the proxy.
CUPS = 'cups'
# AdGuard Home runs on the router. Only its browser UI goes through SSO; the
# router's firewall allows :3000 just from services-01 (where Caddy runs).
ADGUARD = 'adguard'
# Authentik's managed email scope mapping always reports email_verified=False.
# Vaultwarden and Kavita reject an unverified email, so the providers use our
# own mapping for the email scope: invitations already verify the address.
VERIFIED_EMAIL_MAPPING = 'Verified Email'
VERIFIED_EMAIL_EXPRESSION = (
    'return {\n'
    '    "email": request.user.email,\n'
    '    "email_verified": True,\n'
    '}'
)
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


def redirect_uri(base_url, path='/auth/callback'):
    """Return one strict redirect URI, refusing guesses."""
    if not base_url.startswith(('http://', 'https://')):
        raise ValueError('the OIDC base URL must be an absolute http(s) URL')
    return base_url.rstrip('/') + path


def media_zone(portal_url):
    """Return the DNS zone behind the portal name: https://cloud.<zone> -> <zone>."""
    if not portal_url.startswith(('http://', 'https://')):
        raise ValueError('CLOUD_PORTAL_URL must be an absolute http(s) URL')
    host = urllib.parse.urlsplit(portal_url).hostname or ''
    if not host:
        raise ValueError('CLOUD_PORTAL_URL must carry a hostname')
    labels = host.split('.')
    return '.'.join(labels[1:]) if labels[0] == 'cloud' and len(labels) > 1 else host


def media_redirect(name, zone):
    """Return the app-specific OIDC redirect URI for a media client."""
    return f'https://{name}.{zone}{MEDIA_OIDC_CLIENTS[name]}'


def homarr_redirect(zone):
    """Return the Homarr OIDC redirect URI (its NextAuth callback)."""
    return f'https://{HOMARR}.{zone}{HOMARR_REDIRECT_PATH}'


def grafana_redirect(zone):
    """Return the Grafana OIDC redirect URI (generic_oauth)."""
    return f'https://{GRAFANA}.{zone}{GRAFANA_REDIRECT_PATH}'


def vaultwarden_redirect(zone):
    """Return the Vaultwarden OIDC redirect URI (its oidc-signin callback)."""
    return f'https://{VAULTWARDEN_HOST}.{zone}{VAULTWARDEN_REDIRECT_PATH}'


def home_assistant_redirect(zone):
    """Return the OIDC redirect URI used by the Home Assistant auth_oidc integration."""
    return f'https://{HOME_ASSISTANT_HOST}.{zone}{HOME_ASSISTANT_REDIRECT_PATH}'


def oidc_provider_body(name, redirect, flows, mappings, signing_key, credential):
    """Build one confidential OIDC provider.

    sub_mode is user_uuid, not hashed_user_id: the hashed form is derived per
    provider, so recreating this provider would give every account a new sub
    and orphan all of their resources in the cloud API's database.
    """
    return {
        'name': name,
        'authorization_flow': flows[AUTHORIZATION_FLOW],
        'invalidation_flow': flows[INVALIDATION_FLOW],
        'client_type': 'confidential',
        'client_id': credential['client_id'],
        'client_secret': credential['client_secret'],
        'grant_types': ['authorization_code', 'refresh_token'],
        # redirect_uri_type is echoed back by the API; omitting it reports drift forever.
        'redirect_uris': [{'matching_mode': 'strict', 'url': redirect,
                           'redirect_uri_type': 'authorization'}],
        'property_mappings': sorted(mappings),
        'signing_key': signing_key,
        'sub_mode': 'user_uuid',
        'include_claims_in_id_token': True,
    }


def public_oidc_provider_body(name, redirect, flows, mappings, signing_key):
    """Build a public OIDC provider for PKCE clients that hold no secret."""
    return {
        'name': name,
        'authorization_flow': flows[AUTHORIZATION_FLOW],
        'invalidation_flow': flows[INVALIDATION_FLOW],
        'client_type': 'public',
        'client_id': name,
        'grant_types': ['authorization_code'],
        'redirect_uris': [{'matching_mode': 'strict', 'url': redirect,
                           'redirect_uri_type': 'authorization'}],
        'property_mappings': sorted(mappings),
        'signing_key': signing_key,
        'sub_mode': 'user_uuid',
        'include_claims_in_id_token': True,
    }


def provider_body(flows, mappings, signing_key, credential, portal_url,
                  callback='/auth/callback', name=CLIENT):
    """Build the OAuth2 provider one application logs in through."""
    return oidc_provider_body(name, redirect_uri(portal_url, callback), flows,
                              mappings, signing_key, credential)


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


def credential(client=CLIENT):
    """The OIDC client credentials for one application.

    The cloud client is generated here and never leaves the identity VM except
    through the deployment. NetBox keeps its secret in SOPS instead, because
    both the identity and NetBox roles read the same value; `credential` takes
    it from the environment when the deployment provides it.
    """
    external = os.environ.get(f'{client.upper()}_OIDC_CLIENT_SECRET', '').strip()
    if external:
        return {'client_id': client, 'client_secret': external}
    path = ROOT / 'secrets' / f'oidc-{client}.json'
    if not path.exists():
        with path.open('x') as file:
            json.dump({'client_id': client, 'client_secret': secrets.token_urlsafe(48)}, file)
        path.chmod(0o600)
    return json.loads(path.read_text())


def media_credentials():
    """Load or create the media OIDC clients, keeping the values already stored."""
    path = ROOT / 'secrets' / 'oidc-media.json'
    credentials = json.loads(path.read_text()) if path.exists() else {}
    missing = [name for name in MEDIA_OIDC_CLIENTS if name not in credentials]
    if missing:
        for name in missing:
            credentials[name] = {'client_id': name,
                                 'client_secret': secrets.token_urlsafe(48)}
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(json.dumps(credentials))
        path.chmod(0o600)
    return credentials


def homarr_credential():
    """Load or create the Homarr OIDC client, keeping the stored secret."""
    path = ROOT / 'secrets' / 'oidc-homarr.json'
    if path.exists():
        return json.loads(path.read_text())
    credential = {'client_id': HOMARR, 'client_secret': secrets.token_urlsafe(48)}
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(credential))
    path.chmod(0o600)
    return credential


def grafana_credential():
    """Load or create the Grafana OIDC client, keeping the stored secret."""
    path = ROOT / 'secrets' / 'oidc-grafana.json'
    if path.exists():
        return json.loads(path.read_text())
    credential = {'client_id': GRAFANA, 'client_secret': secrets.token_urlsafe(48)}
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(credential))
    path.chmod(0o600)
    return credential


def vaultwarden_credential():
    """Load or create the Vaultwarden OIDC client, keeping the stored secret."""
    path = ROOT / 'secrets' / 'oidc-vaultwarden.json'
    if path.exists():
        return json.loads(path.read_text())
    credential = {'client_id': VAULTWARDEN, 'client_secret': secrets.token_urlsafe(48)}
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(credential))
    path.chmod(0o600)
    return credential


def ensure_oidc_client(api, client, display_name, base_url, callback,
                       flows, mappings, signing_key, groups):
    """Create or correct one OIDC provider and its application, and let the
    shared groups use it.

    `callback` is the application's own path (`/auth/callback` for the cloud
    portal, `/oauth/complete/oidc/` for NetBox), so the strict redirect URI
    stays exact per application.
    """
    desired = provider_body(flows, mappings, signing_key, credential(client), base_url,
                            callback=callback, name=client)
    existing = [row for row in api.rows('providers/oauth2/') if row['name'] == client]
    if not existing:
        provider = api.call('POST', 'providers/oauth2/', desired)
        print(f'CHANGED: created OIDC provider {client}')
    else:
        provider = existing[0]
        changes = drifted(provider, desired)
        if changes:
            provider = api.call('PATCH', f"providers/oauth2/{provider['pk']}/", desired)
            print(f'CHANGED: corrected OIDC provider {client}: {changes}')
        else:
            print(f'OK: OIDC provider {client}')

    applications = [row for row in api.rows('core/applications/') if row['slug'] == client]
    app_body = {'name': display_name, 'slug': client, 'provider': provider['pk'],
                'meta_launch_url': base_url, 'policy_engine_mode': 'any'}
    if not applications:
        application = api.call('POST', 'core/applications/', app_body)
        print(f'CHANGED: created application {client}')
    elif drifted(applications[0], app_body):
        application = api.call('PATCH', f'core/applications/{client}/', app_body)
        print(f'CHANGED: corrected application {client}')
    else:
        application = applications[0]
        print(f'OK: application {client}')

    # Only members of these groups may log in; an application with no binding
    # would admit every Authentik user, including people invited for media only.
    bindings = api.rows(f"policies/bindings/?target={application['pk']}")
    for order, name in enumerate(GROUPS):
        group = groups.get(name)
        if group is None:
            continue
        if any(row.get('group') == group['pk'] for row in bindings):
            print(f'OK: {name} may use {client}')
        else:
            api.call('POST', 'policies/bindings/', {'target': application['pk'],
                                                    'group': group['pk'], 'order': order})
            print(f'CHANGED: {name} may use {client}')
    return application


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


def configure_passkey_login(api):
    """Let people sign in with a passkey alone (passwordless).

    Pointing the authentication flow's identification stage at the flow's
    authenticator validation stage makes the login form offer the browser's
    passkey autofill. Authentik's built-in policies then skip the password and
    validation stages for a passkey login, so this one pointer is the whole
    switch. Passkeys must be discoverable (resident keys) for the prompt to
    appear, and the registration HTTPS name must not change.
    """
    flow = next((row for row in api.rows('flows/instances/')
                 if row['slug'] == 'default-authentication-flow'), None)
    if flow is None:
        raise SystemExit('default-authentication-flow is missing')
    stages = {}
    for binding in api.rows(f"flows/bindings/?target={flow['pk']}"):
        stage = binding.get('stage_obj') or {}
        stages[stage.get('component')] = stage
    identification = stages.get('ak-stage-identification-form')
    validate = stages.get('ak-stage-authenticator-validate-form')
    if identification is None or validate is None:
        raise SystemExit('authentication flow is missing its identification or validation stage')
    detail = api.call('GET', f"stages/identification/{identification['pk']}/")
    if detail.get('webauthn_stage') == validate['pk']:
        print('OK: passkey (passwordless) sign-in')
        return
    # The identification serializer insists on re-reading user_fields, so send
    # them with the patch or it reports "no user fields and no source".
    api.call('PATCH', f"stages/identification/{identification['pk']}/",
             {'webauthn_stage': validate['pk'], 'user_fields': detail.get('user_fields', [])})
    print('CHANGED: passkey (passwordless) sign-in enabled')


def ensure_oauth2_provider(api, name, desired):
    """Create or correct one OIDC provider, reporting drift without echoing secrets."""
    existing = [row for row in api.rows('providers/oauth2/') if row.get('name') == name]
    if not existing:
        provider = api.call('POST', 'providers/oauth2/', desired)
        print(f'CHANGED: created OIDC provider {name}')
        return provider
    provider = existing[0]
    changes = drifted(provider, desired)
    if changes:
        provider = api.call('PATCH', f"providers/oauth2/{provider['pk']}/", desired)
        print(f'CHANGED: corrected OIDC provider {name}: {changes}')
    else:
        print(f'OK: OIDC provider {name}')
    return provider


def ensure_scope_mapping(api, name, scope_name, expression):
    """Create or correct one custom OAuth2 scope mapping."""
    desired = {'name': name, 'scope_name': scope_name, 'expression': expression}
    existing = [row for row in api.rows('propertymappings/provider/scope/')
                if row.get('name') == name]
    if not existing:
        mapping = api.call('POST', 'propertymappings/provider/scope/', desired)
        print(f'CHANGED: created scope mapping {name}')
        return mapping
    mapping = existing[0]
    changes = drifted(mapping, desired)
    if changes:
        mapping = api.call('PATCH',
                           f"propertymappings/provider/scope/{mapping['pk']}/", desired)
        print(f'CHANGED: corrected scope mapping {name}: {changes}')
    else:
        print(f'OK: scope mapping {name}')
    return mapping


def ensure_proxy_provider(api, name, desired):
    """Create or correct one Forward Auth provider for the embedded outpost."""
    payload = {'name': name, **desired}
    existing = [row for row in api.rows('providers/proxy/') if row.get('name') == name]
    if not existing:
        provider = api.call('POST', 'providers/proxy/', payload)
        print(f'CHANGED: created forward-auth provider {name}')
        return provider
    provider = existing[0]
    changes = drifted(provider, payload)
    if changes:
        provider = api.call('PATCH', f"providers/proxy/{provider['pk']}/", payload)
        print(f'CHANGED: corrected forward-auth provider {name}: {changes}')
    else:
        print(f'OK: forward-auth provider {name}')
    return provider


def ensure_application(api, slug, desired):
    """Create or correct one Authentik application and return it.

    superuser_full_list is required: the plain list only returns applications
    the requesting user can see, and the media apps are bound to the users
    group. Without it a redeploy does not find the application it created and
    POSTs a duplicate (HTTP 400 "slug already exists", 2026-09-12).
    """
    applications = [row for row in api.rows('core/applications/?superuser_full_list=true')
                    if row.get('slug') == slug]
    if not applications:
        application = api.call('POST', 'core/applications/', desired)
        print(f'CHANGED: created application {slug}')
    elif drifted(applications[0], desired):
        application = api.call('PATCH', f'core/applications/{slug}/', desired)
        print(f'CHANGED: corrected application {slug}')
    else:
        application = applications[0]
        print(f'OK: application {slug}')
    return application


def bind_group(api, target, group, order=10):
    """Give one group access to an application; return whether it was added."""
    bindings = api.rows(f'policies/bindings/?target={target}')
    if any(row.get('group') == group for row in bindings):
        return False
    api.call('POST', 'policies/bindings/', {'target': target, 'group': group, 'order': order})
    return True


def outpost_body(current, provider_pks, zone):
    """Union the outpost's providers and point it at https://auth.<zone>.

    The embedded outpost is shared with the services already behind Forward
    Auth, so the update never drops a provider that is not in this declaration.
    """
    providers = sorted(set(current.get('providers') or []) | set(provider_pks))
    config = dict(current.get('config') or {})
    config['authentik_host'] = f'https://auth.{zone}'
    config['authentik_host_browser'] = f'https://auth.{zone}'
    return {'providers': providers, 'config': config}


def ensure_outpost(api, provider_pks, zone, label):
    """Union the embedded outpost's providers and report what changed."""
    outposts = [row for row in api.rows('outposts/instances/')
                if MEDIA_OUTPOST in (row.get('name') or '')]
    if not outposts:
        raise SystemExit(f'Authentik outpost containing {MEDIA_OUTPOST} was not found')
    desired = outpost_body(outposts[0], provider_pks, zone)
    if drifted(outposts[0], desired):
        api.call('PATCH', f"outposts/instances/{outposts[0]['pk']}/", desired)
        print(f'CHANGED: embedded outpost serves the {label}')
    else:
        print('OK: embedded outpost')


def configure_media(api, groups, flows, mappings, signing_key, portal_url):
    """Reconcile the media SSO clients, the Forward Auth providers and access."""
    zone = media_zone(portal_url)
    credentials = media_credentials()
    providers = {}
    for name in MEDIA_OIDC_CLIENTS:
        provider = ensure_oauth2_provider(api, name, oidc_provider_body(
            name, media_redirect(name, zone), flows, mappings, signing_key,
            credentials[name]))
        providers[name] = provider['pk']
    for name in MEDIA_PROXY_PROVIDERS:
        provider = ensure_proxy_provider(api, name, {
            'authorization_flow': flows[AUTHORIZATION_FLOW],
            'invalidation_flow': flows[INVALIDATION_FLOW],
            'mode': 'forward_single',
            'external_host': f'https://{name}.{zone}',
        })
        providers[name] = provider['pk']

    ensure_outpost(api, (providers[name] for name in MEDIA_PROXY_PROVIDERS), zone,
                   'media forward-auth providers')

    # Media is for every invited person, not only administrators: the users
    # group alone gets access, and admins keep the access the cloud app owns.
    for name, label in MEDIA_APPLICATIONS.items():
        application = ensure_application(api, name, {
            'name': label, 'slug': name, 'provider': providers[name],
            'meta_launch_url': f'https://{name}.{zone}',
            'policy_engine_mode': 'any',
        })
        if bind_group(api, application['pk'], groups['users']['pk']):
            print(f'CHANGED: users may use {name}')
        else:
            print(f'OK: users may use {name}')


def configure_homarr(api, groups, flows, mappings, signing_key, portal_url):
    """Reconcile the Homarr entry point: OIDC provider, application, access."""
    zone = media_zone(portal_url)
    provider = ensure_oauth2_provider(api, HOMARR, oidc_provider_body(
        HOMARR, homarr_redirect(zone), flows, mappings, signing_key, homarr_credential()))
    application = ensure_application(api, HOMARR, {
        'name': 'Homarr', 'slug': HOMARR, 'provider': provider['pk'],
        'meta_launch_url': f'https://{HOMARR}.{zone}',
        'policy_engine_mode': 'any',
    })
    if bind_group(api, application['pk'], groups['users']['pk']):
        print(f'CHANGED: users may use {HOMARR}')
    else:
        print(f'OK: users may use {HOMARR}')


def configure_grafana(api, groups, flows, mappings, signing_key, portal_url):
    """Reconcile the Grafana monitoring portal: OIDC provider, app, access."""
    zone = media_zone(portal_url)
    provider = ensure_oauth2_provider(api, GRAFANA, oidc_provider_body(
        GRAFANA, grafana_redirect(zone), flows, mappings, signing_key, grafana_credential()))
    application = ensure_application(api, GRAFANA, {
        'name': 'Grafana', 'slug': GRAFANA, 'provider': provider['pk'],
        'meta_launch_url': f'https://{GRAFANA}.{zone}',
        'policy_engine_mode': 'any',
    })
    for order, name in enumerate(GROUPS):
        if bind_group(api, application['pk'], groups[name]['pk'], order=order):
            print(f'CHANGED: {name} may use {GRAFANA}')
        else:
            print(f'OK: {name} may use {GRAFANA}')


def configure_vaultwarden(api, groups, flows, mappings, signing_key, portal_url):
    """Reconcile Vaultwarden's native OIDC client: provider, application, access."""
    zone = media_zone(portal_url)
    provider = ensure_oauth2_provider(api, VAULTWARDEN, oidc_provider_body(
        VAULTWARDEN, vaultwarden_redirect(zone), flows, mappings, signing_key,
        vaultwarden_credential()))
    application = ensure_application(api, VAULTWARDEN, {
        'name': 'Vaultwarden', 'slug': VAULTWARDEN, 'provider': provider['pk'],
        'meta_launch_url': f'https://{VAULTWARDEN_HOST}.{zone}',
        'policy_engine_mode': 'any',
    })
    if bind_group(api, application['pk'], groups['users']['pk']):
        print(f'CHANGED: users may use {VAULTWARDEN}')
    else:
        print(f'OK: users may use {VAULTWARDEN}')


def configure_home_assistant(api, groups, flows, mappings, signing_key, portal_url):
    """Reconcile Home Assistant's OIDC client for the community auth_oidc integration.

    Both groups get access: akadmin is not a member of `users`, so binding only
    `users` would lock the administrator out of the SSO entrance.  The HA roles
    still come from the groups claim (`admins` is administrator).
    """
    zone = media_zone(portal_url)
    provider = ensure_oauth2_provider(api, HOME_ASSISTANT, public_oidc_provider_body(
        HOME_ASSISTANT, home_assistant_redirect(zone), flows, mappings, signing_key))
    application = ensure_application(api, HOME_ASSISTANT, {
        'name': 'Home Assistant', 'slug': HOME_ASSISTANT, 'provider': provider['pk'],
        'meta_launch_url': f'https://{HOME_ASSISTANT_HOST}.{zone}',
        'policy_engine_mode': 'any',
    })
    for order, name in enumerate(GROUPS):
        if bind_group(api, application['pk'], groups[name]['pk'], order=order):
            print(f'CHANGED: {name} may use {HOME_ASSISTANT}')
        else:
            print(f'OK: {name} may use {HOME_ASSISTANT}')


def configure_cups(api, groups, flows, portal_url):
    """Reconcile the CUPS status page: Forward Auth provider, access, outpost.

    Printing itself stays on IPP 631; only the browser UI goes through SSO.
    """
    zone = media_zone(portal_url)
    provider = ensure_proxy_provider(api, CUPS, {
        'authorization_flow': flows[AUTHORIZATION_FLOW],
        'invalidation_flow': flows[INVALIDATION_FLOW],
        'mode': 'forward_single',
        'external_host': f'https://{CUPS}.{zone}',
    })
    application = ensure_application(api, CUPS, {
        'name': 'CUPS', 'slug': CUPS, 'provider': provider['pk'],
        'meta_launch_url': f'https://{CUPS}.{zone}',
        'policy_engine_mode': 'any',
    })
    if bind_group(api, application['pk'], groups['users']['pk']):
        print(f'CHANGED: users may use {CUPS}')
    else:
        print(f'OK: users may use {CUPS}')
    ensure_outpost(api, [provider['pk']], zone, 'CUPS forward-auth provider')


def configure_adguard(api, groups, flows, portal_url):
    """Reconcile the AdGuard Home UI: Forward Auth provider, access, outpost."""
    zone = media_zone(portal_url)
    provider = ensure_proxy_provider(api, ADGUARD, {
        'authorization_flow': flows[AUTHORIZATION_FLOW],
        'invalidation_flow': flows[INVALIDATION_FLOW],
        'mode': 'forward_single',
        'external_host': f'https://{ADGUARD}.{zone}',
    })
    application = ensure_application(api, ADGUARD, {
        'name': 'AdGuard Home', 'slug': ADGUARD, 'provider': provider['pk'],
        'meta_launch_url': f'https://{ADGUARD}.{zone}',
        'policy_engine_mode': 'any',
    })
    if bind_group(api, application['pk'], groups['users']['pk']):
        print(f'CHANGED: users may use {ADGUARD}')
    else:
        print(f'OK: users may use {ADGUARD}')
    ensure_outpost(api, [provider['pk']], zone, 'AdGuard forward-auth provider')


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
    # Authentikのmanaged emailマッピングはemail_verified=Falseを返す。検証済み
    # メールを要求するVaultwarden・Kavitaには独自マッピングを使う（2026-09-13）。
    verified_email = ensure_scope_mapping(api, VERIFIED_EMAIL_MAPPING, 'email',
                                          VERIFIED_EMAIL_EXPRESSION)
    # profile carries the groups claim the API and NetBox use to recognise admins.
    # offline_access lets clients that ask for it receive a refresh token
    # (Vaultwarden's SSO session keeps working with one).
    mappings = [row['pk'] for row in api.rows('propertymappings/provider/scope/')
                if row.get('managed', '')
                and row['scope_name'] in ('openid', 'profile', 'offline_access')]
    mappings.append(verified_email['pk'])
    keys = [row['pk'] for row in api.rows('crypto/certificatekeypairs/') if row['name'] == SIGNING_KEY]
    if not keys:
        raise SystemExit(f'Signing key not found: {SIGNING_KEY}')
    portal_url = os.environ['CLOUD_PORTAL_URL']
    ensure_oidc_client(api, CLIENT, 'shake-cloud', portal_url, '/auth/callback',
                       flows, mappings, keys[0], groups)

    # NetBox logs in through the same Authentik when NETBOX_URL is deployed.
    netbox_url = os.environ.get('NETBOX_URL', '').strip()
    if netbox_url:
        ensure_oidc_client(api, 'netbox', 'NetBox', netbox_url, '/oauth/complete/oidc/',
                           flows, mappings, keys[0], groups)
    else:
        print('note: NETBOX_URL is not set; skipped the NetBox OIDC client')

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
    configure_passkey_login(api)
    configure_media(api, groups, flows, mappings, keys[0], portal_url)
    configure_homarr(api, groups, flows, mappings, keys[0], portal_url)
    configure_grafana(api, groups, flows, mappings, keys[0], portal_url)
    configure_vaultwarden(api, groups, flows, mappings, keys[0], portal_url)
    configure_home_assistant(api, groups, flows, mappings, keys[0], portal_url)
    configure_cups(api, groups, flows, portal_url)
    configure_adguard(api, groups, flows, portal_url)


if __name__ == '__main__':
    main()
