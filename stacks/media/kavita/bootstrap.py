#!/usr/bin/env python3
"""Initialize the local Kavita administrator and Books library without printing credentials.

Runs on media-01 after `manage.py up`, against the loopback port in `.env`.
Creates `secrets/accounts.json` once (directory 0700, file 0600) and keeps it
afterwards. Idempotent: prints CHANGED only when it registers, enables folder
watching or creates the library, and OK otherwise.

Requires the `requests` module (installed as python3-requests by
platform/ansible/media-kavita.yml).
"""
import json
import os
from pathlib import Path
import secrets
import sys

import requests

ROOT = Path(__file__).resolve().parent
EMAIL = 'admin@localhost.localdomain'
LIBRARY_NAME = 'Books'
LIBRARY_PATH = '/books'


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


def load_accounts():
    """Return the private admin credentials, generating them once.

    The 0600 file is the only place the random password lives; callers must
    never print it. An existing file is respected so the admin stays the same
    across runs.
    """
    path = accounts_path()
    if path.exists():
        path.chmod(0o600)
        return json.loads(path.read_text()), False
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    values = {'username': 'admin', 'password': 'Aa1!' + secrets.token_urlsafe(30)}
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w') as file:
        json.dump(values, file, indent=2)
    return values, True


def login(session, base, accounts):
    """Log in, registering the very first administrator when Kavita asks."""
    result = session.post(base + '/api/Account/login', json=accounts, timeout=30)
    changed = result.status_code == 401
    if changed:
        result = session.post(base + '/api/Account/register',
                              json=dict(accounts, email=EMAIL), timeout=30)
    result.raise_for_status()
    session.headers['Authorization'] = 'Bearer ' + result.json()['token']
    return changed


def ensure_folder_watching(session, base):
    result = session.get(base + '/api/Settings', timeout=30)
    result.raise_for_status()
    server = result.json()
    if server.get('enableFolderWatching'):
        return False
    server['enableFolderWatching'] = True
    result = session.post(base + '/api/Settings', json=server, timeout=30)
    result.raise_for_status()
    return True


def ensure_books(session, base):
    result = session.get(base + '/api/Library/libraries', timeout=30)
    result.raise_for_status()
    if any(library.get('name') == LIBRARY_NAME for library in result.json()):
        return False
    result = session.post(base + '/api/Library/create', json={
        'id': 0, 'name': LIBRARY_NAME, 'type': 2, 'folders': [LIBRARY_PATH],
        'folderWatching': True, 'includeInDashboard': True, 'includeInSearch': True,
        'manageCollections': True, 'manageReadingLists': True, 'allowScrobbling': False,
        'allowMetadataMatching': False, 'enableMetadata': False,
        'removePrefixForSortName': False, 'inheritWebLinksFromFirstChapter': False,
        'defaultLanguage': 'ja', 'metadataProvider': 2,
        'fileGroupTypes': [1, 2, 3, 4], 'excludePatterns': [],
    }, timeout=30)
    if not result.ok:
        raise RuntimeError(f'Kavita rejected the {LIBRARY_NAME} library (HTTP {result.status_code})')
    return True


def main():
    base = base_url()
    accounts, changed = load_accounts()
    session = requests.Session()
    changed = login(session, base, accounts) or changed
    changed = ensure_folder_watching(session, base) or changed
    changed = ensure_books(session, base) or changed
    print('CHANGED: Kavita admin and Books library initialized'
          if changed else 'OK: Kavita admin and Books library already present')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, requests.RequestException) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
