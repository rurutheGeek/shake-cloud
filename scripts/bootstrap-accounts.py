#!/usr/bin/env python3
"""Initialize local Kavita/Navidrome administrators without printing credentials."""
import json
import os
from pathlib import Path
import secrets
import requests

ROOT = Path(__file__).resolve().parents[1]
changed = False
path = ROOT / 'runtime' / 'accounts.json'
path.parent.mkdir(exist_ok=True, mode=0o700)
if not path.exists():
    changed = True
    values = {name: {'username': 'admin', 'password': 'Aa1!' + secrets.token_urlsafe(30)}
              for name in ('kavita', 'navidrome')}
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w') as file:
        json.dump(values, file, indent=2)
values = json.loads(path.read_text())

kavita = requests.Session()
result = kavita.post('http://localhost:5000/api/Account/login', json=values['kavita'], timeout=30)
if result.status_code == 401:
    changed = True
    result = kavita.post('http://localhost:5000/api/Account/register',
                         json=dict(values['kavita'], email='admin@localhost.localdomain'), timeout=30)
result.raise_for_status()
kavita.headers['Authorization'] = 'Bearer ' + result.json()['token']
libraries = kavita.get('http://localhost:5000/api/Library/libraries', timeout=30)
libraries.raise_for_status()
if not any(lib['name'] == 'Books' for lib in libraries.json()):
    changed = True
    settings = kavita.get('http://localhost:5000/api/Settings', timeout=30)
    settings.raise_for_status()
    settings_data = settings.json()
    settings_data['enableFolderWatching'] = True
    result = kavita.post('http://localhost:5000/api/Settings', json=settings_data, timeout=30)
    result.raise_for_status()
    result = kavita.post('http://localhost:5000/api/Library/create', json={
        'id': 0, 'name': 'Books', 'type': 2, 'folders': ['/books'],
        'folderWatching': True, 'includeInDashboard': True, 'includeInSearch': True,
        'manageCollections': True, 'manageReadingLists': True, 'allowScrobbling': False,
        'allowMetadataMatching': False, 'enableMetadata': False,
        'removePrefixForSortName': False, 'inheritWebLinksFromFirstChapter': False,
        'defaultLanguage': 'ja', 'metadataProvider': 2,
        'fileGroupTypes': [1, 2, 3, 4], 'excludePatterns': [],
    }, timeout=30)
    if not result.ok:
        print('Kavita library rejected:', result.status_code, result.text[:500])
    result.raise_for_status()
print('Kavita admin login and Books library verified')

import stack
env=stack.settings()
nav_url='http://localhost:'+env.get('NAVIDROME_PORT','4533')
navidrome = requests.Session()
result = navidrome.post(nav_url+'/auth/login', json=values['navidrome'], timeout=30)
if result.status_code in (401, 403):
    changed = True
    result = navidrome.post(nav_url+'/auth/createAdmin', json=values['navidrome'], timeout=30)
result.raise_for_status()
assert result.json()['isAdmin'] is True
print('Navidrome admin login verified')

# Consumers such as the music synchronization timer use this private access file.
access_path = ROOT / 'runtime' / 'access.json'
access = json.loads(access_path.read_text()) if access_path.exists() else {}
for name, port in [('kavita', 5000), ('navidrome', 4533)]:
    access[name] = dict(access.get(name, {}), **values[name], url=f'http://localhost:{port}')
fd = os.open(access_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as file:
    json.dump(access, file, indent=2)
access_path.chmod(0o600)

print('CHANGED: media accounts initialized' if changed else 'OK: media accounts already initialized')
