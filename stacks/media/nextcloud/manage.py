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
    """Enable files_external and cron, then reconcile the shared library mounts.

    The library lives on the shared data disk, so it is opened to every account
    that can log in: inviting someone in Authentik is the access decision. The
    mount is created without an applicable list (empty = everyone) and any
    leftover user/group restriction is removed on redeploy.
    """
    occ('app:enable', 'files_external')
    occ('background:cron')
    raw = json.loads(occ('files_external:list', '--output=json', capture_output=True).stdout)
    mounts = list(raw.values()) if isinstance(raw, dict) else raw
    for name, datadir in (('books', '/library/books'),
                          ('music', '/library/music'),
                          ('docs', '/docs'),
                          ('inbox', '/library/inbox')):
        matching = [m for m in mounts if m['mount_point'].strip('/') == name]
        if not matching:
            occ('files_external:create', '/' + name, 'local', 'null::null',
                '--config', f'datadir={datadir}')
            print(f'CHANGED: external storage created: /{name}')
            continue
        if len(matching) != 1 or matching[0]['configuration'].get('datadir') != datadir:
            raise RuntimeError(f'Conflicting external storage mount: {name}; inspect in Nextcloud')
        mount = matching[0]
        changed = False
        for user in mount.get('applicable_users') or []:
            occ('files_external:applicable', str(mount['mount_id']), f'--remove-user={user}')
            changed = True
        for group in mount.get('applicable_groups') or []:
            occ('files_external:applicable', str(mount['mount_id']), f'--remove-group={group}')
            changed = True
        if changed:
            print(f'CHANGED: external storage opened to every user: /{name}')
        else:
            print(f'OK: external storage available to every user: /{name}')


def upgrade():
    """Apply pending Nextcloud/app upgrades (needed after an app version bump)."""
    result = occ('upgrade', capture_output=True)
    if 'Everything up-to-date' in result.stdout:
        print('OK: Nextcloud already up to date')
    else:
        print('CHANGED: Nextcloud upgraded')


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


def config_app(app, values):
    """Reconcile app config values and report only real changes.

    The token is a shared secret from SOPS and reaches this script through the
    environment; it is stored in Nextcloud's app config for the controller.
    """
    for key, value in values:
        try:
            current = occ('config:app:get', app, key,
                          capture_output=True).stdout.strip()
        except subprocess.CalledProcessError:
            current = ''
        if current == value:
            print(f'OK: {app} {key}')
        else:
            occ('config:app:set', app, key, f'--value={value}')
            print(f'CHANGED: {app} {key}')


def config_print():
    config_app('shake_print', (
        ('print_api_url', os.environ['PRINT_API_URL']),
        ('print_api_token', os.environ['PRINT_API_TOKEN']),
    ))


def config_localsend():
    config_app('shake_localsend', (
        ('send_api_url', os.environ['SEND_API_URL']),
        ('send_api_token', os.environ['SEND_API_TOKEN']),
    ))


def config_tags():
    config_app('shake_tags', (
        ('tags_api_url', os.environ['TAGS_API_URL']),
        ('tags_api_token', os.environ['TAGS_API_TOKEN']),
    ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',
                        choices=['init', 'lock', 'up', 'upgrade', 'setup', 'apps',
                                 'config-print', 'config-localsend', 'config-tags',
                                 'status', 'down'])
    parser.add_argument('--apps', dest='app_names', help='Comma-separated Nextcloud app IDs')
    args = parser.parse_args()
    if args.action in ('init', 'up'):
        init()
    if args.action == 'lock':
        lock()
    elif args.action == 'up':
        up()
    elif args.action == 'upgrade':
        upgrade()
    elif args.action == 'setup':
        setup()
    elif args.action == 'apps':
        if args.app_names is None:
            raise ValueError('Use --apps app1,app2 with the apps action')
        apps(args.app_names)
    elif args.action == 'config-print':
        config_print()
    elif args.action == 'config-localsend':
        config_localsend()
    elif args.action == 'config-tags':
        config_tags()
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
