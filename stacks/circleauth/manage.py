#!/usr/bin/env python3
"""The CIRCLEAUTH Discord bot on apps-01. Run with sudo.

The code is a checkout of the private repository rurutheGeek/CIRCLEAUTH and is
replaced by ``update``. Everything the bot writes lives outside that checkout,
in ``STORAGE_ROOT/state``, and is mounted over it: an update can never touch
the save data, and ``import`` refuses to write over save data that exists.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parent
SERVICE = 'bot'
TOKEN = 'discord_token'
# What the bot writes, relative to the checkout. Keep in step with the volumes
# in compose.yaml.
STATE_DIRECTORIES = ('save', 'log', 'resource/image')
STATE_FILES = ('config.json',)
STAMP = re.compile(r'^\d{8}T\d{6}Z\.tar\.gz$')


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, text=True, check=True, **kwargs)


def settings():
    return dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)


def token():
    path = ROOT / 'secrets' / TOKEN
    return path.read_text().strip() if path.exists() else ''


def compose(*args, locked=True, **kwargs):
    cmd = ['docker', 'compose', '--env-file', str(ROOT / '.env'), '-f', 'compose.yaml']
    if locked and (ROOT / 'compose.lock.yaml').exists():
        cmd += ['-f', 'compose.lock.yaml']
    # config と pull は値を使わないので、トークンが無くても通るよう仮の値を渡す。
    env = dict(os.environ, DISCORD_TOKEN=token() or 'unset')
    return run(cmd + list(args), env=env, **kwargs)


def storage():
    configured = Path(settings().get('STORAGE_ROOT', '/srv/circleauth'))
    path = configured.resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('STORAGE_ROOT must not contain the deployment directory')
    return path


def source():
    return storage() / 'source'


def state():
    return storage() / 'state'


def init():
    """Create .env and the storage layout. Existing save data is left alone."""
    changed = False
    if not (ROOT / '.env').exists():
        shutil.copyfile(ROOT / '.env.example', ROOT / '.env')
        changed = True
    (ROOT / '.env').chmod(0o600)
    directory = ROOT / 'secrets'
    directory.mkdir(exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    for name in STATE_DIRECTORIES:
        path = state() / name
        if not path.exists():
            path.mkdir(parents=True, mode=0o755)
            changed = True
    print('CHANGED: circleauth initialized' if changed else 'OK: circleauth already initialized')


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
        print('OK: circleauth digests preserved')
        return
    temporary = path.with_suffix('.tmp')
    temporary.write_text(content)
    temporary.replace(path)
    print('CHANGED: circleauth images pinned')


def git(*args):
    return run(['git', '-C', str(source()), *args], capture_output=True).stdout.strip()


def running():
    return SERVICE in compose('ps', '--services', '--status', 'running',
                              capture_output=True).stdout.split()


def update():
    """Bring the checkout to the branch head; restart the bot only if it runs."""
    configured = settings()
    repository = configured['CIRCLEAUTH_REPOSITORY']
    branch = configured.get('CIRCLEAUTH_BRANCH', 'main')
    if not (source() / '.git').exists():
        source().parent.mkdir(parents=True, exist_ok=True)
        run(['git', 'clone', '--branch', branch, repository, str(source())], capture_output=True)
        print(f'CHANGED: source cloned at {git("rev-parse", "--short", "HEAD")}')
        return
    git('fetch', '--quiet', repository, branch)
    wanted = git('rev-parse', 'FETCH_HEAD')
    if git('rev-parse', 'HEAD') == wanted:
        print(f'OK: source at {wanted[:7]}')
        return
    # The save data is mounted from state/, so resetting the checkout cannot reach it.
    git('reset', '--hard', wanted)
    if running():
        compose('up', '-d', '--force-recreate')
    print(f'CHANGED: source updated to {wanted[:7]}')


def missing_state():
    paths = [state() / name for name in STATE_DIRECTORIES + STATE_FILES]
    return [str(path) for path in paths if not path.exists()]


def up():
    if not (ROOT / 'compose.lock.yaml').exists():
        raise SystemExit('Run lock first')
    if not token():
        raise ValueError('secrets/discord_token is missing')
    if not (source() / 'main.py').exists():
        raise ValueError('Run update first: the source is not checked out')
    missing = missing_state()
    if missing:
        # Starting without the save data would let the bot begin from nothing.
        raise ValueError(f'Save data is missing, import it first: {", ".join(missing)}')
    compose('up', '-d', '--remove-orphans')


def state_files():
    root = state()
    return sorted(path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file())


def allowed(name):
    if name in STATE_FILES or name in STATE_DIRECTORIES:
        return True
    return any(name.startswith(directory + '/') for directory in STATE_DIRECTORIES)


def import_state(archive):
    """Unpack the old host's save data. Refuses if any save data is here."""
    present = state_files()
    if present:
        raise ValueError(f'Save data already exists ({len(present)} files); not overwritten')
    root = state()
    count = 0
    with tarfile.open(archive, 'r:*') as tar:
        members = tar.getmembers()
        for member in members:
            name = PurePosixPath(member.name).as_posix()
            if name.startswith('./'):
                name = name[2:]
            if '..' in PurePosixPath(name).parts or name.startswith('/') or not allowed(name):
                raise ValueError(f'Unexpected entry in the archive: {member.name}')
            if not (member.isfile() or member.isdir()):
                raise ValueError(f'Unsupported entry in the archive: {member.name}')
        for member in members:
            target = root / PurePosixPath(member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as data, open(target, 'wb') as file:
                shutil.copyfileobj(data, file)
            os.utime(target, (member.mtime, member.mtime))
            count += 1
    missing = missing_state()
    if missing:
        raise ValueError(f'The archive lacks: {", ".join(missing)}')
    print(f'CHANGED: imported {count} files into {root}')


def digest():
    """Print `sha256  path` for every save file, like sha256sum, sorted by path."""
    root = state()
    for name in state_files():
        print(f'{hashlib.sha256((root / name).read_bytes()).hexdigest()}  {name}')


def backup(destination, keep):
    destination = Path(destination).resolve()
    if destination == state() or state() in destination.parents:
        raise ValueError('Backup destination must be outside the save data')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.chmod(0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target = destination / f'{stamp}.tar.gz'
    partial = destination / f'{stamp}.incomplete'
    with tarfile.open(partial, 'w:gz') as tar:
        for name in STATE_DIRECTORIES + STATE_FILES:
            tar.add(state() / name, arcname=name)
    partial.rename(target)
    complete = sorted(path for path in destination.iterdir() if STAMP.match(path.name))
    for path in complete[:-keep] if keep > 0 else []:
        path.unlink()
    print(f'circleauth backup complete: {target}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'lock', 'update', 'up', 'status', 'down',
                                           'import', 'digest', 'backup'])
    parser.add_argument('archive', nargs='?', help='save data tarball for import')
    parser.add_argument('--refresh-images', action='store_true')
    parser.add_argument('--destination', default=str(ROOT / 'backups'))
    parser.add_argument('--keep', type=int, default=14, help='backups to keep')
    args = parser.parse_args()
    if args.action == 'init':
        init()
    elif args.action == 'lock':
        lock(args.refresh_images)
    elif args.action == 'update':
        update()
    elif args.action == 'up':
        up()
    elif args.action == 'status':
        compose('ps')
    elif args.action == 'down':
        compose('down')
    elif args.action == 'import':
        if not args.archive:
            parser.error('import requires the save data tarball')
        import_state(args.archive)
    elif args.action == 'digest':
        digest()
    else:
        backup(args.destination, args.keep)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, tarfile.TarError,
            subprocess.CalledProcessError) as error:
        detail = getattr(error, 'stderr', '') or ''
        print(f'ERROR: {error}{": " + detail.strip() if detail else ""}', file=sys.stderr)
        sys.exit(1)
