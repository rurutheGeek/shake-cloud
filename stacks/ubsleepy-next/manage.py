#!/usr/bin/env python3
"""UBSLEEPY（-next）の運用。Run with sudo.

配備はAnsible（platform/ansible/ubsleepy-next.yml）が行う。ここは状態の確認や
手元操作のためのもの。イメージは compose.lock.yaml の digest（GitHub Actions が
main のマージ時に出すコミットIDタグのもの）を使い、apps-01 ではビルドしない。
セーブデータは STORAGE_ROOT/state からコンテナへ重ねる。
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SERVICE = 'bot'
TOKEN = 'discord_token'
# 環境変数名 -> secrets/ のファイル名
DB_SECRETS = {
    'PKDB_PASSWORD': 'pkdb_password',
    'UBSLEEPY_DB_PASSWORD': 'ubsleepy_db_password',
}
STATE_DIRECTORIES = ('save', 'log', 'resource/image')
STATE_FILES = ('config.json', 'resource/pokemon_senryu.csv')


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'up', 'down', 'status', 'digest'])
    args = parser.parse_args()
    if args.action == 'init':
        init()
    elif args.action == 'up':
        up()
    elif args.action == 'down':
        compose('down')
    elif args.action == 'status':
        compose('ps')
    else:
        digest()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        detail = getattr(error, 'stderr', '') or ''
        print(f'ERROR: {error}{": " + detail.strip() if detail else ""}', file=sys.stderr)
        sys.exit(1)
