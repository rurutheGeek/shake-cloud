#!/usr/bin/env python3
"""Deploy FreshRSS as an independent Compose project on media-01.

Secrets (the OIDC client and the generated passwords) are passed to Compose as
environment variables, never written to .env. The SharedFeeds system extension
is enabled in data/config.php after the container is healthy.
"""
import argparse
import datetime
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GENERATED_SECRETS = ('default_password', 'default_api_password', 'oidc_crypto_key')
OIDC_SECRET_FILE = 'oidc_client.json'
# data/config.php を壊さずに SharedFeeds をシステム拡張として有効化する。
ENABLE_EXTENSION = r'''
$path = '/var/www/FreshRSS/data/config.php';
if (!is_file($path)) {
    fwrite(STDERR, "config.php is missing\n");
    exit(2);
}
$config = include $path;
if (!is_array($config)) {
    fwrite(STDERR, "config.php did not return an array\n");
    exit(3);
}
$enabled = is_array($config['extensions_enabled'] ?? null) ? $config['extensions_enabled'] : [];
if (($enabled['SharedFeeds'] ?? false) === true) {
    echo "OK: SharedFeeds enabled\n";
    exit(0);
}
$enabled['SharedFeeds'] = true;
$config['extensions_enabled'] = $enabled;
if (file_put_contents($path, "<?php\n return " . var_export($config, true) . ";\n") === false) {
    fwrite(STDERR, "cannot write config.php\n");
    exit(4);
}
if (function_exists('opcache_reset')) {
    opcache_reset();
}
echo "CHANGED: SharedFeeds enabled\n";
'''


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


def secret(name):
    path = ROOT / 'secrets' / name
    return path.read_text().strip() if path.exists() else ''


def oidc_client():
    path = ROOT / 'secrets' / OIDC_SECRET_FILE
    return json.loads(path.read_text()) if path.exists() else {}


def compose(*args, locked=True, capture_output=False):
    command = ['docker', 'compose', '--env-file', str(ROOT / '.env'),
               '-f', str(ROOT / 'compose.yaml')]
    if locked and (ROOT / 'compose.lock.yaml').exists():
        command += ['-f', str(ROOT / 'compose.lock.yaml')]
    environment = dict(os.environ)
    # Shell variables must not silently change .env paths.
    environment.update(settings())
    # Secrets travel to the container only through the environment.
    oidc = oidc_client()
    has_oidc = bool(oidc.get('client_secret'))
    environment.update({
        'FRESHRSS_OIDC_ENABLED': '1' if has_oidc else '0',
        'FRESHRSS_OIDC_CLIENT_ID': oidc.get('client_id', ''),
        'FRESHRSS_OIDC_CLIENT_SECRET': oidc.get('client_secret', ''),
        'FRESHRSS_OIDC_CRYPTO_KEY': secret('oidc_crypto_key'),
        'FRESHRSS_DEFAULT_PASSWORD': secret('default_password'),
        'FRESHRSS_DEFAULT_API_PASSWORD': secret('default_api_password'),
    })
    return subprocess.run(command + list(args), cwd=ROOT, check=True, text=True,
                          env=environment, capture_output=capture_output)


def state():
    """Return the FreshRSS state directory that a cold backup archives."""
    config = settings()
    return Path(config.get('STORAGE_ROOT', '/srv/media-stack/storage')) / 'freshrss'


def run(args):
    return subprocess.run(args, cwd=ROOT, check=True)


