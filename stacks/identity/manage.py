#!/usr/bin/env python3
"""Independent Authentik lifecycle on the identity VM. Run with sudo."""
import argparse
import datetime
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SECRETS = ('db_password', 'secret_key', 'bootstrap_password', 'bootstrap_token')


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, text=True, check=True, **kwargs)


def settings():
    return dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)


def secret(name):
    return (ROOT / 'secrets' / name).read_text().strip()


def compose(*args, locked=True, **kwargs):
    cmd = ['docker', 'compose', '--env-file', str(ROOT / '.env'), '-f', 'compose.yaml']
    if locked and (ROOT / 'compose.lock.yaml').exists():
        cmd += ['-f', 'compose.lock.yaml']
    # The bootstrap values only matter on the worker's first start, but compose
    # interpolates them on every call. Pass them from secrets/ so they never
    # land in .env or in the process list of another user.
    env = dict(os.environ, AUTHENTIK_BOOTSTRAP_PASSWORD=secret('bootstrap_password'),
               AUTHENTIK_BOOTSTRAP_TOKEN=secret('bootstrap_token'))
    return run(cmd + list(args), env=env, **kwargs)


def storage():
    path = (ROOT / settings().get('STORAGE_ROOT', './storage')).resolve()
    if path == ROOT or path in ROOT.parents:
        raise ValueError('STORAGE_ROOT must not contain the deployment directory')
    return path


def init():
    """Create .env, storage and secrets once. Never regenerate an existing secret."""
    changed = False
    if not (ROOT / '.env').exists():
        shutil.copyfile(ROOT / '.env.example', ROOT / '.env')
        changed = True
    (ROOT / '.env').chmod(0o600)
    for name in ('data', 'templates', 'postgres'):
        path = storage() / name
        if not path.exists():
            path.mkdir(parents=True, mode=0o750)
            changed = True
        if name != 'postgres' and path.stat().st_uid != 1000:
            # The server process runs as UID 1000 and writes media and templates here.
            os.chown(path, 1000, 1000)
            changed = True
    directory = ROOT / 'secrets'
    directory.mkdir(exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    for name in SECRETS:
        path = directory / name
        if not path.exists():
            with path.open('x') as file:
                file.write(secrets.token_urlsafe(48) + '\n')
            changed = True
        if not path.read_text().strip():
            raise ValueError(f'Empty secret: {name}')
        # Compose file secrets are bind mounts; the containers do not run as root.
        path.chmod(0o444 if name in ('db_password', 'secret_key') else 0o400)
    print('CHANGED: identity initialized' if changed else 'OK: identity already initialized')


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
            info = json.loads(run(['docker', 'image', 'inspect', service['image']], capture_output=True).stdout)[0]
            pinned[name] = {'image': info['RepoDigests'][0]}
    content = json.dumps({'services': pinned}, indent=2) + '\n'
    if path.exists() and path.read_text() == content:
        print('OK: identity digests preserved')
        return
    temporary = path.with_suffix('.tmp')
    temporary.write_text(content)
    temporary.replace(path)
    print('CHANGED: identity images pinned')


def configure():
    env = dict(os.environ, AUTHENTIK_TOKEN=secret('bootstrap_token'),
               CLOUD_PORTAL_URL=settings().get('CLOUD_PORTAL_URL', ''))
    run([sys.executable, str(ROOT / 'configure.py')], env=env)
    # Invitation-only enrollment is part of the identity service. The cloud API
    # and portal do not manage it; the identity administrator does.
    run([sys.executable, str(ROOT / 'invitations.py'), 'configure'], env=env)


def backup(destination):
    destination = Path(destination).resolve()
    source = storage()
    if destination == source or source in destination.parents:
        raise ValueError('Backup destination must be outside storage')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = destination / (stamp + '.incomplete')
    target.mkdir(mode=0o700)
    running = compose('ps', '--services', '--status', 'running', capture_output=True).stdout.split()
    try:
        compose('stop', '--timeout', '120')
        run(['tar', '--numeric-owner', '-cpf', str(target / 'state.tar'), '-C', str(source), '.'])
        run(['tar', '--numeric-owner', '-cpf', str(target / 'deployment.tar'),
             'compose.yaml', 'compose.lock.yaml', '.env', '.env.example', 'secrets',
             'manage.py', 'configure.py', 'invitations.py'])
    finally:
        if running:
            compose('start', *running)
    target.rename(target.with_suffix(''))
    print(f'Identity backup complete: {target.with_suffix("")}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['init', 'lock', 'up', 'configure', 'status', 'backup'])
    parser.add_argument('--refresh-images', action='store_true')
    parser.add_argument('--destination', default=str(ROOT / 'backups'))
    args = parser.parse_args()
    if args.action == 'init':
        init()
    elif args.action == 'lock':
        lock(args.refresh_images)
    elif args.action == 'up':
        if not (ROOT / 'compose.lock.yaml').exists():
            raise SystemExit('Run lock first')
        compose('up', '-d', '--remove-orphans', '--wait', '--wait-timeout', '900')
    elif args.action == 'configure':
        configure()
    elif args.action == 'status':
        compose('ps')
    else:
        backup(args.destination)


if __name__ == '__main__':
    main()
