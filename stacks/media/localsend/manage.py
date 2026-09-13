#!/usr/bin/env python3
"""Deploy the LocalSend receiver as an independent Compose project on media-01."""
import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTAINER_UID = 33
CONTAINER_GID = 33


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


def directories(config):
    """Return the host directories the receiver and Nextcloud share."""
    storage = Path(config.get('STORAGE_ROOT', '/srv/media-stack/storage'))
    library = Path(config.get('LIBRARY_ROOT', '/srv/media-stack/library'))
    return [
        (storage / 'localsend', None),
        (storage / 'localsend' / 'config', (CONTAINER_UID, CONTAINER_GID)),
        (storage / 'localsend' / 'data', (CONTAINER_UID, CONTAINER_GID)),
        # Nextcloud から music/books/docs へ移動できるよう、受信先も www-data に
        # 合わせる。root 所有のままだと Nextcloud の外部ストレージが操作できない。
        (library / 'inbox', (CONTAINER_UID, CONTAINER_GID)),
    ]


def init():
    env = ROOT / '.env'
    if not env.exists():
        env.write_bytes((ROOT / '.env.example').read_bytes())
    env.chmod(0o600)
    for path, owner in directories(settings()):
        if not path.exists():
            try:
                path.mkdir(parents=True, mode=0o750)
            except PermissionError as error:
                raise PermissionError(f'Run init with sudo to create {path}') from error
        if owner:
            if (path.stat().st_uid, path.stat().st_gid) != owner:
                if os.geteuid() != 0:
                    raise PermissionError(
                        f'Run init with sudo to own {path} as {owner[0]}:{owner[1]}')
                os.chown(path, *owner)
            path.chmod(0o2750)
    directory = ROOT / 'secrets'
    directory.mkdir(exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    pin = directory / 'localsend_pin'
    if not pin.exists():
        # LocalSend の PIN は短い数字。上流 1.0.10 は読まないが、対応版へ
        # 差し替えたときにそのまま使えるよう先に生成しておく。
        with pin.open('x') as handle:
            handle.write(f'{secrets.randbelow(1000000):06d}\n')
    if not pin.read_text().strip():
        raise ValueError(f'Empty secret file: {pin}')
    pin.chmod(0o444)
    print('OK: LocalSend directories and PIN secret are ready')


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'lock', 'up', 'status'])
    args = parser.parse_args()
    if args.action in ('init', 'up'):
        init()
    if args.action == 'lock':
        lock()
    elif args.action == 'up':
        up()
    elif args.action == 'status':
        compose('ps')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
