#!/usr/bin/env python3
"""Minecraft lifecycle on shakeserver (Raspberry Pi 5). Run with sudo.

The world lives under STORAGE_ROOT/data. Secrets (RCON, the R2 backup keys and
the CurseForge API key) are installed into secrets/ by Ansible from SOPS and
handed to Compose as environment variables, so they never land in .env.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
# Installed by Ansible (platform/sops/minecraft.sops.yaml). Never generated here:
# the RCON password and the keys already exist outside this host.
SECRETS = {
    'mc_rcon_password': 'MC_RCON_PASSWORD',
    'cf_access_key': 'CF_ACCESS_KEY',
    'cf_secret_key': 'CF_SECRET_KEY',
    'cf_api_key': 'CF_API_KEY',
}


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, text=True, check=True, **kwargs)


def settings():
    return dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)


def secret(name):
    path = ROOT / 'secrets' / name
    return path.read_text().strip() if path.exists() else ''


def compose(*args, locked=True, **kwargs):
    cmd = ['docker', 'compose', '--env-file', str(ROOT / '.env'), '-f', 'compose.yaml']
    if locked and (ROOT / 'compose.lock.yaml').exists():
        cmd += ['-f', 'compose.lock.yaml']
    env = dict(os.environ, **{variable: secret(name) for name, variable in SECRETS.items()})
    return run(cmd + list(args), env=env, **kwargs)


def storage():
    path = Path(settings().get('STORAGE_ROOT', '/srv/minecraft')).resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('STORAGE_ROOT must not contain the deployment directory')
    return path


def init():
    """Create .env and the world directory. Refuse to start without the secrets."""
    changed = False
    if not (ROOT / '.env').exists():
        shutil.copyfile(ROOT / '.env.example', ROOT / '.env')
        changed = True
    (ROOT / '.env').chmod(0o600)
    data = storage() / 'data'
    if not data.exists():
        data.mkdir(parents=True, mode=0o750)
        values = settings()
        os.chown(data, int(values.get('MC_UID', '1000')), int(values.get('MC_GID', '1000')))
        changed = True
    missing = [name for name in SECRETS if not secret(name)]
    if missing:
        raise SystemExit(f'Missing secrets: {", ".join(missing)} (Ansible installs them from SOPS)')
    print('CHANGED: minecraft initialized' if changed else 'OK: minecraft already initialized')


def up():
    if not (ROOT / 'compose.lock.yaml').exists():
        raise SystemExit('compose.lock.yaml is missing')
    compose('up', '-d', '--remove-orphans')


def down():
    compose('down')


def backup(destination):
    """Cold copy of the world: the server stops while tar runs."""
    destination = Path(destination).resolve()
    source = storage() / 'data'
    if destination == source or source in destination.parents:
        raise ValueError('Backup destination must be outside storage')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target = destination / (stamp + '.incomplete')
    target.mkdir(mode=0o700)
    running = compose('ps', '--services', '--status', 'running', capture_output=True).stdout.split()
    try:
        compose('stop', '--timeout', '120')
        run(['tar', '--numeric-owner', '-czpf', str(target / 'world.tar.gz'), '-C', str(source), '.'])
        (target / 'manifest.json').write_text(json.dumps({
            'storage_root': str(source.parent), 'created_utc': stamp,
            'architecture': os.uname().machine, 'format': 1,
        }, indent=2) + '\n')
    finally:
        if running:
            compose('start', *running)
    target.rename(target.with_suffix(''))
    print(f'Minecraft backup complete: {target.with_suffix("")}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'up', 'down', 'status', 'backup'])
    parser.add_argument('--destination', default=str(ROOT / 'backups'))
    args = parser.parse_args()
    if args.action == 'init':
        init()
    elif args.action == 'up':
        up()
    elif args.action == 'down':
        down()
    elif args.action == 'status':
        compose('ps')
    else:
        backup(args.destination)


if __name__ == '__main__':
    main()
