#!/usr/bin/env python3
"""Independent Homarr lifecycle on services-01. Run with sudo.

The stack is Homarr alone: no Authentik database, no docs site, no other
service's storage. Secrets are generated here and passed to Compose as
environment variables, so they never land in .env.
"""
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
# Generated on this VM. The OIDC client file is copied from the identity stack
# by the Ansible role and is JSON ({client_id, client_secret}).
GENERATED_SECRETS = ('secret_encryption_key', 'admin_password')
OIDC_SECRET_FILE = 'oidc_client.json'


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, text=True, check=True, **kwargs)


def settings():
    return dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)


def secret(name):
    path = ROOT / 'secrets' / name
    return path.read_text().strip() if path.exists() else ''


def oidc_client_secret():
    path = ROOT / 'secrets' / OIDC_SECRET_FILE
    if not path.exists():
        return ''
    return json.loads(path.read_text()).get('client_secret', '')


def compose(*args, locked=True, **kwargs):
    cmd = ['docker', 'compose', '--env-file', str(ROOT / '.env'), '-f', 'compose.yaml']
    if locked and (ROOT / 'compose.lock.yaml').exists():
        cmd += ['-f', 'compose.lock.yaml']
    env = dict(os.environ, SECRET_ENCRYPTION_KEY=secret('secret_encryption_key'),
               AUTH_OIDC_CLIENT_SECRET=oidc_client_secret())
    return run(cmd + list(args), env=env, **kwargs)


def storage():
    configured = Path(settings().get('STORAGE_ROOT', '/srv/services/homarr'))
    path = configured.resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('STORAGE_ROOT must not contain the deployment directory')
    return path


def init():
    """Create .env, storage and secrets once. Never regenerate an existing secret."""
    changed = False
    if not (ROOT / '.env').exists():
        shutil.copyfile(ROOT / '.env.example', ROOT / '.env')
        changed = True
    (ROOT / '.env').chmod(0o600)
    path = storage() / 'homarr'
    if not path.exists():
        path.mkdir(parents=True, mode=0o750)
        changed = True
    if path.stat().st_uid != 1000:
        # The container runs as the non-root nextjs user (UID 1000).
        os.chown(path, 1000, 1000)
        changed = True
    directory = ROOT / 'secrets'
    directory.mkdir(exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    for name in GENERATED_SECRETS:
        target = directory / name
        if not target.exists():
            value = secrets.token_hex(32) if name == 'secret_encryption_key' else secrets.token_urlsafe(24)
            with target.open('x') as file:
                file.write(value + '\n')
            changed = True
        if not target.read_text().strip():
            raise ValueError(f'Empty secret: {name}')
        target.chmod(0o400)
    print('CHANGED: homarr initialized' if changed else 'OK: homarr already initialized')


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
        print('OK: homarr digests preserved')
        return
    temporary = path.with_suffix('.tmp')
    temporary.write_text(content)
    temporary.replace(path)
    print('CHANGED: homarr images pinned')


def configure_env():
    values = settings()
    # BASE_URL があればそれを使う（HTTPS では NextAuth の Cookie が Secure になり、
    # ローカルの HTTP ではセッションが続かない）。未設定ならローカルへ直接。
    url = values.get('BASE_URL') or f"http://127.0.0.1:{values.get('HOMARR_PORT', '7575')}"
    return dict(os.environ,
               HOMARR_URL=url,
               HOMARR_ADMIN_USERNAME=values.get('HOMARR_ADMIN_USERNAME', 'admin'),
               HOMARR_ADMIN_PASSWORD=secret('admin_password'),
               BOARD_NAME=values.get('BOARD_NAME', 'home'),
               APPS_FILE=values.get('APPS_FILE', 'apps.json'),
               ADMIN_GROUP=values.get('ADMIN_GROUP', 'admins'),
               LOCALE=values.get('LOCALE', 'ja'))


def configure():
    env = configure_env()
    run([sys.executable, str(ROOT / 'configure.py')], env=env)
    # 監視スタックのトークンが配備されているときだけ、連携とウィジェットを揃える。
    if (ROOT / 'secrets' / 'integration_values.json').exists():
        run([sys.executable, str(ROOT / 'configure-integrations.py')], env=env)


def arrange():
    """一度だけボードを整列する。以後の手動配置は configure では動かさない。"""
    if not (ROOT / 'secrets' / 'integration_values.json').exists():
        raise SystemExit('integration values are missing; run configure first')
    run([sys.executable, str(ROOT / 'configure-integrations.py'), '--arrange'],
        env=configure_env())


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
        compose('stop', '--timeout', '60')
        run(['tar', '--numeric-owner', '-cpf', str(target / 'state.tar'), '-C', str(source), '.'])
        run(['tar', '--numeric-owner', '-cpf', str(target / 'deployment.tar'),
             'compose.yaml', 'compose.lock.yaml', '.env', '.env.example', 'secrets',
             'manage.py', 'configure.py', 'apps.json'])
    finally:
        if running:
            compose('start', *running)
    target.rename(target.with_suffix(''))
    print(f'Homarr backup complete: {target.with_suffix("")}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['init', 'lock', 'up', 'configure', 'arrange', 'status', 'backup'])
    parser.add_argument('--refresh-images', action='store_true')
    parser.add_argument('--destination', default=str(ROOT / 'backups'))
    args = parser.parse_args()
    if args.action == 'init':
        init()
    elif args.action == 'lock':
        lock(args.refresh_images)
    elif args.action == 'up':
        if not (ROOT / 'compose.lock.yaml').exists():
            raise SystemExit('Run lock first')
        compose('up', '-d', '--remove-orphans', '--wait', '--wait-timeout', '300')
    elif args.action == 'configure':
        configure()
    elif args.action == 'arrange':
        arrange()
    elif args.action == 'status':
        compose('ps')
    else:
        backup(args.destination)


if __name__ == '__main__':
    main()
