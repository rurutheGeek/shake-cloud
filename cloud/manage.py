#!/usr/bin/env python3
"""shake-cloud API lifecycle on cloud-01. Run with sudo."""
import argparse
import base64
import datetime
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
BOOTSTRAP_KEY = 'bootstrap_admin_key'
# Written by the cloud_api Ansible role from the identity VM, never generated here.
OIDC_CREDENTIALS = 'oidc_credentials'
# The postgres user in the official alpine image.
POSTGRES_UID = 70


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, text=True, check=True, **kwargs)


def settings():
    return dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)


def compose(*args, locked=True, **kwargs):
    cmd = ['docker', 'compose', '--env-file', str(ROOT / '.env'), '-f', 'compose.yaml']
    if locked and (ROOT / 'compose.lock.yaml').exists():
        cmd += ['-f', 'compose.lock.yaml']
    return run(cmd + list(args), **kwargs)


def storage():
    path = (ROOT / settings().get('STORAGE_ROOT', './storage')).resolve()
    if path == ROOT or path in ROOT.parents:
        raise ValueError('STORAGE_ROOT must not contain the deployment directory')
    return path


def bootstrap_key():
    """Mint an access key in the format of cloud/api/internal/accesskey."""
    key_id = base64.b32encode(secrets.token_bytes(12)).decode().rstrip('=').lower()
    secret = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')
    return f'sca_{key_id}.{secret}'


def write_secret(path, value):
    """Replace a secret atomically. Compose mounts single files, and the API runs
    as a non-root user, so the file is world-readable inside a 0700 directory."""
    temporary = path.with_name(path.name + '.tmp')
    temporary.unlink(missing_ok=True)
    with temporary.open('x') as file:
        file.write(value + '\n')
    temporary.chmod(0o444)
    temporary.replace(path)


def init():
    """Create .env, storage and secrets once. Never regenerate an existing secret."""
    changed = False
    if not (ROOT / '.env').exists():
        shutil.copyfile(ROOT / '.env.example', ROOT / '.env')
        changed = True
    (ROOT / '.env').chmod(0o600)
    path = storage() / 'postgres'
    if not path.exists():
        path.mkdir(parents=True, mode=0o750)
        changed = True
    if path.stat().st_uid != POSTGRES_UID:
        # PostgreSQL 18 keeps its data in <mount>/18/docker and creates that
        # directory after dropping to the postgres user, so the mount itself
        # must belong to that user; the entrypoint only fixes the leaf.
        os.chown(path, POSTGRES_UID, POSTGRES_UID)
        changed = True
    directory = ROOT / 'secrets'
    directory.mkdir(exist_ok=True, mode=0o700)
    directory.chmod(0o700)

    password = directory / 'db_password'
    if not password.exists():
        write_secret(password, secrets.token_urlsafe(48))
        changed = True
    if not password.read_text().strip():
        raise ValueError('Empty secret: db_password')

    # An empty key file is a deliberate "disabled" and must survive init.
    key = directory / BOOTSTRAP_KEY
    if not key.exists():
        write_secret(key, bootstrap_key())
        changed = True
    for path in (password, key):
        path.chmod(0o444)
    print('CHANGED: cloud initialized' if changed else 'OK: cloud already initialized')


def lock(refresh=False):
    """Pin pulled images. The API image is built here from pinned base images."""
    config = json.loads(compose('config', '--format', 'json', locked=False, capture_output=True).stdout)
    pulled = {name: service for name, service in config['services'].items() if 'build' not in service}
    path = ROOT / 'compose.lock.yaml'
    old = json.loads(path.read_text()).get('services', {}) if path.exists() else {}
    missing = [name for name in pulled if refresh or name not in old]
    if missing:
        compose('pull', *missing, locked=False)
    pinned = {}
    for name, service in pulled.items():
        if name in old and not refresh:
            pinned[name] = old[name]
        else:
            info = json.loads(run(['docker', 'image', 'inspect', service['image']], capture_output=True).stdout)[0]
            pinned[name] = {'image': info['RepoDigests'][0]}
    content = json.dumps({'services': pinned}, indent=2) + '\n'
    if path.exists() and path.read_text() == content:
        print('OK: cloud digests preserved')
        return
    temporary = path.with_suffix('.tmp')
    temporary.write_text(content)
    temporary.replace(path)
    print('CHANGED: cloud images pinned')


def up():
    if not (ROOT / 'compose.lock.yaml').exists():
        raise SystemExit('Run lock first')
    if not (ROOT / 'secrets' / OIDC_CREDENTIALS).exists():
        raise SystemExit('secrets/oidc_credentials is missing; deploy with platform/ansible/cloud.yml')
    compose('up', '-d', '--build', '--remove-orphans', '--wait', '--wait-timeout', '600')


def restart_api():
    # The key is read at startup, and a replaced file is a new inode the old
    # bind mount does not see, so recreate rather than restart.
    compose('up', '-d', '--no-deps', '--force-recreate', '--wait', '--wait-timeout', '120', 'api')


def rotate_bootstrap_key():
    write_secret(ROOT / 'secrets' / BOOTSTRAP_KEY, bootstrap_key())
    restart_api()
    print('CHANGED: bootstrap key rotated; the previous key is revoked')


def disable_bootstrap_key():
    write_secret(ROOT / 'secrets' / BOOTSTRAP_KEY, '')
    restart_api()
    print('CHANGED: bootstrap key disabled')


def backup(destination):
    """pg_dump runs against the live database, so the API stays up."""
    destination = Path(destination).resolve()
    if destination == storage() or storage() in destination.parents:
        raise ValueError('Backup destination must be outside storage')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = destination / (stamp + '.incomplete')
    target.mkdir(mode=0o700)
    with (target / 'shakecloud.dump').open('wb') as dump:
        subprocess.run(['docker', 'compose', '--env-file', str(ROOT / '.env'), '-f', 'compose.yaml',
                        'exec', '-T', 'postgres', 'pg_dump', '-U', 'shakecloud', '-Fc', 'shakecloud'],
                       cwd=ROOT, check=True, stdout=dump)
    run(['tar', '--numeric-owner', '-cpf', str(target / 'deployment.tar'),
         'compose.yaml', 'compose.lock.yaml', '.env', '.env.example', 'secrets', 'manage.py'])
    target.rename(target.with_suffix(''))
    print(f'Cloud backup complete: {target.with_suffix("")}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['init', 'lock', 'up', 'status', 'backup',
                                           'rotate-bootstrap-key', 'disable-bootstrap-key'])
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
    elif args.action == 'backup':
        backup(args.destination)
    elif args.action == 'rotate-bootstrap-key':
        rotate_bootstrap_key()
    else:
        disable_bootstrap_key()


if __name__ == '__main__':
    os.umask(0o077)
    main()
