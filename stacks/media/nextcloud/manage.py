#!/usr/bin/env python3
"""Deploy Nextcloud, Calendar and Tasks as an independent Compose project on media-01."""
import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTAINER_UID = 33
CONTAINER_GID = 33
SECRETS = ('postgres_password', 'nextcloud_admin_password')


def settings():
    """Read the literal KEY=value pairs Compose and init share."""
    values = {}
    for line in (ROOT / '.env').read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not key.replace('_', '').isalnum():
            raise ValueError('Invalid .env line; use KEY=literal_value')
        values[key] = value
    return values


def compose(*args, locked=True, capture_output=False):
    command = ['docker', 'compose', '--env-file', str(ROOT / '.env'),
               '-f', str(ROOT / 'compose.yaml')]
    if locked and (ROOT / 'compose.lock.yaml').exists():
        command += ['-f', str(ROOT / 'compose.lock.yaml')]
    environment = dict(os.environ)
    # Prevent shell environment variables from silently changing .env paths.
    environment.update(settings())
    return subprocess.run(command + list(args), cwd=ROOT, check=True, text=True,
                          env=environment, capture_output=capture_output)


def paths(config):
    """Return STORAGE_ROOT and LIBRARY_ROOT, kept as separate trees."""
    storage = Path(config.get('STORAGE_ROOT', '/srv/media-stack/storage')).resolve()
    library = Path(config.get('LIBRARY_ROOT', '/srv/media-stack/library')).resolve()
    if storage == library or storage in library.parents or library in storage.parents:
        raise ValueError('STORAGE_ROOT and LIBRARY_ROOT must be separate directories')
    return storage, library


def init():
    env = ROOT / '.env'
    if not env.exists():
        env.write_bytes((ROOT / '.env.example').read_bytes())
    env.chmod(0o600)
    storage, library = paths(settings())
    # www-data (33:33) writes Nextcloud's code, config and data, and reads the
    # shared books/music/docs originals. postgres owns its data directory itself.
    directories = [
        (storage, None),
        (storage / 'postgres', None),
        (storage / 'nextcloud', None),
    ]
    directories += [(storage / 'nextcloud' / name, (CONTAINER_UID, CONTAINER_GID))
                    for name in ('html', 'config', 'data')]
    directories += [(library, None)]
    directories += [(library / name, (CONTAINER_UID, CONTAINER_GID))
                    for name in ('books', 'music', 'docs')]
    for path, owner in directories:
        if not path.exists():
            try:
                path.mkdir(parents=True, mode=0o750)
            except PermissionError as error:
                raise PermissionError(f'Run init with sudo to create {path}') from error
        if owner:
            if (path.stat().st_uid, path.stat().st_gid) != owner:
                if os.geteuid() != 0:
                    raise PermissionError(
                        f'Run init with sudo to own {path} as {owner[0]}:{owner[1]}')
                os.chown(path, *owner)
            path.chmod(0o2750)
    directory = ROOT / 'secrets'
    directory.mkdir(exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    for name in SECRETS:
        path = directory / name
        if not path.exists():
            # Readable by the container users; the host directory stays private.
            with path.open('x') as handle:
                handle.write(secrets.token_urlsafe(36) + '\n')
        if not path.read_text().strip():
            raise ValueError(f'Empty secret file: {path}')
        path.chmod(0o444)
    print('OK: Nextcloud directories and secrets are ready')


def lock():
    lockfile = ROOT / 'compose.lock.yaml'
    if lockfile.exists():
        print('OK: existing image digests preserved')
        return
    compose('pull', locked=False)
    config = json.loads(compose('config', '--format', 'json', locked=False,
                                capture_output=True).stdout)
    services = {}
    for name, service in config['services'].items():
        data = json.loads(subprocess.check_output(
            ['docker', 'image', 'inspect', service['image']], text=True))[0]
        services[name] = {'image': data['RepoDigests'][0]}
    lockfile.write_text(json.dumps({'services': services}, indent=2) + '\n')
    print('CHANGED: image digests pinned in compose.lock.yaml')


def up():
    lock()
    compose('config', '--quiet')
    compose('up', '-d', '--remove-orphans', '--wait', '--wait-timeout', '900')


def occ(*args, **kwargs):
    return compose('exec', '-T', '--user', '33:33', 'nextcloud', 'php', 'occ', *args, **kwargs)


def setup():
    """Enable files_external and cron, then reconcile the shared library mounts."""
    occ('app:enable', 'files_external')
    occ('background:cron')
    raw = json.loads(occ('files_external:list', '--output=json', capture_output=True).stdout)
    mounts = list(raw.values()) if isinstance(raw, dict) else raw
    admin = settings().get('NEXTCLOUD_ADMIN_USER', 'admin')
    for name, datadir in (('books', '/library/books'),
                          ('music', '/library/music'),
                          ('docs', '/docs')):
        matching = [m for m in mounts if m['mount_point'].strip('/') == name]
        if not matching:
            occ('files_external:create', '/' + name, 'local', 'null::null',
                '--config', f'datadir={datadir}', '--applicable-user', admin)
            print(f'CHANGED: external storage created: /{name}')
        elif len(matching) != 1 or matching[0]['configuration'].get('datadir') != datadir:
            raise RuntimeError(f'Conflicting external storage mount: {name}; inspect in Nextcloud')
        else:
            # Preserve intentionally edited access rules on subsequent deployments.
            print(f'OK: external storage preserved: /{name}')


def apps(names):
    """Install and enable selected Nextcloud apps through occ.

    This keeps the container interaction in the portable unit script so
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',
                        choices=['init', 'lock', 'up', 'setup', 'apps', 'status', 'down'])
    parser.add_argument('--apps', dest='app_names', help='Comma-separated Nextcloud app IDs')
    args = parser.parse_args()
    if args.action in ('init', 'up'):
        init()
    if args.action == 'lock':
        lock()
    elif args.action == 'up':
        up()
    elif args.action == 'setup':
        setup()
    elif args.action == 'apps':
        if args.app_names is None:
            raise ValueError('Use --apps app1,app2 with the apps action')
        apps(args.app_names)
    elif args.action == 'status':
        compose('ps')
    elif args.action == 'down':
        compose('down')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
