#!/usr/bin/env python3
"""Deploy UrBackup (client devices) as an independent Compose project on media-01."""
import argparse
import binascii
import datetime
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent


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


def compose(*args, locked=True, capture_output=False):
    command = ['docker', 'compose', '--env-file', str(ROOT / '.env'),
               '-f', str(ROOT / 'compose.yaml')]
    if locked and (ROOT / 'compose.lock.yaml').exists():
        command += ['-f', str(ROOT / 'compose.lock.yaml')]
    environment = dict(os.environ)
    # Prevent shell environment variables from silently changing .env paths.
    environment.update(settings())
    return subprocess.run(command + list(args), cwd=ROOT, check=True, text=True,
                          env=environment, capture_output=capture_output)


def state():
    """Return the UrBackup state directory that a cold backup archives."""
    config = settings()
    return Path(config.get('STORAGE_ROOT', '/srv/media-stack/storage')) / 'urbackup'


def run(args):
    return subprocess.run(args, cwd=ROOT, check=True)


def init():
    env = ROOT / '.env'
    if not env.exists():
        env.write_bytes((ROOT / '.env.example').read_bytes())
    env.chmod(0o600)
    config = settings()
    uid = int(config.get('URBACKUP_UID', 101))
    gid = int(config.get('URBACKUP_GID', 101))
    storage = Path(config.get('STORAGE_ROOT', '/srv/media-stack/storage')) / 'urbackup'
    backups = Path(config.get('CLIENT_BACKUP_ROOT',
                              '/srv/media-stack/client-backups')) / 'urbackup'
    # WebUSB（ポータル）のアップロード先。Docker に作らせると NFS 上で chown に
    # 失敗するため、root（all_squash で 101 になる）で先に作っておく。
    android = Path(config.get('CLIENT_BACKUP_ROOT',
                              '/srv/media-stack/client-backups')) / 'android'
    for path in (storage, backups, android):
        created = not path.exists()
        if created:
            path.mkdir(parents=True, mode=0o770)
        if (path.stat().st_uid, path.stat().st_gid) != (uid, gid):
            if os.geteuid() != 0:
                raise PermissionError(f'Run init with sudo to own {path} as {uid}:{gid}')
            os.chown(path, uid, gid)
    secret_dir = ROOT / 'secrets'
    secret_dir.mkdir(mode=0o700, exist_ok=True)
    password = secret_dir / 'urbackup_admin_password'
    if not password.exists():
        password.write_text(secrets.token_urlsafe(24) + '\n')
        password.chmod(0o400)
    print('OK: UrBackup state, backup directory and admin password are ready')


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


def up():
    lock()
    compose('config', '--quiet')
    compose('up', '-d', '--wait', '--wait-timeout', '180')


class Api:
    """Minimal UrBackup server web API client (the /x JSON endpoints).

    The login handshake mirrors the server's own Python wrapper: ask for the
    salt, hash the password with md5 (+ pbkdf2 when requested), then log in.
    """

    def __init__(self, base, username, password):
        # エンドポイントは /x。ここへ余分なスラッシュを足すと "Unknown action" に
        # なる（実測）。パスは付けず、?a= だけを足す。
        self.base = base.rstrip('/')
        self.username = username
        self.password = password
        self.session = ''
        self.logged_in = False

    def call(self, action, params=None, method='POST'):
        params = dict(params or {})
        if self.session:
            params['ses'] = self.session
        url = self.base + '?' + urllib.parse.urlencode({'a': action})
        if method == 'GET':
            url += '&' + urllib.parse.urlencode(params)
            request = urllib.request.Request(url, method='GET')
        else:
            request = urllib.request.Request(
                url, data=urllib.parse.urlencode(params).encode(), method='POST')
        request.add_header('Accept', 'application/json')
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode('utf-8', 'ignore')
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body

    def login(self):
        if self.logged_in:
            return True
        salt = self.call('salt', {'username': self.username})
        if not isinstance(salt, dict) or 'ses' not in salt:
            return False
        self.session = salt['ses']
        digest = hashlib.md5((salt['salt'] + self.password).encode()).digest()
        password = binascii.hexlify(digest).decode()
        rounds = int(salt.get('pbkdf2_rounds', 0) or 0)
        if rounds > 0:
            password = binascii.hexlify(hashlib.pbkdf2_hmac(
                'sha256', digest, salt['salt'].encode(), rounds)).decode()
        password = hashlib.md5((salt['rnd'] + password).encode()).hexdigest()
        result = self.call('login', {'username': self.username, 'password': password})
        self.logged_in = bool(result) and bool(result.get('success'))
        return self.logged_in


