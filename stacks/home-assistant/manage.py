#!/usr/bin/env python3
"""Manage the isolated Home Assistant Container project."""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile


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
    path = Path(config.get('STORAGE_ROOT', '/srv/services/home-assistant')).resolve()
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


def run(args):
    return subprocess.run(args, cwd=ROOT, check=True)


def init():
    env = ROOT / '.env'
    if not env.exists():
        shutil.copyfile(ROOT / '.env.example', env)
    env.chmod(0o600)
    config_dir = storage_path(settings()) / 'config'
    config_dir.mkdir(parents=True, mode=0o750, exist_ok=True)
    config_dir.chmod(0o750)
    print(f'OK: Home Assistant config directory is ready: {config_dir}')


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


def ensure_http_proxy(proxy):
    """Trust the local reverse proxy in Home Assistant's HTTP config store.

    Home Assistant 2026.9 moved the HTTP settings out of configuration.yaml
    into .storage/http, where a YAML import becomes an unconfirmed ``pending``
    config that auto-reverts after five minutes unless the UI promotes it.
    Deployments cannot click that button, so write the setting into ``stable``
    and drop the trial.  Returns True when the store changed.
    """
    store = storage_path(settings()) / 'config' / '.storage' / 'http'
    if not store.exists():
        raise FileNotFoundError(
            f'{store} is missing; start Home Assistant once before setting the proxy')
    document = json.loads(store.read_text(encoding='utf-8'))
    data = document['data']
    stable = data['stable']
    wanted = {'use_x_forwarded_for': True, 'trusted_proxies': [proxy]}
    if (data.get('pending') is None
            and all(stable.get(key) == value for key, value in wanted.items())):
        print('OK: Home Assistant trusts the reverse proxy')
        return False
    stable.update(wanted)
    stable['error'] = None
    stable['error_message'] = None
    data['pending'] = None
    data['yaml_migration_done'] = True
    store.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
    store.chmod(0o600)
    print('CHANGED: Home Assistant HTTP config now trusts the reverse proxy')
    return True


def restart():
    compose('restart', 'homeassistant')
    compose('up', '-d', '--wait', '--wait-timeout', '180')


def extract_archive(archive, member, destination):
    """Unpack a zip or tar archive and return the directory holding the code."""
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(destination)
    else:
        with tarfile.open(archive) as bundle:
            bundle.extractall(destination, filter='data')
    source = destination / member if member else destination
    if not source.is_dir():
        raise RuntimeError(f'member {member or "."} is not a directory in {archive.name}')
    return source


def install_integration(name, url, sha256, member=''):
    """Install a pinned custom integration into the Home Assistant config.

    The archive is downloaded over HTTPS, checked against the recorded digest,
    unpacked into ``custom_components/<name>`` and marked with that digest so a
    repeated deploy is a no-op.  Nothing is replaced until the archive passed
    the check, so a bad download cannot leave a half-installed component.
    """
    if not re.fullmatch(r'[a-z0-9_]+', name):
        raise ValueError('integration name must match [a-z0-9_]+')
    if not url.startswith('https://'):
        raise ValueError('integration URL must use https')
    if not re.fullmatch(r'[0-9a-f]{64}', sha256):
        raise ValueError('sha256 must be 64 lowercase hex characters')
    components = storage_path(settings()) / 'config' / 'custom_components'
    target = components / name
    marker = components / f'.{name}.sha256'
    if (marker.exists() and target.is_dir()
            and marker.read_text(encoding='utf-8').strip() == sha256):
        print(f'OK: integration {name} is already at {sha256[:12]}')
        return False
    with urllib.request.urlopen(url, timeout=120) as response:
        payload = response.read()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != sha256:
        raise RuntimeError(f'{name}: sha256 mismatch: got {digest}')
    components.mkdir(parents=True, exist_ok=True, mode=0o750)
    with tempfile.TemporaryDirectory() as work:
        archive = Path(work) / 'archive'
        archive.write_bytes(payload)
        extracted = Path(work) / 'extract'
        extracted.mkdir()
        source = extract_archive(archive, member, extracted)
        staging = components / f'.{name}.staging'
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(source, staging)
    shutil.rmtree(target, ignore_errors=True)
    staging.rename(target)
    marker.write_text(sha256 + '\n', encoding='utf-8')
    marker.chmod(0o644)
    print(f'CHANGED: installed integration {name} at {sha256[:12]}')
    return True


def backup(destination):
    """Cold-backup config and deployment files without copying host secrets elsewhere."""
    if os.geteuid() != 0:
        raise PermissionError('Run backup with sudo to read Home Assistant state')
    state = storage_path(settings())
    destination = Path(destination).resolve()
    if destination == state or state in destination.parents:
        raise ValueError('Backup destination must be outside STORAGE_ROOT')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.chmod(0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = destination / f'{stamp}.incomplete'
    target.mkdir(mode=0o700)
    running = compose(
        'ps', '--services', '--status', 'running', capture_output=True,
    ).stdout.split()
    try:
        compose('stop', '--timeout', '120')
        run(['tar', '--numeric-owner', '-cpf', str(target / 'state.tar'),
             '-C', str(state), '.'])
        run(['tar', '--numeric-owner', '-cpf', str(target / 'deployment.tar'),
             'compose.yaml', 'compose.lock.yaml', '.env', '.env.example', 'manage.py'])
        (target / 'manifest.json').write_text(json.dumps({
            'storage_root': str(state),
            'created_utc': stamp,
            'architecture': os.uname().machine,
            'format': 1,
            'notes': 'Cold backup of Home Assistant config and deployment files. '
                     'The image cache and external device state are not included. '
                     'Restore into a new or empty directory with the service stopped.',
        }, indent=2) + '\n', encoding='utf-8')
    finally:
        if running:
            compose('start', *running)
    target.rename(target.with_suffix(''))
    print(f'Backup complete: {target.with_suffix("")}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=[
        'init', 'lock', 'up', 'status', 'down', 'backup', 'restart',
        'ensure-http-proxy', 'install-integration'])
    parser.add_argument('--destination', default=str(ROOT / 'backups'))
    parser.add_argument('--proxy', default='')
    parser.add_argument('--name', default='')
    parser.add_argument('--url', default='')
    parser.add_argument('--sha256', default='')
    parser.add_argument('--member', default='')
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
    elif args.action == 'restart':
        restart()
    elif args.action == 'ensure-http-proxy':
        if not args.proxy:
            raise ValueError('ensure-http-proxy requires --proxy')
        if ensure_http_proxy(args.proxy):
            restart()
    elif args.action == 'install-integration':
        if not all([args.name, args.url, args.sha256]):
            raise ValueError('install-integration requires --name, --url and --sha256')
        if install_integration(args.name, args.url, args.sha256, args.member):
            restart()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
