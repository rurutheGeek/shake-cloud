#!/usr/bin/env python3
"""Build and serve the Pokémon-aware translator.

``build`` writes the dictionary, the static translation site under
``STORAGE_ROOT/site`` (``./storage`` when there is no .env) and the browser extension (``extension/`` plus a zip for
phones).  The PokéAPI download is cached in ``STORAGE_ROOT/pokeapi.json`` and kept
unless ``--refresh`` is given, so rebuilding never changes official names
silently; custom-terms.json is always applied fresh.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import dictionary

ROOT = Path(__file__).resolve().parent
EXTENSION = ROOT / 'extension'
ZIP_NAME = 'poke-translate-extension.zip'
# 辞書の元データの版。更新するときはここを変えて ``build --refresh`` する。
POKEAPI_REF = '168b1e89467054cda2e7df43ccebbb69b459497a'
# 拡張機能に同梱する生成物（Git管理外）。
GENERATED = ['poketr.js', 'dictionary.json']


def settings():
    env = ROOT / '.env'
    if not env.exists():
        return {}
    return dict(line.split('=', 1) for line in env.read_text(encoding='utf-8').splitlines()
                if line and not line.startswith('#') and '=' in line)


def storage():
    """配備先は .env の STORAGE_ROOT。.env が無い手元では ./storage に作る。"""
    configured = settings().get('STORAGE_ROOT')
    if not configured:
        return ROOT / 'storage'
    path = Path(configured).resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('STORAGE_ROOT must not contain the deployment directory')
    return path


def compose(*args, locked=True, capture_output=False):
    command = ['docker', 'compose', '--env-file', str(ROOT / '.env'),
               '-f', str(ROOT / 'compose.yaml')]
    if locked and (ROOT / 'compose.lock.yaml').exists():
        command += ['-f', str(ROOT / 'compose.lock.yaml')]
    return subprocess.run(command + list(args), cwd=ROOT, check=True, text=True,
                          capture_output=capture_output)


def init():
    env = ROOT / '.env'
    if not env.exists():
        shutil.copyfile(ROOT / '.env.example', env)
    env.chmod(0o600)
    storage().mkdir(mode=0o755, parents=True, exist_ok=True)


def write(path, data):
    """中身が変わったときだけ置き換え、置き換えたかを返す。"""
    if path.exists() and path.read_bytes() == data:
        return False
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(data)
    temporary.chmod(0o644)
    temporary.replace(path)
    return True


def extension_zip():
    """同じ中身なら同じバイト列になるよう、時刻と順序を固定して zip にする。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(EXTENSION.iterdir()):
            if path.is_file() and not path.name.endswith('.tmp'):
                info = zipfile.ZipInfo(path.name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, path.read_bytes())
    return buffer.getvalue()


def build(refresh=False, ref=POKEAPI_REF):
    state = storage()
    state.mkdir(mode=0o755, parents=True, exist_ok=True)
    pokeapi, site = state / 'pokeapi.json', state / 'site'
    if refresh or not pokeapi.exists():
        base = dictionary.fetch_pokeapi(ref)
        write(pokeapi, json.dumps(base, ensure_ascii=False).encode('utf-8'))
        print(f'CHANGED: {len(base["entries"])} official terms from {base["source"]}')
    base = json.loads(pokeapi.read_text(encoding='utf-8'))
    custom = json.loads((ROOT / 'custom-terms.json').read_text(encoding='utf-8'))
    built = json.dumps(dictionary.build(base, custom), ensure_ascii=False,
                       separators=(',', ':')).encode('utf-8')
    core = (ROOT / 'core/poketr.js').read_bytes()

    changed = [write(EXTENSION / name, data)
               for name, data in [('poketr.js', core), ('dictionary.json', built)]]
    site.mkdir(mode=0o755, exist_ok=True)
    changed += [write(site / name, data)
                for name, data in [('index.html', (ROOT / 'site/index.html').read_bytes()),
                                   ('poketr.js', core), ('dictionary.json', built)]]
    # スマホのブラウザは zip から読み込むので、同じ中身をまとめて配る。
    changed.append(write(site / ZIP_NAME, extension_zip()))
    digest = hashlib.sha256(built).hexdigest()[:12]
    status = 'CHANGED' if any(changed) else 'OK'
    print(f'{status}: site and extension built (dictionary {digest})')


def lock():
    lockfile = ROOT / 'compose.lock.yaml'
    if lockfile.exists():
        print('OK: existing image digests preserved')
        return
    compose('pull', locked=False)
    rendered = json.loads(compose('config', '--format', 'json', locked=False,
                                  capture_output=True).stdout)
    services = {}
    for name, service in rendered['services'].items():
        inspected = json.loads(subprocess.check_output(
            ['docker', 'image', 'inspect', service['image']], text=True))[0]
        if not inspected.get('RepoDigests'):
            raise RuntimeError(f'Image has no repository digest: {name}')
        services[name] = {'image': inspected['RepoDigests'][0]}
    lockfile.write_text(json.dumps({'services': services}, indent=2) + '\n', encoding='utf-8')
    print('CHANGED: image digests pinned in compose.lock.yaml')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'build', 'lock', 'up', 'status', 'down'])
    parser.add_argument('--refresh', action='store_true', help='PokéAPI から取り直す')
    parser.add_argument('--ref', default=POKEAPI_REF, help='PokéAPI の commit')
    args = parser.parse_args()
    if args.action == 'init':
        init()
    elif args.action == 'build':
        build(args.refresh, args.ref)
    elif args.action == 'lock':
        lock()
    elif args.action == 'up':
        init()
        build()
        lock()
        compose('up', '-d', '--remove-orphans', '--wait', '--wait-timeout', '120')
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
