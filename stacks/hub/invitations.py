#!/usr/bin/env python3
"""Manage invitation-only enrollment. Never send mail or print invitation tokens."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import secrets

import requests

ROOT = Path(__file__).resolve().parents[1]
SLUG = 'media-invitation-enrollment'
IDENTITY = 'https://login.localhost:9443'


class IdentityAPI:
    def __init__(self):
        values = dict(line.split('=', 1) for line in (ROOT / 'hub/.env').read_text().splitlines()
                      if '=' in line and not line.startswith('#'))
        self.session = requests.Session()
        self.session.headers['Authorization'] = 'Bearer ' + values['AUTHENTIK_BOOTSTRAP_TOKEN']

    def call(self, method, path, **kwargs):
        response = self.session.request(method, 'http://localhost:9000/api/v3/' + path,
                                        timeout=30, **kwargs)
        if not response.ok:
            raise RuntimeError(f'Identity API {method} {path.split("?")[0]}: HTTP {response.status_code}')
        return response.json() if response.content else None

    def rows(self, path):
        result = []
        page = 1
        while True:
            data = self.call('GET', path, params={'page_size': 100, 'page': page})
            result.extend(data['results'])
            if not data['pagination']['next']:
                return result
            page += 1

    def ensure(self, path, identifiers, values):
        matches = [row for row in self.rows(path)
                   if all(row.get(key) == value for key, value in identifiers.items())]
        if len(matches) > 1:
            raise RuntimeError('Ambiguous managed identity object')
        payload = {**identifiers, **values}
        if matches:
            key = matches[0]['slug'] if path == 'flows/instances/' else matches[0]['pk']
            return self.call('PATCH', path + str(key) + '/', json=payload)
        return self.call('POST', path, json=payload)


def configure(api):
    group = next(x for x in api.rows('core/groups/') if x['name'] == 'media-users')
    flow = api.ensure('flows/instances/', {'slug': SLUG}, {
        'name': 'Media invitation enrollment', 'title': '招待されたアカウントのパスワードを設定',
        'designation': 'enrollment', 'authentication': 'require_unauthenticated'})
    invite = api.ensure('stages/invitation/stages/', {'name': SLUG + '-token'}, {
        'continue_flow_without_invitation': False})
    fields = []
    for order, (key, label) in enumerate([('password', 'パスワード（12文字以上）'),
                                         ('password_repeat', 'パスワード（確認）')]):
        fields.append(api.ensure('stages/prompt/prompts/', {'name': SLUG + '-' + key}, {
            'field_key': key, 'label': label, 'type': 'password', 'required': True,
            'order': order})['pk'])
    # Identity comes from Invitation stage; Prompt accepts only password fields.
    policy = api.ensure('policies/expression/', {'name': SLUG + '-validate'}, {
        'expression': '''data = request.context.get("prompt_data", {})
if len(data.get("password", "")) < 12:
    ak_message("パスワードは12文字以上にしてください。")
    return False
return True''', 'execution_logging': False})
    prompt = api.ensure('stages/prompt/stages/', {'name': SLUG + '-credentials'}, {
        'fields': fields, 'validation_policies': [policy['pk']]})
    write = api.ensure('stages/user_write/', {'name': SLUG + '-create'}, {
        'user_creation_mode': 'always_create', 'user_type': 'internal',
        'create_users_as_inactive': False, 'create_users_group': group['pk'],
        'user_path_template': 'users/invited'})
    login = api.ensure('stages/user_login/', {'name': SLUG + '-login'}, {})
    for order, stage in [(10, invite), (20, prompt), (30, write), (40, login)]:
        api.ensure('flows/bindings/', {'target': flow['pk'], 'order': order}, {
            'stage': stage['pk'], 'evaluate_on_plan': False, 're_evaluate_policies': True})
    print('Invitation-only flow configured; no invitations issued or messages sent')
    return flow


def issue(api, manifest, confirmed):
    entry = json.loads(manifest.read_text())
    username, email = entry['username'], entry['email'].strip()
    if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}', username) or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise ValueError('Valid username and email are required')
    if any(u['username'] == username or u.get('email', '').casefold() == email.casefold()
           for u in api.rows('core/users/')):
        raise ValueError('Account already exists; use its existing login and verification procedure')
    if any(i.get('fixed_data', {}).get('username') == username or
           i.get('fixed_data', {}).get('email', '').casefold() == email.casefold()
           for i in api.rows('stages/invitation/invitations/')):
        raise ValueError('Invitation already exists; revoke or reuse it in the admin interface')
    flow = next(x for x in api.rows('flows/instances/') if x['slug'] == SLUG)
    expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    record = api.call('POST', 'stages/invitation/invitations/', json={
        'name': 'media-' + secrets.token_hex(8), 'flow': flow['pk'], 'single_use': True,
        'expires': expires, 'fixed_data': {'username': username, 'email': email,
        'name': entry.get('name', username), 'attributes': {'email_verified': confirmed}}})
    directory = ROOT / 'runtime/invitations'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = directory / (record['name'] + '.json')
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump({'url': IDENTITY + '/if/flow/' + SLUG + '/?itoken=' + record['pk'],
                   'expires': expires, 'username': username, 'email': email}, stream, indent=2)
    print('Invitation saved to', target.relative_to(ROOT), '; no message sent')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    subs.add_parser('configure')
    invite = subs.add_parser('invite')
    invite.add_argument('manifest', type=Path)
    invite.add_argument('--email-owner-confirmed', action='store_true',
                        help='Administrator has independently verified ownership of this exact email')
    args = parser.parse_args()
    api = IdentityAPI()
    if args.command == 'configure':
        configure(api)
    else:
        issue(api, args.manifest, args.email_owner_confirmed)


if __name__ == '__main__':
    main()
