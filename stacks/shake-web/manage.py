#!/usr/bin/env python3
"""Shake-Web（公開サイト）の配備。shakeserver（Pi 5）で sudo で動かす。

アプリと静的物は、すべて各リポジトリの CI がビルドしたイメージ（GHCR）で、
``pull`` が取ってきて ``up`` が起動する。ホストではソースを取らず、ビルドもしない。
秘密値（DB のパスワードなど）は role が SOPS から置く。
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
DEFAULT_STORAGE = '/srv/shake-web'

# 各リポジトリの CI がビルドしたイメージ（GHCR）を使うサービス。タグ（main）を追う。
PULLED_SERVICES = ['quiz_app', 'pkhack_app', 'alexa_skill', 'ayahuya',
                   'shake_static', 'pkhack_static']


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


# レジストリのイメージ（compose.lock.yaml で digest を固定するもの）。
# 自作のイメージ（PULLED_SERVICES）は対象外。
REGISTRY_IMAGES = {
    'web': 'nginx:1.27-alpine',
}


def compose(*args):
    cmd = ['docker', 'compose', '--env-file', str(ROOT / '.env'), '-f', 'compose.yaml']
    if (ROOT / 'compose.lock.yaml').exists():
        cmd += ['-f', 'compose.lock.yaml']
    return run(cmd + list(args), capture_output=True)


def lock():
    """レジストリのイメージを pull し、digest を compose.lock.yaml へ固定する。"""
    import json
    locked = {'services': {}}
    for service, image in REGISTRY_IMAGES.items():
        run(['docker', 'pull', image], capture_output=True)
        digest = run(['docker', 'inspect', '--format', '{{index .RepoDigests 0}}', image],
                     capture_output=True).stdout.strip()
        repository = image.split(':')[0]
        if not digest.startswith(repository + '@'):
            sys.exit(f'{image}: unexpected digest {digest}')
        locked['services'][service] = {'image': digest}
    (ROOT / 'compose.lock.yaml').write_text(json.dumps(locked, indent=2) + '\n')
    print('CHANGED: image digests pinned in compose.lock.yaml')


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
    for directory in ('alexa/logs', 'log', 'certs', 'templates'):
        target = path / directory
        if not target.exists():
            target.mkdir(parents=True)
            changed = True
    print('CHANGED: shake-web initialized' if changed else 'OK: shake-web already initialized')


def image_ids():
    result = compose('images', '--quiet', *PULLED_SERVICES)
    return set(result.stdout.split())


def pull():
    """CI がビルドしたイメージを取ってくる。新しいイメージが来たら CHANGED を出す。"""
    before = image_ids()
    compose('pull', '--quiet', *PULLED_SERVICES)
    ids = []
    for service in PULLED_SERVICES:
        image = compose('config', '--images', service).stdout.strip()
        ids.append(run(['docker', 'image', 'inspect', '--format', '{{.Id}}', image],
                       capture_output=True).stdout.strip())
    changed = [s for s, i in zip(PULLED_SERVICES, ids) if i not in before]
    print(f'CHANGED: pulled {", ".join(changed)}' if changed else 'OK: every image is current')


def up():
    result = compose('up', '-d')
    output = result.stdout + result.stderr
    changed = any(word in output for word in ('Created', 'Recreated', 'Started'))
    if changed:
        # nginx は upstream（pkhack_app など）の名前を起動時に一度だけ解決する。
        # アプリを作り直すと IP が変わり、古い IP のままだと別コンテナへ届いて
        # 404 になる（2026-10-05 に発生）。作り直したら web も再起動する。
        compose('restart', 'web')
    print('CHANGED: containers up' if changed else 'OK: containers already current')


def status():
    result = compose('ps')
    print(result.stdout, end='')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'pull', 'lock', 'up', 'status'])
    args = parser.parse_args()
    globals()[args.action]()


if __name__ == '__main__':
    main()
