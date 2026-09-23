#!/usr/bin/env python3
"""shake-cloud API lifecycle on cloud-01. Run with sudo."""
import argparse
import base64
import datetime
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
BOOTSTRAP_KEY = 'bootstrap_admin_key'
# A finished backup is a directory named with its UTC stamp, e.g.
# 20260912T024107123456Z. `.incomplete` staging directories are not backups.
BACKUP_STAMP = re.compile(r'^\d{8}T\d{12}Z$')
# Written by the cloud_api Ansible role from the identity VM, never generated here.
OIDC_CREDENTIALS = 'oidc_credentials'
# The postgres user in the official alpine image.
POSTGRES_UID = 70
# The nonroot user in the distroless base image the API runs as (api/Dockerfile).
API_UID = 65532


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, text=True, check=True, **kwargs)


def settings():
    return dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)


def compose(*args, locked=True, **kwargs):
    cmd = ['docker', 'compose', '--env-file', str(ROOT / '.env'), '-f', 'compose.yaml']
    if locked and (ROOT / 'compose.lock.yaml').exists():
        cmd += ['-f', 'compose.lock.yaml']
    return run(cmd + list(args), **kwargs)


def storage():
    path = (ROOT / settings().get('STORAGE_ROOT', './storage')).resolve()
    if path == ROOT or path in ROOT.parents:
        raise ValueError('STORAGE_ROOT must not contain the deployment directory')
    return path


def bootstrap_key():
    """Mint an access key in the format of cloud/api/internal/accesskey."""
    key_id = base64.b32encode(secrets.token_bytes(12)).decode().rstrip('=').lower()
    secret = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')
    return f'sca_{key_id}.{secret}'


def write_secret(path, value):
    """Replace a secret atomically. Compose mounts single files, and the API runs
    as a non-root user, so the file is world-readable inside a 0700 directory."""
    temporary = path.with_name(path.name + '.tmp')
    temporary.unlink(missing_ok=True)
    with temporary.open('x') as file:
        file.write(value + '\n')
    temporary.chmod(0o444)
    temporary.replace(path)


def init():
    """Create .env, storage and secrets once. Never regenerate an existing secret."""
    changed = False
    if not (ROOT / '.env').exists():
        shutil.copyfile(ROOT / '.env.example', ROOT / '.env')
        changed = True
    (ROOT / '.env').chmod(0o600)
    path = storage() / 'postgres'
    if not path.exists():
        path.mkdir(parents=True, mode=0o750)
        changed = True
    if path.stat().st_uid != POSTGRES_UID:
        # PostgreSQL 18 keeps its data in <mount>/18/docker and creates that
        # directory after dropping to the postgres user, so the mount itself
        # must belong to that user; the entrypoint only fixes the leaf.
        os.chown(path, POSTGRES_UID, POSTGRES_UID)
        changed = True

    # Where an uploaded image waits while it is handed to Proxmox. It has to be
    # real disk: the node refuses a body of unknown length, so the API writes
    # the upload down to learn its size, and an image does not fit in RAM. The
    # API runs as the distroless nonroot user, so the mount must belong to it.
    uploads = storage() / 'uploads'
    if not uploads.exists():
        uploads.mkdir(parents=True, mode=0o750)
        changed = True
    if uploads.stat().st_uid != API_UID:
        os.chown(uploads, API_UID, API_UID)
        changed = True

    directory = ROOT / 'secrets'
    directory.mkdir(exist_ok=True, mode=0o700)
    directory.chmod(0o700)

    password = directory / 'db_password'
    if not password.exists():
        write_secret(password, secrets.token_urlsafe(48))
        changed = True
    if not password.read_text().strip():
        raise ValueError('Empty secret: db_password')

    # An empty key file is a deliberate "disabled" and must survive init.
    key = directory / BOOTSTRAP_KEY
    if not key.exists():
        write_secret(key, bootstrap_key())
        changed = True
    for path in (password, key):
        path.chmod(0o444)
    print('CHANGED: cloud initialized' if changed else 'OK: cloud already initialized')


def lock(refresh=False):
    """Pin pulled images. The API image is built here from pinned base images."""
    config = json.loads(compose('config', '--format', 'json', locked=False, capture_output=True).stdout)
    pulled = {name: service for name, service in config['services'].items() if 'build' not in service}
    path = ROOT / 'compose.lock.yaml'
    old = json.loads(path.read_text()).get('services', {}) if path.exists() else {}
    missing = [name for name in pulled if refresh or name not in old]
    if missing:
        compose('pull', *missing, locked=False)
    pinned = {}
    for name, service in pulled.items():
        if name in old and not refresh:
            pinned[name] = old[name]
        else:
            info = json.loads(run(['docker', 'image', 'inspect', service['image']], capture_output=True).stdout)[0]
            pinned[name] = {'image': info['RepoDigests'][0]}
    content = json.dumps({'services': pinned}, indent=2) + '\n'
    if path.exists() and path.read_text() == content:
        print('OK: cloud digests preserved')
        return
    temporary = path.with_suffix('.tmp')
    temporary.write_text(content)
    temporary.replace(path)
    print('CHANGED: cloud images pinned')


