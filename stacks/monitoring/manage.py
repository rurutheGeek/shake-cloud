#!/usr/bin/env python3
"""Monitoring stack lifecycle on monitor-01. Run with sudo.

Prometheus keeps its time series on the data disk, Grafana its database. The
secret values (Grafana admin, NUT password, Proxmox token) are generated or
copied here and passed to Compose as environment variables, never written to
.env.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import secrets
import shutil
import string
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
GENERATED_SECRETS = ('grafana_admin_password', 'nut_password', 'peanut_web_password')
# The Proxmox read-only token is copied from SOPS by the Ansible role.
PVE_TOKEN = 'pve_token'
OIDC_SECRET = 'oidc_client.json'


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, text=True, check=True, **kwargs)


def settings():
    return dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)


def secret(name):
    path = ROOT / 'secrets' / name
    return path.read_text().strip() if path.exists() else ''


def oidc_client_secret():
    path = ROOT / 'secrets' / OIDC_SECRET
    if not path.exists():
        return ''
    return json.loads(path.read_text()).get('client_secret', '')


def compose(*args, locked=True, **kwargs):
    cmd = ['docker', 'compose', '--env-file', str(ROOT / '.env'), '-f', 'compose.yaml']
    if locked and (ROOT / 'compose.lock.yaml').exists():
        cmd += ['-f', 'compose.lock.yaml']
    env = dict(os.environ,
               GRAFANA_ADMIN_PASSWORD=secret('grafana_admin_password'),
               GRAFANA_OIDC_CLIENT_SECRET=oidc_client_secret(),
               NUT_PASSWORD=secret('nut_password'),
               PEANUT_WEB_PASSWORD=secret('peanut_web_password'))
    return run(cmd + list(args), env=env, **kwargs)


def storage():
    path = (ROOT / settings().get('STORAGE_ROOT', './storage')).resolve()
    if path == ROOT or path in ROOT.parents:
        raise ValueError('STORAGE_ROOT must not contain the deployment directory')
    return path


def render_pve_config():
    """Write pve-exporter's config with the token from secrets/, not Git."""
    values = settings()
    token = secret(PVE_TOKEN)
    if not token:
        raise SystemExit('secrets/pve_token is missing; the Ansible role copies it from SOPS')
    target = storage() / 'pve-exporter'
    target.mkdir(parents=True, exist_ok=True)
    (target / 'pve.yml').write_text(
        'default:\n'
        f"  user: {values.get('PVE_USER', 'monitoring@pve')}\n"
        f"  token_name: {values.get('PVE_TOKEN_NAME', 'monitoring')}\n"
        f'  token_value: {token}\n'
        '  verify_ssl: false\n')
    (target / 'pve.yml').chmod(0o600)


def render_peanut_config():
    """Write PeaNUT's settings.yml with the NUT server and credentials.

    PeaNUT is configured through /config/settings.yml. The container runs as
    UID 1000, so the directory and file are owned by that user.
    """
    values = settings()
    nut_password = secret('nut_password')
    if not nut_password:
        raise SystemExit('secrets/nut_password is missing; run manage.py init first')
    target = storage() / 'peanut'
    target.mkdir(parents=True, exist_ok=True)
    os.chown(target, 1000, 1000)
    path = target / 'settings.yml'
    path.write_text(
        'NUT_SERVERS:\n'
        f"  - HOST: {values.get('NUT_SERVER', '192.168.10.126')}\n"
        '    PORT: 3493\n'
        f"    USERNAME: {values.get('NUT_USERNAME', 'monitor')}\n"
        f'    PASSWORD: {nut_password}\n')
    os.chown(path, 1000, 1000)
    path.chmod(0o600)


