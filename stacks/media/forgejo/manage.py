#!/usr/bin/env python3
"""Deploy Forgejo (the repository archive) as an independent Compose project on media-01.

Secrets are passed to Compose as environment variables, never written to .env.
After the container is healthy, `up` reconciles the Authentik login source, the
local administrator the API calls use, the archive organization and the pull
mirrors listed in mirrors.json. Removing a mirror from the list never deletes
the repository: keeping it is the point of the archive.
"""
import argparse
import datetime
import json
import os
import secrets
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GENERATED_SECRETS = ('secret_key', 'internal_token', 'jwt_secret', 'admin_password')
OIDC_SECRET_FILE = 'oidc_client.json'
TOKEN_FILE = 'admin_token'
# 管理用のローカル利用者。人は Authentik から入り、admins グループが管理者になる。
ADMIN_USER = 'shakecloud'
ADMIN_EMAIL = 'shakecloud@localhost'
AUTH_SOURCE = 'authentik'
TOKEN_SCOPES = 'write:repository,write:organization,read:user'


def settings():
    """Read the literal KEY=value pairs Compose and init share."""
    values = {}
    for line in (ROOT / '.env').read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not key.replace('_', '').isalnum():
            raise ValueError('Invalid .env line; use KEY=literal_value')
        values[key] = value
    return values


def secret(name):
    path = ROOT / 'secrets' / name
    return path.read_text().strip() if path.exists() else ''


def oidc_client():
    path = ROOT / 'secrets' / OIDC_SECRET_FILE
    return json.loads(path.read_text()) if path.exists() else {}


def compose(*args, locked=True, capture_output=False, check=True):
    command = ['docker', 'compose', '--env-file', str(ROOT / '.env'),
               '-f', str(ROOT / 'compose.yaml')]
    if locked and (ROOT / 'compose.lock.yaml').exists():
        command += ['-f', str(ROOT / 'compose.lock.yaml')]
    environment = dict(os.environ)
    # Shell variables must not silently change .env paths.
    environment.update(settings())
    # Secrets travel to the container only through the environment.
    environment.update({
        'FORGEJO_SECRET_KEY': secret('secret_key'),
        'FORGEJO_INTERNAL_TOKEN': secret('internal_token'),
        'FORGEJO_JWT_SECRET': secret('jwt_secret'),
    })
    return subprocess.run(command + list(args), cwd=ROOT, check=check, text=True,
                          env=environment, capture_output=capture_output)


def forgejo(*args, check=True):
    """Run the forgejo CLI inside the container as the git user."""
    return compose('exec', '-T', '--user', 'git', 'forgejo', 'forgejo', *args,
                   capture_output=True, check=check)


def state():
    """Return the Forgejo state directory (repositories, SQLite, LFS)."""
    config = settings()
    return Path(config.get('STORAGE_ROOT', '/srv/media-stack/storage')) / 'forgejo'


def run(args):
    return subprocess.run(args, cwd=ROOT, check=True)


