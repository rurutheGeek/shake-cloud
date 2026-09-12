#!/usr/bin/env python3
"""Independent Vaultwarden lifecycle on services-01. Run with sudo.

The stack is Vaultwarden alone: no old media-hub database, no docs site, no
other service's storage. The admin token is generated here; the OIDC client
secret is copied from the identity stack by the Ansible role and passed to
Compose as an environment variable, so it never lands in .env.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
# Generated on this VM. The OIDC client file is copied from the identity stack
# by the Ansible role and is JSON ({client_id, client_secret}).
GENERATED_SECRETS = ('admin_token',)
OIDC_SECRET_FILE = 'oidc_client.json'
STORAGE_DIRECTORY = 'data'


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, text=True, check=True, **kwargs)


def settings():
    return dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)


def secret(name):
    path = ROOT / 'secrets' / name
    return path.read_text().strip() if path.exists() else ''


def oidc_client():
    path = ROOT / 'secrets' / OIDC_SECRET_FILE
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text())
    return loaded if isinstance(loaded, dict) else {}


def compose(*args, locked=True, **kwargs):
    cmd = ['docker', 'compose', '--env-file', str(ROOT / '.env'), '-f', 'compose.yaml']
    if locked and (ROOT / 'compose.lock.yaml').exists():
        cmd += ['-f', 'compose.lock.yaml']
    client = oidc_client()
    env = dict(os.environ,
               SSO_CLIENT_ID=client.get('client_id', 'vaultwarden'),
               SSO_CLIENT_SECRET=client.get('client_secret', ''))
    return run(cmd + list(args), env=env, **kwargs)


def storage():
    configured = Path(settings().get('STORAGE_ROOT', '/srv/services/vaultwarden'))
    path = configured.resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('STORAGE_ROOT must not contain the deployment directory')
    return path


def init():
    """Create .env, storage and the admin token once. Never regenerate it."""
    changed = False
    if not (ROOT / '.env').exists():
        shutil.copyfile(ROOT / '.env.example', ROOT / '.env')
        changed = True
    (ROOT / '.env').chmod(0o600)
    path = storage() / STORAGE_DIRECTORY
    if not path.exists():
        path.mkdir(parents=True, mode=0o750)
        changed = True
    directory = ROOT / 'secrets'
    directory.mkdir(exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    for name in GENERATED_SECRETS:
        target = directory / name
        if not target.exists():
            with target.open('x') as file:
                file.write(secrets.token_urlsafe(48) + '\n')
            changed = True
        if not target.read_text().strip():
            raise ValueError(f'Empty secret: {name}')
        target.chmod(0o400)
    print('CHANGED: vaultwarden initialized' if changed else 'OK: vaultwarden already initialized')


def lock(refresh=False):
    config = json.loads(compose('config', '--format', 'json', locked=False, capture_output=True).stdout)
    path = ROOT / 'compose.lock.yaml'
    old = json.loads(path.read_text()).get('services', {}) if path.exists() else {}
    missing = [name for name in config['services'] if refresh or name not in old]
    if missing:
        compose('pull', *missing, locked=False)
    pinned = {}
    for name, service in config['services'].items():
        if name in old and not refresh:
            pinned[name] = old[name]
        else:
            info = json.loads(run(['docker', 'image', 'inspect', service['image']],
                                  capture_output=True).stdout)[0]
            pinned[name] = {'image': info['RepoDigests'][0]}
    content = json.dumps({'services': pinned}, indent=2) + '\n'
    if path.exists() and path.read_text() == content:
        print('OK: vaultwarden digests preserved')
        return
    temporary = path.with_suffix('.tmp')
    temporary.write_text(content)
    temporary.replace(path)
    print('CHANGED: vaultwarden images pinned')


def up():
    if not (ROOT / 'compose.lock.yaml').exists():
        raise SystemExit('Run lock first')
    compose('up', '-d', '--remove-orphans', '--wait', '--wait-timeout', '300')


def backup(destination):
    destination = Path(destination).resolve()
    source = storage() / STORAGE_DIRECTORY
    if destination == source or source in destination.parents:
        raise ValueError('Backup destination must be outside storage')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.chmod(0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = destination / (stamp + '.incomplete')
    target.mkdir(mode=0o700)
    running = compose('ps', '--services', '--status', 'running', capture_output=True).stdout.split()
    try:
        compose('stop', '--timeout', '120')
        run(['tar', '--numeric-owner', '-cpf', str(target / 'state.tar'), '-C', str(source), '.'])
        run(['tar', '--numeric-owner', '-cpf', str(target / 'deployment.tar'),
             'compose.yaml', 'compose.lock.yaml', '.env', '.env.example', 'manage.py', 'secrets'])
        (target / 'manifest.json').write_text(json.dumps({
            'storage_root': str(source),
            'created_utc': stamp,
            'architecture': os.uname().machine,
            'format': 1,
            'notes': 'Cold Vaultwarden data and deployment backup. The master password '
                     'and vault encryption keys are not part of SSO. Restore only into '
                     'a new or empty directory with the service stopped.',
        }, indent=2) + '\n')
    finally:
        if running:
            compose('start', *running)
    target.rename(target.with_suffix(''))
    print(f'Vaultwarden backup complete: {target.with_suffix("")}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'lock', 'up', 'status', 'backup'])
    parser.add_argument('--refresh-images', action='store_true')
    parser.add_argument('--destination', default=str(ROOT / 'backups'))
    args = parser.parse_args()
    if args.action == 'init':
        init()
    elif args.action == 'lock':
        lock(args.refresh_images)
    elif args.action == 'up':
        up()
    elif args.action == 'status':
        compose('ps')
    else:
        backup(args.destination)


if __name__ == '__main__':
    main()
