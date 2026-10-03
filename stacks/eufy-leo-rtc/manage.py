#!/usr/bin/env python3
"""Manage the standalone Eufy leo_rtc live-stream container."""

import argparse
import json
import os
from pathlib import Path
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
    path = Path(config.get('STORAGE_ROOT', '/srv/eufy-leo-rtc')).resolve()
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
    environment.update(settings())
    return subprocess.run(
        command + list(args), cwd=ROOT, check=True, text=True,
        env=environment, capture_output=capture_output,
    )


def init():
    if not (ROOT / '.env').exists():
        (ROOT / '.env').write_text((ROOT / '.env.example').read_text(encoding='utf-8'), encoding='utf-8')
        (ROOT / '.env').chmod(0o600)
        print('CHANGED: created .env from the example (fill in the credentials)')
    storage = storage_path()
    for child in ('state',):
        (storage / child).mkdir(parents=True, exist_ok=True)
        print(f'OK: {storage / child}')


def lock():
    compose('config', '--quiet')
    services = compose('config', '--format', 'json', capture_output=True)
    names = list(json.loads(services.stdout)['services'])
    digests = {}
    for name in names:
        image = json.loads(services.stdout)['services'][name]['image']
        if image.endswith(':local'):
            continue
        inspected = subprocess.check_output(
            ['docker', 'image', 'inspect', image, '--format', '{{index .RepoDigests 0}}']).decode().strip()
        digests[name] = inspected
    lines = ['# manage.py lock が生成。更新は明示的に。', 'services:']
    for name, image in digests.items():
        lines += [f'  {name}:', f'    image: {image}']
    (ROOT / 'compose.lock.yaml').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('CHANGED: image digests pinned in compose.lock.yaml')


def up():
    init()
    compose('build', '--pull')
    compose('up', '-d', '--remove-orphans')
    print('OK: eufy-leo-rtc started')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'lock', 'up', 'status', 'down', 'restart', 'logs'])
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
    elif args.action == 'restart':
        compose('restart')
    elif args.action == 'logs':
        compose('logs', '--tail', '40')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
