#!/usr/bin/env python3
"""Configure Kavita's native OIDC against the shared identity provider.

Runs on media-01 after `bootstrap.py`. The client credentials come from the
environment as KAVITA_OIDC_CLIENT_ID / KAVITA_OIDC_CLIENT_SECRET; the secret
value is never printed. Only when the reported settings differ does this script
write them back and restart Kavita (the settings endpoint reads them at login
time). Idempotent: prints CHANGED or OK and exits non-zero on API errors.

Requires the `requests` module (installed as python3-requests by
platform/ansible/media-kavita.yml).
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import requests

ROOT = Path(__file__).resolve().parent
AUTHORITY = 'https://auth.apextox.dpdns.org/application/o/kavita/'
DEFAULT_ROLES = ['Pleb', 'Login', 'Download', 'Bookmark']
LIBRARY_NAME = 'Books'


def settings():
    """Read the literal KEY=value pairs Compose and this script share."""
    values = {}
    path = ROOT / '.env'
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not key.replace('_', '').isalnum():
            raise ValueError('Invalid .env line; use KEY=literal_value')
        values[key] = value
    return values


def accounts_path():
    return ROOT / 'secrets' / 'accounts.json'


def base_url():
    port = settings().get('KAVITA_PORT') or os.environ.get('KAVITA_PORT', '5000')
    return f'http://127.0.0.1:{port}'


def compose(*args):
    command = ['docker', 'compose', '--env-file', str(ROOT / '.env'),
               '-f', str(ROOT / 'compose.yaml')]
    if (ROOT / 'compose.lock.yaml').exists():
        command += ['-f', str(ROOT / 'compose.lock.yaml')]
    environment = dict(os.environ)
    environment.update(settings())
    return subprocess.run(command + list(args), cwd=ROOT, check=True, text=True,
                          env=environment, capture_output=True)


def default_libraries(libraries):
    return [library['id'] for library in libraries if library.get('name') == LIBRARY_NAME]


def desired_config(client_id, client_secret, library_ids):
    return {
        'authority': AUTHORITY,
        'clientId': client_id,
        'secret': client_secret,
        'provisionAccounts': True,
        'requireVerifiedEmail': True,
        'syncUserSettings': False,
        'defaultRoles': DEFAULT_ROLES,
        'defaultLibraries': library_ids,
        'defaultIncludeUnknowns': True,
    }


def drifted(current, desired):
    def normal(value):
        return sorted(value, key=json.dumps) if isinstance(value, list) else value
    return sorted(key for key, value in desired.items()
                  if normal(current.get(key)) != normal(value))


def main():
    client_id = os.environ.get('KAVITA_OIDC_CLIENT_ID', '')
    client_secret = os.environ.get('KAVITA_OIDC_CLIENT_SECRET', '')
    if not client_id or not client_secret:
        raise RuntimeError('Set KAVITA_OIDC_CLIENT_ID and KAVITA_OIDC_CLIENT_SECRET')
    base = base_url()
    accounts = json.loads(accounts_path().read_text())
    session = requests.Session()
    result = session.post(base + '/api/Account/login', json=accounts, timeout=30)
    result.raise_for_status()
    session.headers['Authorization'] = 'Bearer ' + result.json()['token']
    result = session.get(base + '/api/Settings', timeout=30)
    result.raise_for_status()
    server = result.json()
    result = session.get(base + '/api/Library/libraries', timeout=30)
    result.raise_for_status()
    library_ids = default_libraries(result.json())
    if not library_ids:
        raise RuntimeError(f'The {LIBRARY_NAME} library is missing; run bootstrap.py first')
    current = server.setdefault('oidcConfig', {})
    desired = desired_config(client_id, client_secret, library_ids)
    changes = drifted(current, desired)
    if not changes:
        print('OK: Kavita OIDC already configured')
        return
    current.update(desired)
    result = session.post(base + '/api/Settings', json=server, timeout=60)
    if not result.ok:
        raise RuntimeError(f'Kavita OIDC settings rejected (HTTP {result.status_code})')
    compose('restart', 'kavita')
    print('CHANGED: Kavita OIDC configured: ' + ', '.join(changes))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, requests.RequestException) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
