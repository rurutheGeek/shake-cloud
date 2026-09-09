#!/usr/bin/env python3
"""Independent NetBox lifecycle. Run with sudo on a rootful Docker host."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import string
import subprocess

ROOT = Path(__file__).resolve().parent


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, text=True, check=True, **kwargs)


def settings():
    return dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines()
                if line and not line.startswith('#'))


def compose(*args, locked=True, extra_env=None, **kwargs):
    cmd = ['docker', 'compose', '--env-file', str(ROOT / '.env'), '-f', 'compose.yaml']
    if (ROOT / 'compose.sso.yaml').exists():
        cmd += ['-f', 'compose.sso.yaml']
    if locked and (ROOT / 'compose.lock.yaml').exists():
        cmd += ['-f', 'compose.lock.yaml']
    code_hash=hashlib.sha256((ROOT/'configuration/configuration.py').read_bytes()).hexdigest()
    return run(cmd + list(args), env=dict(os.environ, **settings(), **(extra_env or {}), NETBOX_CONFIG_SHA=code_hash), **kwargs)


def storage():
    path = (ROOT / settings().get('STORAGE_ROOT', './storage')).resolve()
    if path == ROOT or path in ROOT.parents:
        raise ValueError('STORAGE_ROOT must not contain the deployment directory')
    return path


def init():
    changed = False
    if not (ROOT / '.env').exists():
        shutil.copyfile(ROOT / '.env.example', ROOT / '.env')
        changed = True
    (ROOT / '.env').chmod(0o600)
    for name in ('media', 'reports', 'scripts', 'postgres', 'queue'):
        path = storage() / name
        if not path.exists():
            path.mkdir(parents=True, mode=0o770)
            changed = True
        if name in ('media', 'reports', 'scripts'):
            # Official netbox:root process writes through its root group.
            if path.stat().st_gid != 0:
                os.chown(path, -1, 0)
                changed = True
            path.chmod(0o2770)
        elif name == 'postgres':
            # PostgreSQL 18 keeps PGDATA below this mount, and chowns PGDATA
            # rather than the mount root. Its UID must traverse this parent.
            path.chmod(0o755)
    directory = ROOT / 'secrets'
    directory.mkdir(exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    for name in ('db_password', 'secret_key', 'api_token_pepper_1', 'superuser_password'):
        path = directory / name
        if not path.exists():
            with path.open('x') as file:
                file.write(secrets.token_urlsafe(48) + '\n')
            changed = True
        if not path.read_text().strip():
            raise ValueError(f'Empty secret: {name}')
        path.chmod(0o444)
    print('CHANGED: NetBox initialized' if changed else 'OK: NetBox already initialized')


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
        print('OK: NetBox digests preserved')
        return
    temporary = path.with_suffix('.tmp')
    temporary.write_text(content)
    temporary.replace(path)
    print('CHANGED: NetBox images pinned')


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
             'compose.yaml', 'compose.lock.yaml', '.env', '.env.example', 'configuration', 'secrets',
             'manage.py', 'seed_inventory.py', 'seed_terraform_identity.py'])
    finally:
        if running:
            compose('start', *running)
    target.rename(target.with_suffix(''))
    print(f'NetBox backup complete: {target.with_suffix("")}')


def seed(name, address):
    import ipaddress
    ipaddress.IPv4Interface(address)
    if not name:
        raise ValueError('A host name is required')
    path = ROOT / 'secrets' / 'inventory-token.json'
    if not path.exists():
        alphabet = string.ascii_letters + string.digits
        credential = {'key': ''.join(secrets.choice(alphabet) for _ in range(12)),
                      'token': ''.join(secrets.choice(alphabet) for _ in range(40))}
        with path.open('x') as file:
            json.dump(credential, file)
        path.chmod(0o600)
    credential = json.loads(path.read_text())
    compose('exec', '-T', '-e', 'SEED_HOST', '-e', 'SEED_CREDENTIAL', 'netbox',
            '/opt/netbox/venv/bin/python', '/opt/netbox/netbox/manage.py',
            'shell', '--no-startup', '--no-imports', '--interface', 'python',
            extra_env={'SEED_HOST': json.dumps({'name': name, 'address': address}),
                       'SEED_CREDENTIAL': json.dumps(credential)},
            input=(ROOT / 'seed_inventory.py').read_text(encoding='utf-8'))
    print('API credential is saved under secrets/inventory-token.json')


def seed_terraform():
    """Create the write-enabled identity Terraform uses for the NetBox ledger."""
    path = ROOT / 'secrets' / 'terraform-token.json'
    if not path.exists():
        alphabet = string.ascii_letters + string.digits
        credential = {'key': ''.join(secrets.choice(alphabet) for _ in range(12)),
                      'token': ''.join(secrets.choice(alphabet) for _ in range(40))}
        with path.open('x') as file:
            json.dump(credential, file)
        path.chmod(0o600)
    credential = json.loads(path.read_text())
    compose('exec', '-T', '-e', 'SEED_CREDENTIAL', 'netbox',
            '/opt/netbox/venv/bin/python', '/opt/netbox/netbox/manage.py',
            'shell', '--no-startup', '--no-imports', '--interface', 'python',
            extra_env={'SEED_CREDENTIAL': json.dumps(credential)},
            input=(ROOT / 'seed_terraform_identity.py').read_text(encoding='utf-8'))
    print('Write credential is saved under secrets/terraform-token.json')
    print('NETBOX_API_TOKEN is nbt_<key>.<token> built from that file')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'lock', 'up', 'status', 'backup', 'seed', 'seed-terraform'])
    parser.add_argument('--refresh-images', action='store_true')
    parser.add_argument('--destination', default=str(ROOT / 'backups'))
    parser.add_argument('--host-name')
    parser.add_argument('--host-address')
    args = parser.parse_args()
    if args.action == 'seed':
        seed(args.host_name, args.host_address)
    elif args.action == 'seed-terraform':
        seed_terraform()
    elif args.action == 'init':
        init()
    elif args.action == 'lock':
        lock(args.refresh_images)
    elif args.action == 'up':
        if not (ROOT / 'compose.lock.yaml').exists():
            raise SystemExit('Run lock first')
        compose('up', '-d', '--remove-orphans', '--wait', '--wait-timeout', '1200')
    elif args.action == 'status':
        compose('ps')
    else:
        backup(args.destination)
