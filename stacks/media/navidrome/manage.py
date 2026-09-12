#!/usr/bin/env python3
"""Deploy Navidrome as an independent Compose project on media-01."""
import argparse
import datetime
import json
import os
import subprocess
import sys
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
    """Return the Navidrome state directory that a cold backup archives."""
    config = settings()
    return Path(config.get('STORAGE_ROOT', '/srv/media-stack/storage')) / 'navidrome'


def run(args):
    return subprocess.run(args, cwd=ROOT, check=True)


def init():
    env = ROOT / '.env'
    if not env.exists():
        env.write_bytes((ROOT / '.env.example').read_bytes())
    env.chmod(0o600)
    config = settings()
    uid = int(config.get('MEDIA_UID', 33))
    gid = int(config.get('MEDIA_GID', 33))
    storage = Path(config.get('STORAGE_ROOT', '/srv/media-stack/storage')) / 'navidrome'
    music = Path(config.get('LIBRARY_ROOT', '/srv/media-stack/library')) / 'music'
    for path in (storage, music):
        created = not path.exists()
        if created:
            path.mkdir(parents=True, mode=0o750)
        if (path.stat().st_uid, path.stat().st_gid) != (uid, gid):
            if os.geteuid() != 0:
                raise PermissionError(f'Run init with sudo to own {path} as {uid}:{gid}')
            os.chown(path, uid, gid)
    print('OK: Navidrome data and music directories are ready')


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
    compose('up', '-d', '--wait', '--wait-timeout', '120')


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
    # Cold snapshot: the Navidrome database is cleanly stopped before copying.
    # Finally restores only services that were running on entry, even on tar failure.
    try:
        compose('stop', '--timeout', '120')
        run(['tar', '--numeric-owner', '-cpf', str(target / 'state.tar'),
             '-C', str(storage), '.'])
        run(['tar', '--numeric-owner', '-cpf', str(target / 'deployment.tar'),
             'compose.yaml', 'compose.lock.yaml', '.env', '.env.example', 'manage.py'])
        (target / 'manifest.json').write_text(json.dumps({
            'storage_root': str(storage),
            'created_utc': stamp,
            'architecture': os.uname().machine,
            'format': 1,
            'notes': 'Cold backup of Navidrome state only (database, users, playlists); '
                     'the music library is not included. Restore on the same CPU '
                     'architecture, with services stopped, into a new or empty directory; '
                     'do not overwrite a live one.',
        }, indent=2) + '\n')
    finally:
        if running:
            compose('start', *running)
    complete = target.with_suffix('')
    target.rename(complete)
    print(f'Backup complete: {complete}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'lock', 'up', 'status', 'down', 'backup'])
    parser.add_argument('--destination', default=str(ROOT / 'backups'))
    args = parser.parse_args()
    if args.action in ('init', 'up'):
        init()
    if args.action == 'lock':
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
