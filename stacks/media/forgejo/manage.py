#!/usr/bin/env python3
"""Deploy Forgejo (the repository archive) as an independent Compose project on media-01.

Secrets are passed to Compose as environment variables, never written to .env.
After the container is healthy, `up` reconciles the Authentik login source, the
local administrator the API calls use, the archive organization and the pull
mirrors listed in mirrors.json. Removing a mirror from the list never deletes
the repository: keeping it is the point of the archive.

A pull mirror only carries git data. For entries with "issues": true, `issues`
copies the GitHub issues and their comments into a plain repository next to the
mirror (`<name>-issues`), one Markdown file to read and one JSON file to restore
from per issue. Issues that disappear upstream stay in the copy.
"""
import base64
import argparse
import datetime
import json
import os
import secrets
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GENERATED_SECRETS = ('secret_key', 'internal_token', 'jwt_secret', 'admin_password')
OIDC_SECRET_FILE = 'oidc_client.json'
TOKEN_FILE = 'admin_token'
# 管理用のローカル利用者。人は Authentik から入り、admins グループが管理者になる。
ADMIN_USER = 'shakecloud'
ADMIN_EMAIL = 'shakecloud@localhost'
AUTH_SOURCE = 'authentik'
TOKEN_SCOPES = 'write:repository,write:organization,read:user'


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


def compose(*args, locked=True, capture_output=False, check=True):
    command = ['docker', 'compose', '--env-file', str(ROOT / '.env'),
               '-f', str(ROOT / 'compose.yaml')]
    if locked and (ROOT / 'compose.lock.yaml').exists():
        command += ['-f', str(ROOT / 'compose.lock.yaml')]
    environment = dict(os.environ)
    # Shell variables must not silently change .env paths.
    environment.update(settings())
    # Secrets travel to the container only through the environment.
    environment.update({
        'FORGEJO_SECRET_KEY': secret('secret_key'),
        'FORGEJO_INTERNAL_TOKEN': secret('internal_token'),
        'FORGEJO_JWT_SECRET': secret('jwt_secret'),
    })
    return subprocess.run(command + list(args), cwd=ROOT, check=check, text=True,
                          env=environment, capture_output=capture_output)


def forgejo(*args, check=True):
    """Run the forgejo CLI inside the container as the git user."""
    return compose('exec', '-T', '--user', 'git', 'forgejo', 'forgejo', *args,
                   capture_output=True, check=check)


def state():
    """Return the Forgejo state directory (repositories, SQLite, LFS)."""
    config = settings()
    return Path(config.get('STORAGE_ROOT', '/srv/media-stack/storage')) / 'forgejo'


def run(args):
    return subprocess.run(args, cwd=ROOT, check=True)


