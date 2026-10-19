#!/usr/bin/env python3
"""Keep the Nextcloud OAuth2 client of the MCP server registered (idempotent).

Nextcloud stores only a hash of the client secret, so the secret is kept in
OUTPUT (mode 0400) on this host and nowhere else. When OUTPUT is missing, or
Nextcloud no longer has that client or its redirect URI changed, the client is
deleted and registered again (users of the MCP server then log in once more).
Prints CHANGED when it registered a client.

  oauth_client.py NAME REDIRECT_URI OUTPUT
"""
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT = 'media-nextcloud'


def container(service):
    found = subprocess.run(
        ['docker', 'ps', '-q', '--filter', f'label=com.docker.compose.project={PROJECT}',
         '--filter', f'label=com.docker.compose.service={service}'],
        check=True, text=True, capture_output=True).stdout.split()
    if len(found) != 1:
        raise SystemExit(f'expected one running {PROJECT} {service} container, found {len(found)}')
    return found[0]


def occ(*args):
    return subprocess.run(['docker', 'exec', '--user', '33:33', container('nextcloud'), 'php', 'occ', *args],
                          check=True, text=True, capture_output=True).stdout


def clients(name):
    """Return {client_identifier: redirect_uri} of the clients called NAME."""
    query = ("select client_identifier, redirect_uri from oc_oauth2_clients "
             "where name = '" + name.replace("'", "''") + "'")
    out = subprocess.run(
        ['docker', 'exec', container('postgres'), 'sh', '-c',
         'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -AtF "\t" -c "$0"', query],
        check=True, text=True, capture_output=True).stdout
    return dict(line.split('\t', 1) for line in out.splitlines() if '\t' in line)


def main():
    name, redirect_uri, output = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    existing = clients(name)
    if output.exists():
        saved = json.loads(output.read_text())
        if existing.get(saved.get('clientId')) == redirect_uri and len(existing) == 1:
            return
    for identifier in existing:
        occ('oauth2:delete-client', identifier)
    created = json.loads(occ('oauth2:add-client', '--output=json', name, redirect_uri))
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix('.tmp')
    tmp.write_text(json.dumps({'clientId': created['clientId'],
                               'clientSecret': created['clientSecret']}))
    os.chmod(tmp, 0o400)
    tmp.replace(output)
    print('CHANGED')


if __name__ == '__main__':
    main()
