#!/usr/bin/env python3
"""Shelve loose book files into a folder per title so Kavita sees them.

Kavita treats each folder in a library as a series and ignores files that sit
directly in the library root. This keeps `books/` usable as a drop target:
each loose book becomes `books/<title>/<file>` and Kavita's folder watching
picks it up. Runs from a systemd timer on media-01.
"""
import argparse
import json
import os
import time
from pathlib import Path

BOOK_EXTENSIONS = {'.pdf', '.epub', '.cbz', '.cbr', '.cb7', '.mobi', '.azw3', '.fb2'}
SETTLE_SECONDS = 120


def trigger_scan(kavita_dir, timeout=60):
    """Ask Kavita to scan the Books library after files were shelved.

    Kavita's folder watcher logs "could not find root level folder" and ignores
    the rename events on this bind mount (2026-09-13), so trigger the scan that
    the web UI would run.
    """
    try:
        import requests
    except ImportError:
        print('SCAN: skipped (python3-requests is not installed)')
        return
    root = Path(kavita_dir)
    accounts_path = root / 'secrets' / 'accounts.json'
    env_path = root / '.env'
    if not accounts_path.exists() or not env_path.exists():
        print('SCAN: skipped (Kavita credentials are not deployed yet)')
        return
    env = {}
    for line in env_path.read_text().splitlines():
        if '=' in line and not line.strip().startswith('#'):
            key, _, value = line.partition('=')
            env[key.strip()] = value.strip()
    base = 'http://127.0.0.1:' + env.get('KAVITA_PORT', '5000')
    session = requests.Session()
    try:
        result = session.post(base + '/api/Account/login',
                              json=json.loads(accounts_path.read_text()), timeout=timeout)
        result.raise_for_status()
        session.headers['Authorization'] = 'Bearer ' + result.json()['token']
        libraries = session.get(base + '/api/Library/libraries', timeout=timeout).json()
        library = next((row for row in libraries if row.get('name') == 'Books'), None)
        if library is None:
            print('SCAN: skipped (Books library not found)')
            return
        result = session.post(base + '/api/Library/scan',
                              params={'libraryId': library['id'], 'force': 'false'},
                              timeout=timeout)
        result.raise_for_status()
        print(f"SCAN: triggered (library {library['id']})")
    except (OSError, ValueError, requests.RequestException) as error:
        print(f'SCAN: failed ({error})')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--books', default=os.environ.get('KAVITA_BOOKS_DIR', '/books'))
    parser.add_argument('--settle-seconds', type=int, default=SETTLE_SECONDS)
    parser.add_argument('--kavita-dir', default=None,
                        help='Kavita deployment directory (.env + secrets/accounts.json)')
    args = parser.parse_args()

    root = Path(args.books)
    if not root.is_dir():
        print(f'ERROR: {root} is not a directory')
        return 1

    moved = False
    now = time.time()
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in BOOK_EXTENSIONS:
            continue
        if now - path.stat().st_mtime < args.settle_seconds:
            print(f'SKIP (still uploading): {path.name}')
            continue
        folder = root / path.stem
        if folder.exists() and not folder.is_dir():
            print(f'SKIP (name taken by a file): {folder.name}')
            continue
        try:
            folder.mkdir(exist_ok=True)
            stat = path.stat()
            os.chown(folder, stat.st_uid, stat.st_gid)
            os.chmod(folder, 0o755)
        except OSError as error:
            print(f'ERROR: cannot prepare {folder.name}: {error}')
            continue
        target = folder / path.name
        if target.exists():
            print(f'SKIP (already shelved): {target}')
            continue
        path.rename(target)
        moved = True
        print(f'CHANGED: {path.name} -> {folder.name}/')

    if moved and args.kavita_dir:
        trigger_scan(args.kavita_dir)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
