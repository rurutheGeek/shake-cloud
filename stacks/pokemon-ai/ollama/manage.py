#!/usr/bin/env python3
"""Manage the shared Ollama service on game1.

Model downloads are deliberately explicit (``docker compose exec`` or the
``pull`` action); starting the stack never fetches a model or changes a
previously pinned image.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


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


def storage_path(config=None):
    config = settings() if config is None else config
    path = Path(config.get('STORAGE_ROOT', '/srv/game1/ollama')).resolve()
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


def run(args):
    return subprocess.run(args, cwd=ROOT, check=True)


def ensure_network():
    """Create the shared network once, without letting Compose own its labels."""
    found = subprocess.run(
        ['docker', 'network', 'inspect', 'game1-ai'],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if found.returncode:
        run(['docker', 'network', 'create', '--driver', 'bridge', 'game1-ai'])


def init():
    env = ROOT / '.env'
    if not env.exists():
        shutil.copyfile(ROOT / '.env.example', env)
    env.chmod(0o600)
    models = storage_path(settings()) / 'models'
    models.mkdir(parents=True, mode=0o750, exist_ok=True)
    models.chmod(0o750)
    print(f'OK: Ollama model directory is ready: {models}')


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
    ensure_network()
    lock()
    compose('config', '--quiet')
    compose('up', '-d', '--remove-orphans', '--wait', '--wait-timeout', '180')


def pull(model):
    """Download exactly one explicitly requested model."""
    if not model or any(char.isspace() for char in model):
        raise ValueError('model must be one Ollama model identifier')
    compose('exec', '-T', 'ollama', 'ollama', 'pull', model)


def backup(destination):
    if os.geteuid() != 0:
        raise PermissionError('Run backup with sudo to read Ollama model state')
    state = storage_path(settings())
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
             'compose.yaml', '.env', '.env.example', 'manage.py'])
        (target / 'manifest.json').write_text(json.dumps({
            'storage_root': str(state),
            'created_utc': stamp,
            'architecture': os.uname().machine,
            'format': 1,
            'notes': 'Cold backup of Ollama model cache and deployment files. '
                     'Model manifests are included; model downloads can be repeated '
                     'after restore if a layer is missing.',
        }, indent=2) + '\n', encoding='utf-8')
    finally:
        if running:
            compose('start', *running)
    target.rename(target.with_suffix(''))
    print(f'Backup complete: {target.with_suffix("")}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'lock', 'up', 'status', 'down', 'pull', 'backup'])
    parser.add_argument('model', nargs='?')
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
    elif args.action == 'pull':
        if args.model is None:
            parser.error('pull requires a model identifier')
        pull(args.model)
    elif args.action == 'backup':
        backup(args.destination)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