def init():
    env = ROOT / '.env'
    if not env.exists():
        env.write_bytes((ROOT / '.env.example').read_bytes())
    env.chmod(0o600)
    config = settings()
    uid = int(config.get('FORGEJO_UID', 1000))
    gid = int(config.get('FORGEJO_GID', 1000))
    storage = state()
    if not storage.exists():
        storage.mkdir(parents=True, mode=0o750)
    if (storage.stat().st_uid, storage.stat().st_gid) != (uid, gid):
        if os.geteuid() != 0:
            raise PermissionError(f'Run init with sudo to own {storage} as {uid}:{gid}')
        os.chown(storage, uid, gid)
    directory = ROOT / 'secrets'
    directory.mkdir(exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    for name in GENERATED_SECRETS:
        target = directory / name
        if not target.exists():
            with target.open('x') as file:
                # 32 bytes in URL-safe base64 is the form JWT_SECRET expects.
                file.write(secrets.token_urlsafe(32) + '\n')
        if not target.read_text().strip():
            raise ValueError(f'Empty secret: {name}')
        target.chmod(0o400)
    print('OK: Forgejo data and secrets are ready')


def lock():
    lockfile = ROOT / 'compose.lock.yaml'
    if lockfile.exists():
        print('OK: existing image digests preserved')
        return
    compose('pull', locked=False)
    config = json.loads(compose('config', '--format', 'json', locked=False,
                                capture_output=True).stdout)
    services = {}
    for name, service in config['services'].items():
        data = json.loads(subprocess.check_output(
            ['docker', 'image', 'inspect', service['image']], text=True))[0]
        services[name] = {'image': data['RepoDigests'][0]}
    lockfile.write_text(json.dumps({'services': services}, indent=2) + '\n')
    print('CHANGED: image digests pinned in compose.lock.yaml')


def auth_sources():
    """Return {name: id} from `forgejo admin auth list` (tab-padded columns)."""
    lines = forgejo('admin', 'auth', 'list').stdout.splitlines()
    sources = {}
    for line in lines[1:]:
        fields = line.split()
        if len(fields) >= 2 and fields[0].isdigit():
            sources[fields[1]] = fields[0]
    return sources


def configure_login():
    """Create or correct the Authentik login source once its secret is installed."""
    client = oidc_client()
    if not client.get('client_secret'):
        print('OK: OIDC secret not installed yet; run media-forgejo-sso.yml')
        return
    options = ['--provider', 'openidConnect',
               '--key', client['client_id'], '--secret', client['client_secret'],
               '--auto-discover-url', settings()['FORGEJO_OIDC_DISCOVERY_URL'],
               '--scopes', 'openid', '--scopes', 'email', '--scopes', 'profile',
               '--group-claim-name', 'groups', '--admin-group', 'admins',
               '--skip-local-2fa']
    existing = auth_sources().get(AUTH_SOURCE)
    if existing:
        forgejo('admin', 'auth', 'update-oauth', '--id', existing, '--name', AUTH_SOURCE, *options)
        print(f'OK: login source {AUTH_SOURCE} reconciled')
    else:
        forgejo('admin', 'auth', 'add-oauth', '--name', AUTH_SOURCE, *options)
        print(f'CHANGED: login source {AUTH_SOURCE} added')


def configure_admin():
    """Keep the local administrator and an API token for the mirror reconciler."""
    users = forgejo('admin', 'user', 'list', '--admin').stdout.split()
    if ADMIN_USER not in users:
        forgejo('admin', 'user', 'create', '--admin', '--username', ADMIN_USER,
                '--email', ADMIN_EMAIL, '--password', secret('admin_password'),
                '--must-change-password=false')
        print(f'CHANGED: administrator {ADMIN_USER} created')
    token = ROOT / 'secrets' / TOKEN_FILE
    if token.exists() and token.read_text().strip():
        return
    value = forgejo('admin', 'user', 'generate-access-token', '--username', ADMIN_USER,
                    '--token-name', 'manage-py', '--scopes', TOKEN_SCOPES, '--raw').stdout.strip()
    with token.open('x') as file:
        file.write(value + '\n')
    token.chmod(0o400)
    print('CHANGED: API token for manage.py stored')


def api(method, path, body=None):
    """Call the Forgejo API on loopback. Returns (status, parsed JSON or None)."""
    port = settings().get('FORGEJO_PORT', '8083')
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f'http://127.0.0.1:{port}/api/v1{path}', data=data, method=method,
        headers={'Authorization': 'token ' + secret(TOKEN_FILE),
                 'Content-Type': 'application/json', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return 404, None
        raise RuntimeError(f'{method} {path}: HTTP {error.code} {error.read()[:300]!r}') from error


def mirror_list():
    """Validate mirrors.json: [{"url": ..., "name"?: ..., "interval"?: ..., "wiki"?: bool, "lfs"?: bool}]."""
    entries = json.loads((ROOT / 'mirrors.json').read_text())
    if not isinstance(entries, list):
        raise ValueError('mirrors.json must be a JSON list')
    names = set()
    for entry in entries:
        url = entry.get('url', '')
        if not url.startswith('https://'):
            raise ValueError(f'mirror url must be https: {url!r}')
        name = entry.get('name') or urllib.parse.urlsplit(url).path.rstrip('/').split('/')[-1].removesuffix('.git')
        if not name or name in names:
            raise ValueError(f'mirror name missing or duplicated: {name!r}')
        names.add(name)
        entry['name'] = name
    return entries


def mirrors():
    """Create the archive organization and every listed mirror that is missing."""
    organization = settings().get('FORGEJO_ARCHIVE_ORG', 'archive')
    status, _ = api('GET', f'/orgs/{organization}')
    if status == 404:
        api('POST', '/orgs', {'username': organization, 'visibility': 'private'})
        print(f'CHANGED: organization {organization} created')
    for entry in mirror_list():
        name = entry['name']
        status, _ = api('GET', f'/repos/{organization}/{name}')
        if status != 404:
            print(f'OK: mirror {organization}/{name}')
            continue
        api('POST', '/repos/migrate', {
            'clone_addr': entry['url'], 'repo_owner': organization, 'repo_name': name,
            'mirror': True, 'mirror_interval': entry.get('interval', settings().get('FORGEJO_MIRROR_INTERVAL', '8h')),
            'private': True, 'wiki': bool(entry.get('wiki', True)), 'lfs': bool(entry.get('lfs', False)),
            'service': 'git',
        })
        print(f'CHANGED: mirror {organization}/{name} created from {entry["url"]}')


def configure():
    configure_login()
    configure_admin()
    mirrors()


def up():
    lock()
    mirror_list()
    compose('config', '--quiet')
    compose('up', '-d', '--wait', '--wait-timeout', '180')
    configure()


def backup(destination):
    if os.geteuid() != 0:
        raise PermissionError('Run backup with sudo to read all application state')
    storage = state()
    destination = Path(destination).resolve()
    if destination == storage or storage in destination.parents:
        raise ValueError('Backup destination must be outside the state directory')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = destination / (stamp + '.incomplete')
    target.mkdir(mode=0o700)
    running = compose('ps', '--services', '--status', 'running',
                      capture_output=True).stdout.split()
    # Cold snapshot: SQLite and the repositories are copied while nothing writes.
    try:
        compose('stop', '--timeout', '120')
        run(['tar', '--numeric-owner', '-cpf', str(target / 'state.tar'),
             '-C', str(storage), '.'])
        run(['tar', '--numeric-owner', '-cpf', str(target / 'deployment.tar'),
             'compose.yaml', 'compose.lock.yaml', '.env', '.env.example',
             'manage.py', 'mirrors.json', 'secrets'])
        (target / 'manifest.json').write_text(json.dumps({
            'storage_root': str(storage),
            'created_utc': stamp,
            'architecture': os.uname().machine,
            'format': 1,
            'notes': 'Cold backup of Forgejo state (repositories, LFS, SQLite) and '
                     'the deployment (Compose, mirror list, secrets). Restore with '
                     'services stopped into a new or empty directory.',
        }, indent=2) + '\n')
    finally:
        if running:
            compose('start', *running)
    complete = target.with_suffix('')
    target.rename(complete)
    print(f'Backup complete: {complete}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',
                        choices=['init', 'lock', 'up', 'configure', 'mirrors', 'status', 'down', 'backup'])
    parser.add_argument('--destination', default=str(ROOT / 'backups'))
    args = parser.parse_args()
    if args.action in ('init', 'up', 'configure', 'mirrors'):
        init()
    if args.action == 'lock':
        lock()
    elif args.action == 'up':
        up()
    elif args.action == 'configure':
        configure()
    elif args.action == 'mirrors':
        mirrors()
    elif args.action == 'status':
        compose('ps')
    elif args.action == 'down':
        compose('down')
    elif args.action == 'backup':
        backup(args.destination)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