def general_settings(api):
    result = api.call('settings', {'sa': 'general'})
    if not isinstance(result, dict) or 'settings' not in result:
        raise RuntimeError('the server did not return the general settings')
    # 値は {'value': ...} のものと、素の文字列・真偽値のものが混在する。
    return {key: value.get('value') if isinstance(value, dict) else value
            for key, value in result['settings'].items()}


def wait_for_api(api, timeout=120):
    """Wait until the web API answers (with the login salt)."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            salt = api.call('salt', {'username': api.username})
            if isinstance(salt, dict) and 'ses' in salt:
                return
        except (OSError, urllib.error.URLError):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError(
                'the UrBackup web API did not answer; is the container up?')
        time.sleep(5)


def wait_for_login(api, timeout=60):
    """Retry the login; a password reset takes a moment to become visible."""
    deadline = time.monotonic() + timeout
    while True:
        if api.login():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(3)


def configure():
    config = settings()
    password = (ROOT / 'secrets/urbackup_admin_password').read_text().strip()
    api = Api(f"http://127.0.0.1:{config.get('URBACKUP_WEB_PORT', 55414)}/x",
              'admin', password)
    wait_for_api(api)
    # A fresh server has no admin password and the volume may be empty, so try
    # the stored password first and only reset it when the server rejects it.
    if not wait_for_login(api):
        compose('exec', '-T', 'urbackup', 'urbackupsrv', 'reset-admin-pw', '-p', password)
        api = Api(api.base, 'admin', password)
        if not wait_for_login(api):
            raise RuntimeError('the server rejected the admin password after a reset')
    desired = json.loads((ROOT / 'settings.json').read_text())
    current = general_settings(api)
    changes = {key: value for key, value in desired.items()
               if current.get(key) != value}
    if not changes:
        print('OK: server settings already match settings.json')
        return
    result = api.call('settings', {'sa': 'general_save',
                                   **{key: str(value) for key, value in changes.items()}})
    if not isinstance(result, dict) or 'saved_ok' not in result:
        raise RuntimeError(f'the server rejected the settings: {result!r}')
    print('CHANGED: applied ' + ', '.join(sorted(changes)))


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
    # Cold snapshot: stop the server so the SQLite databases and the file
    # index are consistent. The backup client data lives on the bulk share and
    # is not part of this archive.
    try:
        compose('stop', '--timeout', '120')
        run(['tar', '--numeric-owner', '-cpf', str(target / 'state.tar'),
             '-C', str(storage), '.'])
        run(['tar', '--numeric-owner', '-cpf', str(target / 'deployment.tar'),
             'compose.yaml', 'compose.lock.yaml', '.env', '.env.example',
             'settings.json', 'manage.py'])
        (target / 'manifest.json').write_text(json.dumps({
            'storage_root': str(storage),
            'created_utc': stamp,
            'architecture': os.uname().machine,
            'format': 1,
            'notes': 'Cold backup of the UrBackup server state (database, settings, '
                     'identity keys) only. Device backups under CLIENT_BACKUP_ROOT '
                     'are the backup itself. Restore with the server stopped; keep '
                     'the admin password from secrets/urbackup_admin_password.',
        }, indent=2) + '\n')
    finally:
        if running:
            compose('start', *running)
    complete = target.with_suffix('')
    target.rename(complete)
    print(f'Backup complete: {complete}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'lock', 'up', 'configure',
                                           'status', 'down', 'backup'])
    parser.add_argument('--destination', default=str(ROOT / 'backups'))
    args = parser.parse_args()
    if args.action in ('init', 'up'):
        init()
    if args.action == 'lock':
        lock()
    elif args.action == 'up':
        up()
    elif args.action == 'configure':
        configure()
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