def render_alertmanager_config():
    """Write Alertmanager's config with the SMTP values from .env.

    Alertmanager 0.34 does not expand environment variables in its config,
    so the template is filled here. The file contains the SMTP password and
    is owned by the container user (nobody).
    """
    values = settings()
    template = string.Template((ROOT / 'alertmanager/alertmanager.yml.template').read_text())
    rendered = template.substitute({key: values.get(key, '') for key in (
        'SMTP_HOST', 'SMTP_PORT', 'SMTP_FROM', 'SMTP_USERNAME', 'SMTP_PASSWORD',
        'SMTP_REQUIRE_TLS', 'ALERT_EMAIL')})
    target = storage() / 'alertmanager-config'
    target.mkdir(parents=True, exist_ok=True)
    path = target / 'alertmanager.yml'
    path.write_text(rendered)
    os.chown(path, 65534, 65534)
    path.chmod(0o600)


def init():
    """Create .env, storage and secrets once. Never regenerate an existing secret."""
    changed = False
    if not (ROOT / '.env').exists():
        shutil.copyfile(ROOT / '.env.example', ROOT / '.env')
        changed = True
    (ROOT / '.env').chmod(0o600)
    for name in ('prometheus', 'alertmanager', 'alertmanager-config', 'grafana', 'pve-exporter', 'peanut'):
        path = storage() / name
        if not path.exists():
            path.mkdir(parents=True, mode=0o750)
            changed = True
    if (storage() / 'grafana').stat().st_uid != 472:
        # Grafana runs as UID 472 in the official image.
        os.chown(storage() / 'grafana', 472, 472)
        changed = True
    for name in ('prometheus', 'alertmanager', 'alertmanager-config'):
        # The Prometheus and Alertmanager images run as nobody (65534).
        if (storage() / name).stat().st_uid != 65534:
            os.chown(storage() / name, 65534, 65534)
            changed = True
    directory = ROOT / 'secrets'
    directory.mkdir(exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    for name in GENERATED_SECRETS:
        target = directory / name
        if not target.exists():
            with target.open('x') as file:
                file.write(secrets.token_urlsafe(32) + '\n')
            changed = True
        if not target.read_text().strip():
            raise ValueError(f'Empty secret: {name}')
        target.chmod(0o400)
    print('CHANGED: monitoring initialized' if changed else 'OK: monitoring already initialized')


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
        print('OK: monitoring digests preserved')
        return
    temporary = path.with_suffix('.tmp')
    temporary.write_text(content)
    temporary.replace(path)
    print('CHANGED: monitoring images pinned')


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
             'manage.py', 'prometheus', 'grafana', 'blackbox'])
    finally:
        if running:
            compose('start', *running)
    target.rename(target.with_suffix(''))
    print(f'Monitoring backup complete: {target.with_suffix("")}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['init', 'lock', 'up', 'reload', 'restart', 'status', 'backup'])
    parser.add_argument('--refresh-images', action='store_true')
    parser.add_argument('--destination', default=str(ROOT / 'backups'))
    args = parser.parse_args()
    if args.action == 'init':
        init()
        render_pve_config()
        render_alertmanager_config()
        render_peanut_config()
    elif args.action == 'lock':
        lock(args.refresh_images)
    elif args.action == 'up':
        if not (ROOT / 'compose.lock.yaml').exists():
            raise SystemExit('Run lock first')
        render_pve_config()
        render_alertmanager_config()
        render_peanut_config()
        compose('up', '-d', '--remove-orphans', '--wait', '--wait-timeout', '300')
    elif args.action == 'reload':
        # Prometheus と Alertmanager は設定を起動時にしか読まない。
        render_pve_config()
        render_alertmanager_config()
        compose('restart', 'prometheus', 'alertmanager')
    elif args.action == 'restart':
        # 保存先の所有権を直したときなど、設定は同じでもコンテナを作り直す。
        render_peanut_config()
        compose('up', '-d', '--force-recreate', '--wait', '--wait-timeout', '300')
    elif args.action == 'status':
        compose('ps')
    else:
        backup(args.destination)


if __name__ == '__main__':
    main()
