#!/usr/bin/env python3
"""Manage the isolated eufy-security-ws project."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def settings():
    """Read literal KEY=value settings from the deployment .env."""
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


def storage_path(config=None):
    config = settings() if config is None else config
    path = Path(config.get('STORAGE_ROOT', '/srv/services/eufy-security-ws')).resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('STORAGE_ROOT must be outside the project directory')
    return path


def compose(*args, locked=True, capture_output=False):
    command = [
        'docker', 'compose', '--env-file', str(ROOT / '.env'),
        '-f', str(ROOT / 'compose.yaml'),
    ]
    if locked and (ROOT / 'compose.lock.yaml').exists():
        command += ['-f', str(ROOT / 'compose.lock.yaml')]
    environment = dict(os.environ)
    # Compose interpolation must use the checked-in deployment file, not an
    # accidental value inherited from an operator's shell.
    environment.update(settings())
    return subprocess.run(
        command + list(args), cwd=ROOT, check=True, text=True,
        env=environment, capture_output=capture_output,
    )


def init():
    env = ROOT / '.env'
    if not env.exists():
        shutil.copyfile(ROOT / '.env.example', env)
    env.chmod(0o600)
    data_dir = storage_path(settings()) / 'data'
    data_dir.mkdir(parents=True, mode=0o750, exist_ok=True)
    data_dir.chmod(0o750)
    print(f'OK: eufy-security-ws data directory is ready: {data_dir}')


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
    lock()
    compose('config', '--quiet')
    compose('up', '-d', '--remove-orphans', '--wait', '--wait-timeout', '180')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'lock', 'up', 'status', 'down'])
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


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