def init():
    env = ROOT / '.env'
    if not env.exists():
        env.write_bytes((ROOT / '.env.example').read_bytes())
    env.chmod(0o600)
    config = settings()
    uid = int(config.get('FORGEJO_UID', 1000))
    gid = int(config.get('FORGEJO_GID', 1000))
    storage = state()
    if not storage.exists():
        storage.mkdir(parents=True, mode=0o750)
    if (storage.stat().st_uid, storage.stat().st_gid) != (uid, gid):
        if os.geteuid() != 0:
            raise PermissionError(f'Run init with sudo to own {storage} as {uid}:{gid}')
        os.chown(storage, uid, gid)
    directory = ROOT / 'secrets'
    directory.mkdir(exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    for name in GENERATED_SECRETS:
        target = directory / name
        if not target.exists():
            with target.open('x') as file:
                # 32 bytes in URL-safe base64 is the form JWT_SECRET expects.
                file.write(secrets.token_urlsafe(32) + '\n')
        if not target.read_text().strip():
            raise ValueError(f'Empty secret: {name}')
        target.chmod(0o400)
    print('OK: Forgejo data and secrets are ready')


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


def auth_sources():
    """Return {name: id} from `forgejo admin auth list` (tab-padded columns)."""
    lines = forgejo('admin', 'auth', 'list').stdout.splitlines()
    sources = {}
    for line in lines[1:]:
        fields = line.split()
        if len(fields) >= 2 and fields[0].isdigit():
            sources[fields[1]] = fields[0]
    return sources


def configure_login():
    """Create or correct the Authentik login source once its secret is installed."""
    client = oidc_client()
    if not client.get('client_secret'):
        print('OK: OIDC secret not installed yet; run media-forgejo-sso.yml')
        return
    options = ['--provider', 'openidConnect',
               '--key', client['client_id'], '--secret', client['client_secret'],
               '--auto-discover-url', settings()['FORGEJO_OIDC_DISCOVERY_URL'],
               '--scopes', 'openid', '--scopes', 'email', '--scopes', 'profile',
               '--group-claim-name', 'groups', '--admin-group', 'admins',
               '--skip-local-2fa']
    existing = auth_sources().get(AUTH_SOURCE)
    if existing:
        forgejo('admin', 'auth', 'update-oauth', '--id', existing, '--name', AUTH_SOURCE, *options)
        print(f'OK: login source {AUTH_SOURCE} reconciled')
    else:
        forgejo('admin', 'auth', 'add-oauth', '--name', AUTH_SOURCE, *options)
        print(f'CHANGED: login source {AUTH_SOURCE} added')


def configure_admin():
    """Keep the local administrator and an API token for the mirror reconciler."""
    users = forgejo('admin', 'user', 'list', '--admin').stdout.split()
    if ADMIN_USER not in users:
        forgejo('admin', 'user', 'create', '--admin', '--username', ADMIN_USER,
                '--email', ADMIN_EMAIL, '--password', secret('admin_password'),
                '--must-change-password=false')
        print(f'CHANGED: administrator {ADMIN_USER} created')
    token = ROOT / 'secrets' / TOKEN_FILE
    if token.exists() and token.read_text().strip():
        return
    value = forgejo('admin', 'user', 'generate-access-token', '--username', ADMIN_USER,
                    '--token-name', 'manage-py', '--scopes', TOKEN_SCOPES, '--raw').stdout.strip()
    with token.open('x') as file:
        file.write(value + '\n')
    token.chmod(0o400)
    print('CHANGED: API token for manage.py stored')


def api(method, path, body=None):
    """Call the Forgejo API on loopback. Returns (status, parsed JSON or None)."""
    port = settings().get('FORGEJO_PORT', '8083')
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f'http://127.0.0.1:{port}/api/v1{path}', data=data, method=method,
        headers={'Authorization': 'token ' + secret(TOKEN_FILE),
                 'Content-Type': 'application/json', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return 404, None
        raise RuntimeError(f'{method} {path}: HTTP {error.code} {error.read()[:300]!r}') from error


def mirror_list():
    """Validate mirrors.json: [{"url": ..., "name"?: ..., "interval"?: ..., "wiki"?: bool, "lfs"?: bool, "issues"?: bool}]."""
    entries = json.loads((ROOT / 'mirrors.json').read_text())
    if not isinstance(entries, list):
        raise ValueError('mirrors.json must be a JSON list')
    names = set()
    for entry in entries:
        url = entry.get('url', '')
        if not url.startswith('https://'):
            raise ValueError(f'mirror url must be https: {url!r}')
        name = entry.get('name') or urllib.parse.urlsplit(url).path.rstrip('/').split('/')[-1].removesuffix('.git')
        if not name or name in names:
            raise ValueError(f'mirror name missing or duplicated: {name!r}')
        names.add(name)
        entry['name'] = name
        if entry.get('issues') and github_repository(url) is None:
            raise ValueError(f'issues can only be copied from github.com: {url!r}')
    return entries


def mirrors():
    """Create the archive organization and every listed mirror that is missing."""
    organization = settings().get('FORGEJO_ARCHIVE_ORG', 'archive')
    status, _ = api('GET', f'/orgs/{organization}')
    if status == 404:
        api('POST', '/orgs', {'username': organization, 'visibility': 'private'})
        print(f'CHANGED: organization {organization} created')
    for entry in mirror_list():
        name = entry['name']
        status, _ = api('GET', f'/repos/{organization}/{name}')
        if status != 404:
            print(f'OK: mirror {organization}/{name}')
            continue
        api('POST', '/repos/migrate', {
            'clone_addr': entry['url'], 'repo_owner': organization, 'repo_name': name,
            'mirror': True, 'mirror_interval': entry.get('interval', settings().get('FORGEJO_MIRROR_INTERVAL', '24h')),
            'private': True, 'wiki': bool(entry.get('wiki', True)), 'lfs': bool(entry.get('lfs', False)),
            'service': 'git',
        })
        print(f'CHANGED: mirror {organization}/{name} created from {entry["url"]}')


def github_repository(url):
    """'https://github.com/owner/repo(.git)' -> 'owner/repo', anything else -> None."""
    parts = urllib.parse.urlsplit(url)
    path = parts.path.strip('/').removesuffix('.git').split('/')
    if parts.netloc != 'github.com' or len(path) != 2 or not all(path):
        return None
    return '/'.join(path)


def github(path):
    """GET every page of a GitHub API list. Public repositories need no token."""
    items, page = [], 1
    while True:
        separator = '&' if '?' in path else '?'
        request = urllib.request.Request(
            f'https://api.github.com{path}{separator}per_page=100&page={page}',
            headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'shakecloud-forgejo'})
        with urllib.request.urlopen(request, timeout=60) as response:
            batch = json.loads(response.read())
        items.extend(batch)
        if len(batch) < 100:
            return items
        page += 1


def issue_files(issues, comments):
    """Render {path: text} for every issue (pull requests are left out)."""
    by_issue = {}
    for comment in comments:
        number = int(comment['issue_url'].rsplit('/', 1)[1])
        by_issue.setdefault(number, []).append(comment)
    files, index = {}, []
    for issue in sorted((i for i in issues if 'pull_request' not in i), key=lambda i: i['number']):
        number = issue['number']
        thread = sorted(by_issue.get(number, []), key=lambda c: c['created_at'])
        labels = ', '.join(label['name'] for label in issue.get('labels', []))
        lines = [f"# #{number} {issue['title']}", '',
                 f"- 状態: {issue['state']}" + (f"（{issue.get('state_reason')}）" if issue.get('state_reason') else ''),
                 f"- ラベル: {labels or 'なし'}",
                 f"- 作成: {issue['created_at']}（{issue['user']['login']}）",
                 f"- 閉じた日: {issue.get('closed_at') or '—'}",
                 f"- 元: {issue['html_url']}", '', issue.get('body') or '']
        for comment in thread:
            lines += ['', f"## {comment['user']['login']} {comment['created_at']}", '', comment.get('body') or '']
        stem = f'issues/{number:04d}'
        files[stem + '.md'] = '\n'.join(lines).rstrip() + '\n'
        files[stem + '.json'] = json.dumps({'issue': issue, 'comments': thread},
                                           ensure_ascii=False, indent=2, sort_keys=True) + '\n'
        index.append(f"| [#{number}]({stem}.md) | {issue['state']} | {issue['title']} | {labels} |")
    return files, index


def copy_issues(entry, organization):
    source = github_repository(entry['url'])
    name = entry['name'] + '-issues'
    status, _ = api('GET', f'/repos/{organization}/{name}')
    if status == 404:
        api('POST', f'/orgs/{organization}/repos', {
            'name': name, 'private': True, 'auto_init': True, 'default_branch': 'main',
            'description': f'Issues of https://github.com/{source}, copied daily by manage.py issues'})
        print(f'CHANGED: repository {organization}/{name} created')
    files, index = issue_files(github(f'/repos/{source}/issues?state=all'),
                               github(f'/repos/{source}/issues/comments'))
    # The index lists what exists upstream now; files of vanished issues stay.
    files['README.md'] = '\n'.join([
        f'# {source} の Issues の写し', '',
        f'元は https://github.com/{source}/issues 。Forgejo の manage.py issues が毎日写す。'
        '元で消えたものも、ここからは消さない。', '',
        '| 番号 | 状態 | 題 | ラベル |', '| --- | --- | --- | --- |', *index]) + '\n'
    changes = []
    for path, text in sorted(files.items()):
        status, current = api('GET', f'/repos/{organization}/{name}/contents/{path}?ref=main')
        encoded = base64.b64encode(text.encode()).decode()
        if status == 404:
            changes.append({'operation': 'create', 'path': path, 'content': encoded})
        elif base64.b64decode(current['content']).decode() != text:
            changes.append({'operation': 'update', 'path': path, 'content': encoded, 'sha': current['sha']})
    if not changes:
        print(f'OK: issues of {source} unchanged')
        return
    api('POST', f'/repos/{organization}/{name}/contents', {
        'branch': 'main', 'files': changes,
        'message': f'{source} の Issues を写す（{len(changes)} ファイル）'})
    print(f'CHANGED: {len(changes)} files of {source} issues copied to {organization}/{name}')


def issues():
    organization = settings().get('FORGEJO_ARCHIVE_ORG', 'archive')
    for entry in mirror_list():
        if entry.get('issues'):
            copy_issues(entry, organization)


def configure():
    configure_login()
    configure_admin()
    mirrors()


def up():
    lock()
    mirror_list()
    compose('config', '--quiet')
    compose('up', '-d', '--wait', '--wait-timeout', '180')
    configure()


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
    # Cold snapshot: SQLite and the repositories are copied while nothing writes.
    try:
        compose('stop', '--timeout', '120')
        run(['tar', '--numeric-owner', '-cpf', str(target / 'state.tar'),
             '-C', str(storage), '.'])
        run(['tar', '--numeric-owner', '-cpf', str(target / 'deployment.tar'),
             'compose.yaml', 'compose.lock.yaml', '.env', '.env.example',
             'manage.py', 'mirrors.json', 'secrets'])
        (target / 'manifest.json').write_text(json.dumps({
            'storage_root': str(storage),
            'created_utc': stamp,
            'architecture': os.uname().machine,
            'format': 1,
            'notes': 'Cold backup of Forgejo state (repositories, LFS, SQLite) and '
                     'the deployment (Compose, mirror list, secrets). Restore with '
                     'services stopped into a new or empty directory.',
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
                        choices=['init', 'lock', 'up', 'configure', 'mirrors', 'issues', 'status', 'down', 'backup'])
    parser.add_argument('--destination', default=str(ROOT / 'backups'))
    args = parser.parse_args()
    if args.action in ('init', 'up', 'configure', 'mirrors'):
        init()
    if args.action == 'lock':
        lock()
    elif args.action == 'up':
        up()
    elif args.action == 'configure':
        configure()
    elif args.action == 'mirrors':
        mirrors()
    elif args.action == 'issues':
        issues()
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
