#!/usr/bin/env python3
"""Invitation-only enrollment, run by the identity administrator.

This belongs to the **identity service** (Authentik), not to any one application.
The administrator issues a single-use link; the person opens it, sets a password,
and lands in the groups the invitation names (the cloud's `cloud-users` by
default). Applications then create their own account on first SSO login.

    python3 invitations.py configure                 # create/repair the flow
    python3 invitations.py invite --username alice --email alice@example.org
    python3 invitations.py list
    python3 invitations.py revoke --name cloud-0123...

It sends the link by email when SMTP is configured in .env (SMTP_HOST,
SMTP_FROM, ...), and always saves it to a 0600 file under runtime/invitations/ as
a record. Without SMTP the administrator takes the link to the person by another
route. The token itself is never printed, so it does not reach a terminal
scrollback or a log.
"""
import argparse
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import json
import os
from pathlib import Path
import re
import secrets
import smtplib
import ssl
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
BASE = os.environ.get('AUTHENTIK_URL', 'http://localhost:9000') + '/api/v3/'
SLUG = 'cloud-invitation-enrollment'
DEFAULT_GROUP = 'cloud-users'
# The link must be openable from outside the identity VM. The flow runs at the
# same Authentik by name or by 127.0.0.1, but only the name works for a browser.
EXTERNAL = os.environ.get('AUTHENTIK_EXTERNAL_URL', 'https://auth.apextox.dpdns.org').rstrip('/')
USERNAME = re.compile(r'[a-zA-Z0-9_.-]{1,100}')
EMAIL = re.compile(r'[^\s@]+@[^\s@]+\.[^\s@]+')


class API:
    """The slice of Authentik's v3 API this tool needs."""

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
            # Field names only: bodies can echo values back.
            try:
                fields = list(json.loads(error.read()))
            except ValueError:
                fields = []
            raise RuntimeError(f'{method} {path.split("?")[0]}: HTTP {error.code}; fields: {fields}') from None
        return json.loads(content) if content else None

    def rows(self, path):
        return self.call('GET', path + ('&' if '?' in path else '?') + 'page_size=1000')['results']

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


def configure(api, group_name=DEFAULT_GROUP):
    """Create the invitation-only enrollment flow that adds invitees to group_name."""
    group = next((row for row in api.rows('core/groups/') if row['name'] == group_name), None)
    if group is None:
        raise SystemExit(f'Group {group_name} does not exist; run configure.py first')

    flow = api.ensure('flows/instances/', {'slug': SLUG}, {
        'name': 'Invitation enrollment', 'title': '招待されたアカウントの登録',
        'designation': 'enrollment', 'authentication': 'require_unauthenticated'})
    # The invitation is the only way in; opening the flow without one is refused.
    invite = api.ensure('stages/invitation/stages/', {'name': SLUG + '-token'}, {
        'continue_flow_without_invitation': False})
    fields = []
    for order, (key, label) in enumerate([('password', 'パスワード（12文字以上）'),
                                          ('password_repeat', 'パスワード（確認）')]):
        fields.append(api.ensure('stages/prompt/prompts/', {'name': SLUG + '-' + key}, {
            'field_key': key, 'label': label, 'type': 'password', 'required': True,
            'order': order})['pk'])
    # Username and email come from the invitation; the prompt accepts passwords
    # only, so an invitee cannot change who they are or choose their own groups.
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
    print(f'OK: invitation-only enrollment configured, invitees join {group_name}')
    return flow


def _pending(api):
    return api.rows('stages/invitation/invitations/')


def smtp_settings(environ=None, dotenv=None):
    """SMTP settings from the environment, falling back to .env. None if unset.

    Returns None when SMTP_HOST is empty, which is the normal state until an
    SMTP provider is chosen: the tool then only saves the link to a file.
    """
    values = {}
    if dotenv and Path(dotenv).exists():
        for line in Path(dotenv).read_text(encoding='utf-8').splitlines():
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip()
    environ = environ or {}

    def get(key):
        return environ.get(key) or values.get(key) or ''

    host = get('SMTP_HOST')
    if not host:
        return None
    port = int(get('SMTP_PORT') or 587)
    security = get('SMTP_SECURITY') or ('ssl' if port == 465 else 'starttls' if port == 587 else 'plain')
    sender = get('SMTP_FROM')
    if not sender:
        raise SystemExit('SMTP_HOST is set but SMTP_FROM is missing')
    return {'host': host, 'port': port, 'username': get('SMTP_USERNAME'), 'password': get('SMTP_PASSWORD'),
            'sender': sender, 'from_name': get('SMTP_FROM_NAME') or 'shake-cloud', 'security': security}


def build_message(settings, name, email, url, expires):
    message = EmailMessage()
    message['From'] = f"{settings['from_name']} <{settings['sender']}>"
    message['To'] = f'{name} <{email}>' if name else email
    message['Subject'] = 'shake-cloud への招待'
    message.set_content(f"""{name or username_of(email)} さん

ホームラボのプライベートクラウド（shake-cloud）へ招待します。
次のリンクを開き、パスワード（12文字以上）を設定してください。

{url}

このリンクは1回限りで、{expires} まで有効です。
心当たりが無ければ、このメールは捨ててください。
""")
    return message


def username_of(email):
    return email.split('@', 1)[0]


