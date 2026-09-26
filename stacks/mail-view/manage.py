#!/usr/bin/env python3
"""Independent Gmail viewer lifecycle on services-01. Run with sudo.

The stack is mail-view alone. It holds no data: the mailbox stays on Gmail and
the page only reads it over IMAP. The app password is installed by the Ansible
role into secrets/imap_password and passed to Compose as an environment
variable, so it never lands in .env. There is nothing to back up: the mailbox
is Google's and the credentials are in platform/sops/.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
SECRETS = ('imap_password',)


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, text=True, check=True, **kwargs)


def secret(name):
    path = ROOT / 'secrets' / name
    return path.read_text().strip() if path.exists() else ''


def compose(*args, locked=True, **kwargs):
    cmd = ['docker', 'compose', '--env-file', str(ROOT / '.env'), '-f', 'compose.yaml']
    if locked and (ROOT / 'compose.lock.yaml').exists():
        cmd += ['-f', 'compose.lock.yaml']
    env = dict(os.environ, IMAP_PASSWORD=secret('imap_password'))
    return run(cmd + list(args), env=env, **kwargs)


def init():
    """Create .env and check the app password the Ansible role installed."""
    changed = False
    if not (ROOT / '.env').exists():
        shutil.copyfile(ROOT / '.env.example', ROOT / '.env')
        changed = True
    (ROOT / '.env').chmod(0o600)
    directory = ROOT / 'secrets'
    directory.mkdir(exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    for name in SECRETS:
        target = directory / name
        if not target.exists() or not target.read_text().strip():
            raise ValueError(f'Missing secret: {name}. '
                             'The Ansible role installs it from platform/sops/.')
        target.chmod(0o400)
    print('CHANGED: mail-view initialized' if changed else 'OK: mail-view already initialized')


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
        print('OK: mail-view digests preserved')
        return
    temporary = path.with_suffix('.tmp')
    temporary.write_text(content)
    temporary.replace(path)
    print('CHANGED: mail-view images pinned')


def up():
    if not (ROOT / 'compose.lock.yaml').exists():
        raise SystemExit('Run lock first')
    compose('up', '-d', '--remove-orphans', '--wait', '--wait-timeout', '120')


def restart():
    """Recreate the container so a changed app.py is loaded."""
    compose('up', '-d', '--force-recreate', '--remove-orphans', '--wait', '--wait-timeout', '120')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'lock', 'up', 'restart', 'status'])
    parser.add_argument('--refresh-images', action='store_true')
    args = parser.parse_args()
    if args.action == 'init':
        init()
    elif args.action == 'lock':
        lock(args.refresh_images)
    elif args.action == 'up':
        up()
    elif args.action == 'restart':
        restart()
    else:
        compose('ps')


if __name__ == '__main__':
    main()
