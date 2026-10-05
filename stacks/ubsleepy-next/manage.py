#!/usr/bin/env python3
"""UBSLEEPY（-next）の運用。Run with sudo.

配備はAnsible（platform/ansible/ubsleepy-next.yml）が行う。ここは状態の確認や
手元操作のためのもの。イメージは compose.lock.yaml の digest（GitHub Actions が
main のマージ時に出すコミットIDタグのもの）を使い、apps-01 ではビルドしない。
セーブデータは STORAGE_ROOT/state からコンテナへ重ねる。
"""
import argparse
import datetime
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parent
SERVICE = 'bot'
IMAGE = 'ghcr.io/ruruthegeek/ubsleepy-next'
TOKEN = 'discord_token'
# 環境変数名 -> secrets/ のファイル名
DB_SECRETS = {
    'PKDB_PASSWORD': 'pkdb_password',
    'UBSLEEPY_DB_PASSWORD': 'ubsleepy_db_password',
}
STATE_DIRECTORIES = ('save', 'log', 'resource/image')
STATE_FILES = ('config.json', 'resource/pokemon_senryu.csv')
STAMP = re.compile(r'^\d{8}T\d{6}Z\.tar\.gz$')


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, text=True, check=True, **kwargs)


def settings():
    return dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)


def secret(name):
    path = ROOT / 'secrets' / name
    return path.read_text().strip() if path.exists() else ''


def compose(*args, **kwargs):
    cmd = ['docker', 'compose', '--env-file', str(ROOT / '.env'), '-f', 'compose.yaml']
    if (ROOT / 'compose.lock.yaml').exists():
        cmd += ['-f', 'compose.lock.yaml']
    if (ROOT / 'compose.test.yaml').exists() and settings().get('UBSLEEPY_TEST') == 'true':
        cmd += ['-f', 'compose.test.yaml']
    # config と pull は値を使わないので、秘密が無くても通るよう仮の値を渡す。
    env = dict(os.environ, DISCORD_TOKEN=secret(TOKEN) or 'unset')
    env.update({name: secret(file) or 'unset' for name, file in DB_SECRETS.items()})
    return run(cmd + list(args), env=env, **kwargs)


def storage():
    configured = Path(settings().get('STORAGE_ROOT', '/srv/ubsleepy-next'))
    path = configured.resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('STORAGE_ROOT must not contain the deployment directory')
    return path


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
    print('CHANGED: ubsleepy-next initialized' if changed else 'OK: ubsleepy-next already initialized')


def missing_state():
    paths = [state() / name for name in STATE_DIRECTORIES + STATE_FILES]
    return [str(path) for path in paths if not path.exists()]


def up():
    for name in (TOKEN, *DB_SECRETS.values()):
        if not secret(name):
            raise ValueError(f'secrets/{name} is missing')
    missing = missing_state()
    if missing:
        # Starting without the save data would let the bot begin from nothing.
        raise ValueError(f'Save data is missing: {", ".join(missing)}')
    compose('pull')
    compose('up', '-d', '--remove-orphans')


def state_files():
    root = state()
    return sorted(path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file())


def digest():
    """Print `sha256  path` for every save file, like sha256sum, sorted by path."""
    root = state()
    for name in state_files():
        print(f'{hashlib.sha256((root / name).read_bytes()).hexdigest()}  {name}')


def deploy(commit):
    """指定コミットのイメージへ更新して起動する（digestを解決してlockを書き換え）。"""
    if not commit:
        raise ValueError('usage: manage.py deploy <commit>')
    image = f'{IMAGE}:{commit}'
    run(['docker', 'pull', image], capture_output=True)
    output = run(
        ['docker', 'inspect', '--format', '{{index .RepoDigests 0}}', image],
        capture_output=True).stdout.strip()
    digest = output.split('@', 1)[1]
    lock = (
        f'# この digest は {image}\n'
        f'# （main のマージコミット）を GitHub Actions がビルドしたもの。\n'
        f'# イメージを更新するときは、新しいコミットの digest へ書き換えて再配備する。\n'
        f'services:\n'
        f'  bot:\n'
        f'    image: {IMAGE}@{digest}\n'
    )
    (ROOT / 'compose.lock.yaml').write_text(lock, encoding='utf-8')
    compose('pull')
    compose('up', '-d', '--remove-orphans')
    print(f'deployed {commit}')
    print(lock)


def backup(destination, keep):
    """Archive the save data. The destination must be outside the state."""
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
    print(f'ubsleepy backup complete: {target}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'up', 'down', 'status', 'digest',
                                           'backup', 'deploy'])
    parser.add_argument('commit', nargs='?', help='deploy するコミットID')
    parser.add_argument('--destination', default=str(storage() / 'backups'),
                        help='backup destination directory')
    parser.add_argument('--keep', type=int, default=14, help='backups to keep')
    args = parser.parse_args()
    if args.action == 'init':
        init()
    elif args.action == 'up':
        up()
    elif args.action == 'down':
        compose('down')
    elif args.action == 'status':
        compose('ps')
    elif args.action == 'backup':
        backup(args.destination, args.keep)
    elif args.action == 'deploy':
        deploy(args.commit)
    else:
        digest()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        detail = getattr(error, 'stderr', '') or ''
        print(f'ERROR: {error}{": " + detail.strip() if detail else ""}', file=sys.stderr)
        sys.exit(1)
