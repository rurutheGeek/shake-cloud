#!/usr/bin/env python3
"""Portable stack operations; Python standard library and Docker Compose v2."""
import argparse
import datetime
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def settings():
    values = {}
    for line in (ROOT / '.env').read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not key.replace('_', '').isalnum():
            raise ValueError('Invalid .env line; use KEY=literal_value')
        if any(c in value for c in ['$', '"', "'", '#']):
            raise ValueError('Use unquoted literal .env values without $, quotes or #')
        values[key] = value
    ports = ROOT / 'sso/ports.env'
    if ports.exists():
        for line in ports.read_text().splitlines():
            key, sep, value = line.partition('=')
            if sep and key in ('NAVIDROME_PORT', 'METUBE_PORT'):
                if not value.isdigit() or not 1 <= int(value) <= 65535:
                    raise ValueError('Invalid SSO internal port')
                values[key] = value
    return values


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, text=True, **kwargs)


def compose(*args, locked=True, **kwargs):
    cmd = ['docker', 'compose', '--env-file', str(ROOT / '.env'), '-f', 'compose.yaml']
    if (ROOT / 'compose.integrations.yaml').exists():
        cmd += ['-f', 'compose.integrations.yaml']
    if (ROOT / 'compose.https.yaml').exists():
        cmd += ['-f', 'compose.https.yaml']
    if locked and (ROOT / 'compose.lock.yaml').exists():
        cmd += ['-f', 'compose.lock.yaml']
    # Prevent shell environment variables from silently changing .env paths/images.
    env = dict(os.environ)
    env.update(settings())
    return run(cmd + list(args), env=env, **kwargs)


def paths():
    config = settings()
    state = (ROOT / config.get('STORAGE_ROOT', './storage')).resolve()
    library = (ROOT / config.get('LIBRARY_ROOT', './library')).resolve()
    if state == library or state in library.parents or library in state.parents:
        raise ValueError('STORAGE_ROOT and LIBRARY_ROOT must be separate directories')
    for path in (state, library):
        if path == ROOT or path in ROOT.parents:
            raise ValueError('Data paths must not contain the project directory')
    return state, library


def init():
    changed = False
    env = ROOT / '.env'
    if not env.exists():
        shutil.copyfile(ROOT / '.env.example', env)
        changed = True
    env.chmod(0o600)
    config = settings()
    state, library = paths()
    uid, gid = int(config.get('MEDIA_UID', 33)), int(config.get('MEDIA_GID', 33))
    directories = [(state, None), (library, None), (state / 'postgres', None),
                   (state / 'kavita', None), (state / 'vaultwarden', None),
                   (state / 'caddy' / 'data', None), (state / 'caddy' / 'config', None)]
    directories += [(state / 'nextcloud' / name, (33, 33))
                    for name in ('html', 'config', 'data')]
    directories += [(state / 'navidrome', (uid, gid)),
                    (library / 'books', (33, 33)), (library / 'music', (33, 33)),
                    (library / 'docs', (33, 33))]
    for path, owner in directories:
        if not path.exists():
            path.mkdir(parents=True, mode=0o750)
            changed = True
        if owner and (path.stat().st_uid, path.stat().st_gid) != owner:
            if os.geteuid() != 0:
                raise PermissionError('Run init with sudo to set container directory ownership')
            os.chown(path, *owner)
            changed = True
        if owner:
            path.chmod(0o2750)
    secret_dir = ROOT / 'secrets'
    secret_dir.mkdir(mode=0o700, exist_ok=True)
    secret_dir.chmod(0o700)
    for name in ('postgres_password', 'nextcloud_admin_password', 'vaultwarden_admin_token'):
        path = secret_dir / name
        if not path.exists():
            # File readable by container users; host directory is private.
            with path.open('x') as handle:
                handle.write(secrets.token_urlsafe(36) + '\n')
            changed = True
        if not path.read_text().strip():
            raise ValueError(f'Empty secret file: {path}')
        path.chmod(0o444)
    print('CHANGED: initialization complete' if changed else 'OK: already initialized')


def lock(refresh=False):
    config = json.loads(compose('config', '--format', 'json', locked=False,
                               capture_output=True).stdout)
    lockfile = ROOT / 'compose.lock.yaml'
    old = json.loads(lockfile.read_text()).get('services', {}) if lockfile.exists() else {}
    names = [name for name in config['services'] if refresh or name not in old]
    if names:
        compose('pull', *names, locked=False)
    services = {}
    for name, service in config['services'].items():
        if name in old and not refresh:
            services[name] = old[name]
            continue
        data = json.loads(run(['docker', 'image', 'inspect', service['image']],
                              capture_output=True).stdout)[0]
        digests = data.get('RepoDigests', [])
        if not digests:
            raise RuntimeError(f'Image has no repository digest: {name}')
        services[name] = {'image': digests[0]}
    content = json.dumps({'services': services}, indent=2) + '\n'
    if lockfile.exists() and lockfile.read_text() == content:
        print('OK: existing image digests preserved')
        return
    temporary = ROOT / 'compose.lock.yaml.tmp'
    temporary.write_text(content)
    temporary.replace(lockfile)
    print('CHANGED: image digests pinned in compose.lock.yaml')