def init():
    env = ROOT / '.env'
    if not env.exists():
        env.write_bytes((ROOT / '.env.example').read_bytes())
    env.chmod(0o600)
    config = settings()
    uid = int(config.get('MEDIA_UID', 33))
    gid = int(config.get('MEDIA_GID', 33))
    storage = state()
    data = storage / 'data'
    for path in (storage, data):
        if not path.exists():
            path.mkdir(parents=True, mode=0o750)
        if (path.stat().st_uid, path.stat().st_gid) != (uid, gid):
            if os.geteuid() != 0:
                raise PermissionError(f'Run init with sudo to own {path} as {uid}:{gid}')
            os.chown(path, uid, gid)
    # 新規ユーザーへ既定フィードを入れない。FreshRSS は data/opml.xml があれば
    # それを使うので、空の OPML を置く。共通リストは SharedFeeds 拡張が初回
    # ログイン時に配る（既定フィードがあると「購読が空」と見なされず配られない）。
    default_opml = data / 'opml.xml'
    if not default_opml.exists():
        default_opml.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<opml version="2.0"><head><title>shake-cloud default feeds</title></head>'
            '<body></body></opml>\n', encoding='utf-8')
        if os.geteuid() == 0:
            os.chown(default_opml, uid, gid)
        default_opml.chmod(0o644)
    directory = ROOT / 'secrets'
    directory.mkdir(exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    for name in GENERATED_SECRETS:
        target = directory / name
        if not target.exists():
            with target.open('x') as file:
                file.write(secrets.token_urlsafe(40) + '\n')
        if not target.read_text().strip():
            raise ValueError(f'Empty secret: {name}')
        target.chmod(0o400)
    print('OK: FreshRSS data and secrets are ready')


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


def configure():
    """Enable the SharedFeeds system extension in data/config.php (idempotent)."""
    result = compose('exec', '-T', 'freshrss', 'php', '-r', ENABLE_EXTENSION,
                     capture_output=True)
    print(result.stdout.strip())


def seed():
    """Import the starter feeds once, into the default (admin) user.

    Later additions and removals happen in the FreshRSS UI and are shared by
    the extension. The marker keeps a redeploy from re-adding feeds someone
    deliberately removed.
    """
    marker = ROOT / 'secrets' / 'feeds_seeded'
    if marker.exists():
        print('OK: starter feeds already imported')
        return
    user = settings().get('FRESHRSS_DEFAULT_USER', 'akadmin')
    data = state() / 'data'
    shutil.copyfile(ROOT / 'feeds.opml', data / 'seed.opml')
    os.chmod(data / 'seed.opml', 0o644)
    compose('exec', '-T', '--user', 'www-data', 'freshrss',
            'cli/import-for-user.php', '--user', user,
            '--filename', '/var/www/FreshRSS/data/seed.opml')
    marker.write_text('seeded\n')
    marker.chmod(0o400)
    print('CHANGED: starter feeds imported')


def up():
    lock()
    compose('config', '--quiet')
    compose('up', '-d', '--wait', '--wait-timeout', '180')
    configure()
    seed()


def backup(destination):
    if os.geteuid() != 0:
        raise PermissionError('Run backup with sudo to read all application state')
    storage = state()
    destination = Path(destination).resolve()
    if destination == storage or storage in destination.parents:
        raise ValueError('Backup destination must be outside the state directory')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = destination / (stamp + '.incomplete')
    target.mkdir(mode=0o700)
    running = compose('ps', '--services', '--status', 'running',
                      capture_output=True).stdout.split()
    # Cold snapshot: the SQLite data is cleanly stopped before copying.
    try:
        compose('stop', '--timeout', '120')
        run(['tar', '--numeric-owner', '-cpf', str(target / 'state.tar'),
             '-C', str(storage), '.'])
        run(['tar', '--numeric-owner', '-cpf', str(target / 'deployment.tar'),
             'compose.yaml', 'compose.lock.yaml', '.env', '.env.example',
             'manage.py', 'extensions', 'secrets', 'feeds.opml'])
        (target / 'manifest.json').write_text(json.dumps({
            'storage_root': str(storage),
            'created_utc': stamp,
            'architecture': os.uname().machine,
            'format': 1,
            'notes': 'Cold backup of FreshRSS state (data + SQLite databases) and '
                     'the deployment (Compose, SharedFeeds extension, secrets). '
                     'Restore on the same CPU architecture, with services stopped, '
                     'into a new or empty directory; do not overwrite a live one.',
        }, indent=2) + '\n')
    finally:
        if running:
            compose('start', *running)
    complete = target.with_suffix('')
    target.rename(complete)
    print(f'Backup complete: {complete}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',
                        choices=['init', 'lock', 'up', 'configure', 'seed', 'status', 'down', 'backup'])
    parser.add_argument('--destination', default=str(ROOT / 'backups'))
    args = parser.parse_args()
    if args.action in ('init', 'up', 'configure', 'seed'):
        init()
    if args.action == 'lock':
        lock()
    elif args.action == 'up':
        up()
    elif args.action == 'configure':
        configure()
    elif args.action == 'seed':
        seed()
    elif args.action == 'status':
        compose('ps')
    elif args.action == 'down':
        compose('down')
    elif args.action == 'backup':
        backup(args.destination)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