def up():
    if not (ROOT / 'compose.lock.yaml').exists():
        raise SystemExit('Run lock first')
    if not (ROOT / 'secrets' / OIDC_CREDENTIALS).exists():
        raise SystemExit('secrets/oidc_credentials is missing; deploy with platform/ansible/cloud.yml')
    compose('up', '-d', '--build', '--remove-orphans', '--wait', '--wait-timeout', '600')


def restart_api():
    # The key is read at startup, and a replaced file is a new inode the old
    # bind mount does not see, so recreate rather than restart.
    compose('up', '-d', '--no-deps', '--force-recreate', '--wait', '--wait-timeout', '120', 'api')


def rotate_bootstrap_key():
    write_secret(ROOT / 'secrets' / BOOTSTRAP_KEY, bootstrap_key())
    restart_api()
    print('CHANGED: bootstrap key rotated; the previous key is revoked')


def disable_bootstrap_key():
    write_secret(ROOT / 'secrets' / BOOTSTRAP_KEY, '')
    restart_api()
    print('CHANGED: bootstrap key disabled')


def complete_backups(destination):
    """Finished backups, oldest first. A crash mid-dump leaves a `.incomplete`
    staging directory, which must not count as a backup to keep or to prune."""
    return sorted(path for path in destination.iterdir()
                  if path.is_dir() and BACKUP_STAMP.fullmatch(path.name))


def expired_backups(destination, keep):
    """The finished backups older than the newest `keep`. keep <= 0 keeps all."""
    if keep <= 0:
        return []
    complete = complete_backups(destination)
    return complete[:-keep] if len(complete) > keep else []


def backup(destination, keep=0):
    """pg_dump runs against the live database, so the API stays up."""
    destination = Path(destination).resolve()
    if destination == storage() or storage() in destination.parents:
        raise ValueError('Backup destination must be outside storage')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = destination / (stamp + '.incomplete')
    target.mkdir(mode=0o700)
    with (target / 'shakecloud.dump').open('wb') as dump:
        subprocess.run(['docker', 'compose', '--env-file', str(ROOT / '.env'), '-f', 'compose.yaml',
                        'exec', '-T', 'postgres', 'pg_dump', '-U', 'shakecloud', '-Fc', 'shakecloud'],
                       cwd=ROOT, check=True, stdout=dump)
    run(['tar', '--numeric-owner', '-cpf', str(target / 'deployment.tar'),
         'compose.yaml', 'compose.lock.yaml', '.env', '.env.example', 'secrets', 'manage.py'])
    target.rename(target.with_suffix(''))
    # Prune only after a finished backup exists, so a failed run never deletes
    # the only good copy.
    for old in expired_backups(destination, keep):
        shutil.rmtree(old)
    print(f'Cloud backup complete: {target.with_suffix("")}')


def backup_metric(destination, metric):
    """Publish the newest finished backup for node_exporter's textfile collector.

    The alert watches both the age and the absence of this line, so a failed
    run or a stopped timer cannot look like a quiet healthy system. A backup
    directory's mtime is when its files were written, i.e. the finish time.
    """
    destination = Path(destination).resolve()
    metric = Path(metric)
    complete = complete_backups(destination) if destination.is_dir() else []
    newest = complete[-1] if complete else None
    stamp = int(newest.stat().st_mtime) if newest else 0
    metric.parent.mkdir(parents=True, exist_ok=True)
    metric.write_text(
        '# HELP backup_last_success_timestamp_seconds Unix time of the newest finished cloud backup.\n'
        '# TYPE backup_last_success_timestamp_seconds gauge\n'
        f'backup_last_success_timestamp_seconds {stamp}\n')
    metric.chmod(0o644)
    print(f'Cloud backup metric: {newest.name if newest else "none (0)"}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['init', 'lock', 'up', 'status', 'backup', 'backup-metric',
                                           'rotate-bootstrap-key', 'disable-bootstrap-key'])
    parser.add_argument('--refresh-images', action='store_true')
    parser.add_argument('--destination', default=str(ROOT / 'backups'))
    parser.add_argument('--keep', type=int, default=0,
                        help='keep this many finished backups and delete older ones (0 = keep all)')
    parser.add_argument('--metric', default='/var/lib/prometheus/node-exporter/cloud_backup.prom',
                        help='write backup_last_success_timestamp_seconds to this textfile')
    args = parser.parse_args()
    if args.action == 'init':
        init()
    elif args.action == 'lock':
        lock(args.refresh_images)
    elif args.action == 'up':
        up()
    elif args.action == 'status':
        compose('ps')
    elif args.action == 'backup':
        backup(args.destination, args.keep)
    elif args.action == 'backup-metric':
        backup_metric(args.destination, args.metric)
    elif args.action == 'rotate-bootstrap-key':
        rotate_bootstrap_key()
    else:
        disable_bootstrap_key()


if __name__ == '__main__':
    os.umask(0o077)
    main()