def occ(*args, **kwargs):
    return compose('exec', '-T', '--user', '33:33', 'nextcloud', 'php', 'occ', *args, **kwargs)


def setup():
    occ('app:enable', 'files_external')
    occ('background:cron')
    raw = json.loads(occ('files_external:list', '--output=json', capture_output=True).stdout)
    mounts = list(raw.values()) if isinstance(raw, dict) else raw
    admin = settings().get('NEXTCLOUD_ADMIN_USER', 'admin')
    for name, datadir in (('books', '/library/books'),
                          ('music', '/library/music'),
                          ('docs', '/docs')):
        matching = [m for m in mounts if m['mount_point'].strip('/') == name]
        if matching:
            if len(matching) != 1 or matching[0]['configuration'].get('datadir') != datadir:
                raise RuntimeError(f'Conflicting external storage mount: {name}; inspect in Nextcloud')
            # Preserve intentionally edited access rules on subsequent deployments.
            print(f'Existing external storage preserved: {name}')
        else:
            occ('files_external:create', '/' + name, 'local', 'null::null',
                '--config', f'datadir={datadir}', '--applicable-user', admin)


def apps(names):
    """Install and enable selected Nextcloud apps through occ.

    This keeps the container interaction in the portable stack script so
    Ansible can invoke the same operation on local and remote deployments.
    """
    requested = [name.strip() for name in names.split(',') if name.strip()]
    if not requested:
        print('OK: no additional Nextcloud apps requested')
        return
    state = json.loads(occ('app:list', '--output=json', capture_output=True).stdout)
    enabled = set(state.get('enabled', {}))
    disabled = set(state.get('disabled', {}))
    for name in requested:
        if name in enabled:
            print(f'OK: Nextcloud app already enabled: {name}')
        elif name in disabled:
            occ('app:enable', name)
            print(f'CHANGED: Nextcloud app enabled: {name}')
        else:
            occ('app:install', name)
            print(f'CHANGED: Nextcloud app installed: {name}')


def up():
    if not (ROOT / 'compose.lock.yaml').exists():
        raise RuntimeError('Run lock first to pin images')
    compose('config', '--quiet')
    compose('up', '-d', '--remove-orphans', '--wait', '--wait-timeout', '900')
    setup()
    compose('ps')


def backup(destination):
    if os.geteuid() != 0:
        raise PermissionError('Run backup with sudo to read all application state')
    state, library = paths()
    destination = Path(destination).resolve()
    for source in (state, library):
        if destination == source or source in destination.parents:
            raise ValueError('Backup destination must be outside storage and library')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = destination / (stamp + '.incomplete')
    target.mkdir(mode=0o700)
    running = compose('ps', '--services', '--status', 'running', capture_output=True).stdout.split()
    # Cold snapshot: PostgreSQL and SQLite are cleanly stopped before copying.
    # Finally restores only services that were running on entry, even on tar failure.
    try:
        compose('stop', '--timeout', '120')
        run(['tar', '--numeric-owner', '-cpf', str(target / 'state.tar'), '-C', str(state), '.'])
        run(['tar', '--numeric-owner', '-cpf', str(target / 'library.tar'), '-C', str(library), '.'])
        deployment = ['compose.yaml', '.env', '.env.example', 'secrets', 'scripts', 'compose.lock.yaml']
        if (ROOT / 'runtime/accounts.json').exists():
            deployment.append('runtime/accounts.json')
        if (ROOT / 'compose.integrations.yaml').exists():
            deployment.append('compose.integrations.yaml')
        if (ROOT / 'compose.https.yaml').exists():
            deployment += ['compose.https.yaml', 'Caddyfile']
        run(['tar', '--numeric-owner', '-cpf', str(target / 'deployment.tar'), *deployment])
        (target / 'manifest.json').write_text(json.dumps({
            'storage_root': str(state), 'library_root': str(library),
            'architecture': os.uname().machine, 'created_utc': stamp,
            'format': 1, 'database': 'cold PostgreSQL data directory; same major/architecture required'
        }, indent=2) + '\n')
    finally:
        if running:
            compose('start', *running)
    complete = target.with_suffix('')
    target.rename(complete)
    print(f'Backup complete: {complete}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'lock', 'up', 'setup', 'apps', 'status', 'down', 'backup'])
    parser.add_argument('--destination', default=str(ROOT / 'backups'))
    parser.add_argument('--apps', dest='app_names', help='Comma-separated Nextcloud app IDs')
    parser.add_argument('--refresh-images', action='store_true', help='Explicitly update all pinned images')
    args = parser.parse_args()
    if args.action == 'lock':
        lock(refresh=args.refresh_images)
    elif args.action == 'backup':
        backup(args.destination)
    elif args.action == 'apps':
        if args.app_names is None:
            raise ValueError('Use --apps app1,app2 with the apps action')
        apps(args.app_names)
    elif args.action == 'status':
        compose('ps')
    elif args.action == 'down':
        compose('down')
    else:
        globals()[args.action]()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
