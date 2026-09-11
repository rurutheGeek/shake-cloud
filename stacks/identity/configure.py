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
GROUPS = ('cloud-users', 'cloud-admins')
CLIENT = 'cloud'
AUTHORIZATION_FLOW = 'default-provider-authorization-implicit-consent'
INVALIDATION_FLOW = 'default-provider-invalidation-flow'
SIGNING_KEY = 'authentik Self-signed Certificate'


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
    if groups['cloud-admins']['pk'] not in admin['groups']:
        api.call('PATCH', f"core/users/{admin['pk']}/",
                 {'groups': admin['groups'] + [groups['cloud-admins']['pk']]})
        print('CHANGED: akadmin joined cloud-admins')

    flows = {row['slug']: row['pk'] for row in api.rows('flows/instances/')}
    # profile carries the groups claim the API uses to recognise cloud-admins.
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


if __name__ == '__main__':
    main()
