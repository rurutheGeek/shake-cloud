#!/usr/bin/env python3
"""Manage the isolated RomM library on game1."""
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
SECRET_NAMES = ('db_password', 'db_root_password', 'auth_secret_key')


def settings():
    values = {}
    for line in (ROOT / '.env').read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if not separator or not key.replace('_', '').isalnum():
            raise ValueError('Invalid .env line; use KEY=literal_value')
        values[key] = value
    return values


def state_path(config=None):
    config = settings() if config is None else config
    path = Path(config.get('STORAGE_ROOT', '/srv/game1/romm')).resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('STORAGE_ROOT must be outside the project directory')
    return path


def library_path(config=None):
    config = settings() if config is None else config
    path = Path(config.get('ROM_LIBRARY_ROOT', '/srv/game1/games')).resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('ROM_LIBRARY_ROOT must be outside the project directory')
    return path


def secret(name):
    path = ROOT / 'secrets' / name
    return path.read_text(encoding='utf-8').strip() if path.exists() else ''


def compose(*args, locked=True, capture_output=False):
    command = [
        'docker', 'compose', '--env-file', str(ROOT / '.env'),
        '-f', str(ROOT / 'compose.yaml'),
    ]
    if locked and (ROOT / 'compose.lock.yaml').exists():
        command += ['-f', str(ROOT / 'compose.lock.yaml')]
    environment = dict(os.environ)
    environment.update(settings())
    environment.update({
        'ROMM_DB_PASSWORD': secret('db_password'),
        'ROMM_DB_ROOT_PASSWORD': secret('db_root_password'),
        'ROMM_AUTH_SECRET_KEY': secret('auth_secret_key'),
    })
    return subprocess.run(
        command + list(args), cwd=ROOT, check=True, text=True,
        env=environment, capture_output=capture_output,
    )


def run(args):
    return subprocess.run(args, cwd=ROOT, check=True)


def init():
    env = ROOT / '.env'
    if not env.exists():
        shutil.copyfile(ROOT / '.env.example', env)
    env.chmod(0o600)
    state = state_path(settings())
    library = library_path(settings())
    if state == library or state in library.parents or library in state.parents:
        raise ValueError('ROM_LIBRARY_ROOT and STORAGE_ROOT must be separate')
    for name in ('mysql', 'resources', 'redis', 'assets'):
        (state / name).mkdir(parents=True, mode=0o750, exist_ok=True)
    directory = ROOT / 'secrets'
    directory.mkdir(mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    for name in SECRET_NAMES:
        target = directory / name
        if not target.exists():
            target.write_text(secrets.token_urlsafe(48) + '\n', encoding='utf-8')
        if not target.read_text(encoding='utf-8').strip():
            raise ValueError(f'Empty secret file: {target}')
        target.chmod(0o400)
    print(f'OK: RomM state and secrets are ready: {state}')


def lock():
    lockfile = ROOT / 'compose.lock.yaml'
    if lockfile.exists():
        print('OK: existing image digests preserved')
        return
    compose('pull', locked=False)
    rendered = json.loads(compose(
        'config', '--format', 'json', locked=False, capture_output=True,
    ).stdout)
    services = {}
    for name, service in rendered['services'].items():
        inspected = json.loads(subprocess.check_output(
            ['docker', 'image', 'inspect', service['image']], text=True,
        ))[0]
        digests = inspected.get('RepoDigests', [])
        if not digests:
            raise RuntimeError(f'Image has no repository digest: {name}')
        services[name] = {'image': digests[0]}
    lockfile.write_text(json.dumps({'services': services}, indent=2) + '\n', encoding='utf-8')
    print('CHANGED: image digests pinned in compose.lock.yaml')


def up():
    init()
    library = library_path(settings())
    if not library.is_dir():
        raise FileNotFoundError(f'ROM_LIBRARY_ROOT does not exist: {library}')
    lock()
    compose('config', '--quiet')
    compose('up', '-d', '--remove-orphans', '--wait', '--wait-timeout', '240')


def backup(destination):
    if os.geteuid() != 0:
        raise PermissionError('Run backup with sudo to read RomM state')
    state = state_path(settings())
    destination = Path(destination).resolve()
    if destination == state or state in destination.parents:
        raise ValueError('Backup destination must be outside STORAGE_ROOT')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.chmod(0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = destination / f'{stamp}.incomplete'
    target.mkdir(mode=0o700)
    running = compose('ps', '--services', '--status', 'running', capture_output=True).stdout.split()
    try:
        compose('stop', '--timeout', '120')
        run(['tar', '--numeric-owner', '-cpf', str(target / 'state.tar'),
             '-C', str(state), '.'])
        run(['tar', '--numeric-owner', '-cpf', str(target / 'deployment.tar'),
             'compose.yaml', '.env', '.env.example', 'manage.py', 'secrets'])
        (target / 'manifest.json').write_text(json.dumps({
            'storage_root': str(state),
            'created_utc': stamp,
            'architecture': os.uname().machine,
            'format': 1,
            'notes': 'Cold backup of RomM database, metadata and deployment files. '
                     'ROM originals are external and are not included.',
        }, indent=2) + '\n', encoding='utf-8')
    finally:
        if running:
            compose('start', *running)
    target.rename(target.with_suffix(''))
    print(f'Backup complete: {target.with_suffix("")}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'lock', 'up', 'status', 'down', 'backup'])
    parser.add_argument('--destination', default=str(ROOT / 'backups'))
    args = parser.parse_args()
    if args.action == 'init':
        init()
    elif args.action == 'lock':
        lock()
    elif args.action == 'up':
        up()
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
