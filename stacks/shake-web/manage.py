#!/usr/bin/env python3
"""Shake-Web（公開サイト）の配備。web-01 で sudo で動かす。

旧 shakeserver（Raspberry Pi 5）では Ansible が git clone と rsync を行っていた。
ここでは同じ流れを ``fetch``（4リポジトリを固定した ref へ更新）と
``sync``（nginx が配る静的物を写す）に分け、``up`` がビルドして起動する。
秘密値（Deploy key・DB のパスワード）は role が SOPS から置く。
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
DEFAULT_STORAGE = '/srv/shake-web'

# リポジトリ → (URL, 鍵ファイル, .env で ref を上書きする変数, 既定の ref)
REPOS = {
    'shake-web': (
        'git@github.com:rurutheGeek/shake-web.git',
        ROOT / 'secrets/id_shake_web',
        'SHAKE_WEB_REF', 'main',
    ),
    'pkhack': (
        'git@github.com:rurutheGeek/pkhack.git',
        ROOT / 'secrets/id_pkhack',
        'PKHACK_REF', 'main',
    ),
    'pokebs_alexaskill': (
        'https://github.com/rurutheGeek/pokebs_alexaskill.git',
        None,
        'ALEXA_REF', 'main',
    ),
    'ayahuya': (
        'git@github.com:rurutheGeek/ayahuya.git',
        ROOT / 'secrets/id_ayahuya',
        'AYAHUYA_REF', 'main',
    ),
}

# nginx が配る静的物（src 内のパス → STORAGE_ROOT 内のパス）。
STATIC = {
    'shake-web/html': 'html',
    'pkhack/html': 'pkhack/html',
    'ayahuya/html': 'ayahuya/html',
}


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, text=True, check=True, **kwargs)


def settings():
    return dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)


def storage():
    path = Path(settings().get('STORAGE_ROOT', DEFAULT_STORAGE)).resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('STORAGE_ROOT must not contain the deployment directory')
    return path


def compose(*args):
    return run(['docker', 'compose', '--env-file', str(ROOT / '.env'), '-f', 'compose.yaml'] + list(args),
               capture_output=True)


def git(repo, args, key=None):
    env = dict(os.environ)
    if key is not None:
        env['GIT_SSH_COMMAND'] = (
            f'ssh -i {key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new')
    return run(['git', '-C', str(repo)] + list(args), env=env, capture_output=True)


def init():
    """保存先と、マウント済みデータディスクの確認。秘密値は role が置く。"""
    path = storage()
    # データディスクは /srv にマウントする（保存先はその下）。保存先そのものが
    # マウント点でなければ、一番近いマウント点まで親をたどって確かめる。
    probe = path
    while probe != probe.parent and not os.path.ismount(probe):
        probe = probe.parent
    if not os.path.ismount(probe):
        sys.exit(f'{probe} is not a mount point; refusing to deploy (data disk?)')
    changed = False
    for directory in ('src', 'html', 'pkhack/html', 'ayahuya/html',
                      'alexa/logs', 'log', 'certs', 'templates'):
        target = path / directory
        if not target.exists():
            target.mkdir(parents=True)
            changed = True
    print('CHANGED: shake-web initialized' if changed else 'OK: shake-web already initialized')


def fetch():
    """4リポジトリを .env の ref へ合わせる。変わったものだけ CHANGED を出す。"""
    path = storage()
    conf = settings()
    changed = []
    for name, (url, key, ref_var, default_ref) in REPOS.items():
        ref = conf.get(ref_var, default_ref) or default_ref
        target = path / 'src' / name
        if not (target / '.git').exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            run(['git', 'clone', '--branch', ref, url, str(target)],
                env={**os.environ, **({'GIT_SSH_COMMAND':
                     f'ssh -i {key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'}
                     if key else {})})
            changed.append(name)
            continue
        before = git(target, ['rev-parse', 'HEAD']).stdout.strip()
        git(target, ['fetch', '--prune', 'origin'], key=key)
        git(target, ['checkout', '--force', ref], key=key)
        git(target, ['reset', '--hard', f'origin/{ref}'], key=key)
        after = git(target, ['rev-parse', 'HEAD']).stdout.strip()
        if before != after:
            changed.append(name)
    print(f'CHANGED: updated {", ".join(changed)}' if changed else 'OK: every repository is current')


def sync():
    """ビルド元と nginx の静的物を用意する。rsync が無ければ cp で写す。"""
    path = storage()
    changed = []
    for source, destination in STATIC.items():
        src = path / 'src' / source
        dest = path / destination
        if not src.is_dir():
            sys.exit(f'{src} is missing; run fetch first')
        dest.mkdir(parents=True, exist_ok=True)
        if shutil.which('rsync'):
            result = run(['rsync', '-a', '--delete', '--exclude=.git', f'{src}/', f'{dest}/'],
                         capture_output=True)
            if result.stdout or result.stderr:
                pass
        else:
            shutil.copytree(src, dest, dirs_exist_ok=True)
        changed.append(source)
    # 変化の検知は rsync の出力では当てにできない。常に写して OK を出す。
    print(f'OK: synced {", ".join(changed)}')


def up():
    result = compose('up', '-d', '--build')
    changed = any(word in (result.stdout + result.stderr)
                  for word in ('Created', 'Recreated', 'Started'))
    print('CHANGED: containers up' if changed else 'OK: containers already current')


def status():
    result = compose('ps')
    print(result.stdout, end='')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'fetch', 'sync', 'up', 'status'])
    args = parser.parse_args()
    globals()[args.action]()


if __name__ == '__main__':
    main()