def deliver(settings, message):
    """Hand the message to the SMTP server. Raises on any failure."""
    if settings['security'] == 'ssl':
        client = smtplib.SMTP_SSL(settings['host'], settings['port'], timeout=30,
                                  context=ssl.create_default_context())
    else:
        client = smtplib.SMTP(settings['host'], settings['port'], timeout=30)
    try:
        client.ehlo()
        if settings['security'] == 'starttls':
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        if settings['username']:
            client.login(settings['username'], settings['password'])
        client.send_message(message)
    finally:
        client.quit()


def invite(api, username, email, name=None, email_owner_confirmed=False, send_email=True, settings=None):
    """Create one single-use invitation and save its link. Returns the saved path."""
    email = (email or '').strip()
    if not USERNAME.fullmatch(username or ''):
        raise ValueError('username must be 1-100 characters of letters, digits, . _ -')
    if not EMAIL.fullmatch(email):
        raise ValueError('a valid email is required')
    if any(u['username'] == username or (u.get('email') or '').casefold() == email.casefold()
           for u in api.rows('core/users/')):
        raise ValueError('an account already has this username or email; use its existing login')
    if any((i.get('fixed_data') or {}).get('username') == username or
           ((i.get('fixed_data') or {}).get('email') or '').casefold() == email.casefold()
           for i in _pending(api) if not (i.get('used_by') or [])):
        raise ValueError('an invitation already exists for this username or email')

    flow = next((row for row in api.rows('flows/instances/') if row['slug'] == SLUG), None)
    if flow is None:
        raise SystemExit('Run `invitations.py configure` first')
    expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    record = api.call('POST', 'stages/invitation/invitations/', {
        'name': 'cloud-' + secrets.token_hex(8), 'flow': flow['pk'], 'single_use': True,
        'expires': expires, 'fixed_data': {
            'username': username, 'email': email, 'name': name or username,
            'attributes': {'email_verified': bool(email_owner_confirmed)}}})
    url = f'{EXTERNAL}/if/flow/{SLUG}/?itoken={record["pk"]}'
    directory = ROOT / 'runtime' / 'invitations'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = directory / (record['name'] + '.json')
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump({'url': url, 'expires': expires, 'username': username, 'email': email}, stream, indent=2)
    print('CHANGED: invitation saved to', target.relative_to(ROOT))
    if not send_email:
        print('note: --no-email; the link is in that file (0600). Share it directly.')
    else:
        settings = settings or smtp_settings(os.environ, ROOT / '.env')
        if settings:
            deliver(settings, build_message(settings, name or username, email, url, expires))
            print(f'CHANGED: invitation emailed to {email}')
        else:
            print('note: SMTP is not configured; the link is in that file (0600). Share it directly.')
    return target


def list_invitations(api):
    rows = _pending(api)
    if not rows:
        print('OK: no invitations')
        return rows
    print(f"{'NAME':<24} {'USERNAME':<20} {'EMAIL':<30} {'EXPIRES':<20} USED")
    now = datetime.now(timezone.utc)
    for row in rows:
        fixed = row.get('fixed_data') or {}
        expires = row.get('expires') or ''
        used = bool(row.get('used_by'))
        state = 'yes' if used else ('expired' if expires and datetime.fromisoformat(expires.replace('Z', '+00:00')) < now else 'no')
        print(f"{row['name']:<24} {fixed.get('username', ''):<20} {fixed.get('email', ''):<30} "
              f"{(expires[:19] if expires else '-'):<20} {state}")
    return rows


def revoke(api, name):
    rows = [row for row in _pending(api) if row['name'] == name or row['pk'] == name]
    if not rows:
        raise SystemExit(f'No invitation named {name}')
    for row in rows:
        api.call('DELETE', f"stages/invitation/invitations/{row['pk']}/")
    # The saved link file, if any, is no longer usable; remove it too.
    saved = ROOT / 'runtime' / 'invitations' / (name + '.json')
    if saved.exists():
        saved.unlink()
    print(f'CHANGED: revoked {name}')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subs = parser.add_subparsers(dest='command', required=True)
    setup = subs.add_parser('configure', help='create or repair the enrollment flow')
    setup.add_argument('--group', default=DEFAULT_GROUP, help=f'invitees join this group (default {DEFAULT_GROUP})')
    add = subs.add_parser('invite', help='create a single-use invitation and save its link')
    add.add_argument('--username', required=True)
    add.add_argument('--email', required=True)
    add.add_argument('--name')
    add.add_argument('--email-owner-confirmed', action='store_true',
                     help='administrator has independently verified ownership of this email')
    add.add_argument('--no-email', action='store_true',
                     help='save the link but do not send it, even when SMTP is configured')
    subs.add_parser('list', help='list invitations and whether they were used')
    remove = subs.add_parser('revoke', help='delete an invitation and its saved link')
    remove.add_argument('--name', required=True)
    args = parser.parse_args()

    token = os.environ.get('AUTHENTIK_TOKEN')
    if not token:
        raise SystemExit('Set AUTHENTIK_TOKEN (the identity bootstrap token)')
    api = API(token)
    if args.command == 'configure':
        configure(api, args.group)
    elif args.command == 'invite':
        invite(api, args.username, args.email, args.name, args.email_owner_confirmed,
               send_email=not args.no_email)
    elif args.command == 'list':
        list_invitations(api)
    else:
        revoke(api, args.name)


if __name__ == '__main__':
    main()
