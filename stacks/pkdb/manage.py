#!/usr/bin/env python3
"""PostgreSQL for the Pokémon databases on apps-01. Run with sudo.

The server holds sleepy_pkdb, shakeweb and pkhack, moved from the old aarch64
host by logical dump. ``fetch`` dumps another server with the pinned image's
own client, ``restore`` loads a dump directory without touching a database that
already exists, and ``backup`` writes the same layout from this server, so a
backup is restored the same way the migration was.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SERVICE = 'db'
SUPERUSER = 'postgres'
GENERATED_SECRETS = ('postgres_password',)
STORAGE_DIRECTORY = 'data'
SOURCE_PASSWORD = 'PKDB_SOURCE_PASSWORD'
NAME = re.compile(r'^[A-Za-z0-9_]+$')
STAMP = re.compile(r'^\d{8}T\d{6}Z$')
ROLE_STATEMENT = re.compile(r'^(CREATE|ALTER) ROLE ("?)([^" ;]+)\2[ ;]')

LIST_DATABASES = ("select datname from pg_database "
                  f"where not datistemplate and datname <> '{SUPERUSER}' order by 1")
# One row per table and materialized view: name, row count, digest of the rows.
# Rows are ordered by their own digest so the result does not depend on the
# physical order or the collation.
FINGERPRINT = r"""
select format(
  'select %L, count(*), coalesce(md5(string_agg(md5(t::text), '''' order by md5(t::text) collate "C")), ''-'') from %I.%I t',
  n.nspname || '.' || c.relname, n.nspname, c.relname)
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where c.relkind in ('r', 'm') and n.nspname !~ '^pg_' and n.nspname <> 'information_schema'
order by 1 \gexec
"""


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
    configured = Path(settings().get('STORAGE_ROOT', '/srv/pkdb'))
    path = configured.resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('STORAGE_ROOT must not contain the deployment directory')
    return path


def init():
    """Create .env, storage and the superuser password once. Never regenerate it."""
    changed = False
    if not (ROOT / '.env').exists():
        shutil.copyfile(ROOT / '.env.example', ROOT / '.env')
        changed = True
    (ROOT / '.env').chmod(0o600)
    path = storage() / STORAGE_DIRECTORY
    if not path.exists():
        path.mkdir(parents=True, mode=0o700)
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
    print('CHANGED: pkdb initialized' if changed else 'OK: pkdb already initialized')


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
        print('OK: pkdb digests preserved')
        return
    temporary = path.with_suffix('.tmp')
    temporary.write_text(content)
    temporary.replace(path)
    print('CHANGED: pkdb images pinned')


def up():
    if not (ROOT / 'compose.lock.yaml').exists():
        raise SystemExit('Run lock first')
    compose('up', '-d', '--remove-orphans', '--wait', '--wait-timeout', '300')


def local(program, *args, **kwargs):
    """Run a client program in the running container, over its own socket."""
    return compose('exec', '-T', SERVICE, program, '-U', SUPERUSER, *args, **kwargs)


def remote(host, port, user):
    """Return a runner for another server, using the pinned image's client.

    The client must not be newer than this server: pg_restore 15 cannot read an
    archive written by a later pg_dump. The password comes from the environment
    so it never lands in a file or in the container's arguments.
    """
    if not os.environ.get(SOURCE_PASSWORD):
        raise ValueError(f'Set {SOURCE_PASSWORD} to the source password')
    image = json.loads((ROOT / 'compose.lock.yaml').read_text())['services'][SERVICE]['image']
    env = dict(os.environ, PGPASSWORD=os.environ[SOURCE_PASSWORD])

    def runner(program, *args, **kwargs):
        return run(['docker', 'run', '--rm', '-i', '--network', 'host', '-e', 'PGPASSWORD',
                    image, program, '-h', host, '-p', str(port), '-U', user, *args],
                   env=env, **kwargs)
    return runner


def databases(client):
    names = client('psql', '-d', 'postgres', '-At', '-c', LIST_DATABASES,
                   capture_output=True).stdout.split('\n')
    names = [name for name in names if name]
    for name in names:
        if not NAME.match(name):
            raise ValueError(f'Unsupported database name: {name}')
    return names


def dump(client, target):
    """Write globals.sql, one custom-format archive per database and a manifest."""
    target = Path(target).resolve()
    if target.exists():
        raise ValueError(f'Dump directory already exists: {target}')
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    partial = target.with_name(target.name + '.incomplete')
    if partial.exists():
        shutil.rmtree(partial)
    # The roles carry password hashes: keep the whole directory private.
    partial.mkdir(mode=0o700)
    names = databases(client)
    with open(partial / 'globals.sql', 'w', opener=private) as file:
        client('pg_dumpall', '--globals-only', stdout=file)
    for name in names:
        with open(partial / f'{name}.dump', 'wb', opener=private) as file:
            client('pg_dump', '-Fc', '-d', name, stdout=file)
    version = client('psql', '-d', 'postgres', '-At', '-c', 'show server_version',
                     capture_output=True).stdout.strip()
    (partial / 'manifest.json').write_text(json.dumps({
        'databases': names,
        'server_version': version,
        'created_utc': datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
        'format': 1,
    }, indent=2) + '\n')
    partial.rename(target)
    return names


def private(path, flags):
    return os.open(path, flags, 0o600)


def fetch(host, port, user, directory):
    names = dump(remote(host, port, user), directory)
    print(f'CHANGED: fetched {", ".join(names)} into {Path(directory).resolve()}')


def backup(destination, keep):
    destination = Path(destination).resolve()
    source = storage() / STORAGE_DIRECTORY
    if destination == source or source in destination.parents:
        raise ValueError('Backup destination must be outside the data directory')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.chmod(0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    names = dump(local, destination / stamp)
    complete = sorted(path for path in destination.iterdir()
                      if path.is_dir() and STAMP.match(path.name))
    for path in complete[:-keep] if keep > 0 else []:
        shutil.rmtree(path)
    print(f'pkdb backup complete: {destination / stamp} ({", ".join(names)})')


def roles_sql(text, existing):
    """Drop what must not be replayed from a globals dump.

    The superuser keeps the password generated on this server, and a role that
    already exists is not created again. ALTER ROLE for the other roles is kept,
    so a rerun sets their attributes and password hashes to the dump's.
    """
    kept = []
    for line in text.splitlines():
        match = ROLE_STATEMENT.match(line)
        if match:
            verb, role = match.group(1), match.group(3)
            if role == SUPERUSER or (verb == 'CREATE' and role in existing):
                continue
        kept.append(line)
    return '\n'.join(kept) + '\n'


def restore(directory):
    """Load a dump directory. A database that already exists is left alone."""
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'manifest.json').read_text())
    names = manifest['databases']
    for name in names:
        if not NAME.match(name):
            raise ValueError(f'Unsupported database name: {name}')
        if not (directory / f'{name}.dump').is_file():
            raise ValueError(f'Missing archive: {name}.dump')
    existing = set(databases(local))
    wanted = [name for name in names if name not in existing]
    if not wanted:
        print('OK: every database already exists, nothing restored')
        return
    roles = set(local('psql', '-d', 'postgres', '-At', '-c', 'select rolname from pg_roles',
                      capture_output=True).stdout.split('\n'))
    local('psql', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-q',
          input=roles_sql((directory / 'globals.sql').read_text(), roles),
          stdout=subprocess.DEVNULL)
    for name in wanted:
        with open(directory / f'{name}.dump', 'rb') as file:
            local('pg_restore', '--create', '--exit-on-error', '-d', 'postgres', stdin=file)
    skipped = [name for name in names if name in existing]
    print(f'CHANGED: restored {", ".join(wanted)}'
          + (f'; kept existing {", ".join(skipped)}' if skipped else ''))


def fingerprint(client):
    """Print `database schema.table rows digest` for every table and matview."""
    for name in databases(client):
        rows = client('psql', '-d', name, '-At', '-F', ' ', '-v', 'ON_ERROR_STOP=1',
                      input=FINGERPRINT, capture_output=True).stdout
        for row in rows.splitlines():
            print(name, row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'lock', 'up', 'status', 'backup',
                                           'fetch', 'restore', 'fingerprint'])
    parser.add_argument('directory', nargs='?', help='dump directory for fetch and restore')
    parser.add_argument('--refresh-images', action='store_true')
    parser.add_argument('--destination', default=str(ROOT / 'backups'))
    parser.add_argument('--keep', type=int, default=14, help='backups to keep')
    parser.add_argument('--host', help='another server, for fetch and fingerprint')
    parser.add_argument('--port', type=int, default=5432)
    parser.add_argument('--user', default=SUPERUSER)
    args = parser.parse_args()
    if args.action in ('fetch', 'restore') and not args.directory:
        parser.error(f'{args.action} requires the dump directory')
    if args.action == 'fetch' and not args.host:
        parser.error('fetch requires --host')
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
    elif args.action == 'fetch':
        fetch(args.host, args.port, args.user, args.directory)
    elif args.action == 'restore':
        restore(args.directory)
    else:
        fingerprint(remote(args.host, args.port, args.user) if args.host else local)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
