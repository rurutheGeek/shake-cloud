#!/usr/bin/env python3
"""Serve the poke-translate site on apps-01. Run with sudo.

The implementation lives in the public repository rurutheGeek/poke-translate.
Ansible downloads a release archive (version and sha256 pinned in the role
defaults) and ``install`` unpacks it into ``STORAGE_ROOT/site``: only files
whose content changed are replaced, and files that are not in the archive are
removed, so the static server never sees a half-written site.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parent
# Files the site must contain; a release without them is refused.
REQUIRED = {'index.html', 'poketr.js', 'dictionary.json', 'poke-translate-extension.zip'}


def settings():
    return dict(line.split('=', 1) for line in (ROOT / '.env').read_text(encoding='utf-8').splitlines()
                if line and not line.startswith('#') and '=' in line)


def storage():
    path = Path(settings().get('STORAGE_ROOT', '/srv/poke-translate')).resolve()
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
    site = storage() / 'site'
    site.mkdir(mode=0o755, parents=True, exist_ok=True)


def read_release(archive):
    """Return {name: bytes} for the flat files of a release tarball."""
    files = {}
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar.getmembers():
            name = member.name
            if not member.isfile() or '/' in name or name.startswith('.'):
                raise ValueError(f'unexpected entry in release archive: {name}')
            files[name] = tar.extractfile(member).read()
    missing = REQUIRED - set(files)
    if missing:
        raise ValueError(f'release archive lacks {sorted(missing)}')
    return files


def install(archive):
    files = read_release(archive)
    site = storage() / 'site'
    site.mkdir(mode=0o755, parents=True, exist_ok=True)
    changed = False
    for name, data in sorted(files.items()):
        path = site / name
        if path.exists() and path.read_bytes() == data:
            continue
        temporary = site / f'.{name}.tmp'
        temporary.write_bytes(data)
        temporary.chmod(0o644)
        temporary.replace(path)
        changed = True
    for path in site.iterdir():
        if path.name not in files:
            path.unlink()
            changed = True
    print(f'{"CHANGED" if changed else "OK"}: site installed from {Path(archive).name}')


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
    parser.add_argument('action', choices=['init', 'install', 'lock', 'up', 'status', 'down'])
    parser.add_argument('archive', nargs='?', help='release tarball for install')
    args = parser.parse_args()
    if args.action == 'init':
        init()
    elif args.action == 'install':
        if not args.archive:
            parser.error('install requires the release tarball')
        install(args.archive)
    elif args.action == 'lock':
        lock()
    elif args.action == 'up':
        init()
        lock()
        compose('up', '-d', '--remove-orphans', '--wait', '--wait-timeout', '120')
    elif args.action == 'status':
        compose('ps')
    elif args.action == 'down':
        compose('down')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, tarfile.TarError,
            subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
