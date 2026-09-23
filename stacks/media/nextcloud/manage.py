#!/usr/bin/env python3
"""Deploy Nextcloud, Calendar and Tasks as an independent Compose project on media-01."""
import argparse
import base64
from datetime import datetime, timedelta
import json
import os
import re
import secrets
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree
import xml.sax.saxutils
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTAINER_UID = 33
CONTAINER_GID = 33
SECRETS = ('postgres_password', 'nextcloud_admin_password')


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


def compose(*args, locked=True, capture_output=False):
    command = ['docker', 'compose', '--env-file', str(ROOT / '.env'),
               '-f', str(ROOT / 'compose.yaml')]
    if locked and (ROOT / 'compose.lock.yaml').exists():
        command += ['-f', str(ROOT / 'compose.lock.yaml')]
    environment = dict(os.environ)
    # Prevent shell environment variables from silently changing .env paths.
    environment.update(settings())
    return subprocess.run(command + list(args), cwd=ROOT, check=True, text=True,
                          env=environment, capture_output=capture_output)


def paths(config):
    """Return STORAGE_ROOT and LIBRARY_ROOT, kept as separate trees."""
    storage = Path(config.get('STORAGE_ROOT', '/srv/media-stack/storage')).resolve()
    library = Path(config.get('LIBRARY_ROOT', '/srv/media-stack/library')).resolve()
    if storage == library or storage in library.parents or library in storage.parents:
        raise ValueError('STORAGE_ROOT and LIBRARY_ROOT must be separate directories')
    return storage, library


def init():
    env = ROOT / '.env'
    if not env.exists():
        env.write_bytes((ROOT / '.env.example').read_bytes())
    env.chmod(0o600)
    storage, library = paths(settings())
    # www-data (33:33) writes Nextcloud's code, config and data, and reads the
    # shared books/music/docs originals. postgres owns its data directory itself.
    directories = [
        (storage, None),
        (storage / 'postgres', None),
        (storage / 'nextcloud', None),
    ]
    directories += [(storage / 'nextcloud' / name, (CONTAINER_UID, CONTAINER_GID))
                    for name in ('html', 'config', 'data')]
    directories += [(library, None)]
    directories += [(library / name, (CONTAINER_UID, CONTAINER_GID))
                    for name in ('books', 'music', 'docs')]
    for path, owner in directories:
        if not path.exists():
            try:
                path.mkdir(parents=True, mode=0o750)
            except PermissionError as error:
                raise PermissionError(f'Run init with sudo to create {path}') from error
        if owner:
            if (path.stat().st_uid, path.stat().st_gid) != owner:
                if os.geteuid() != 0:
                    raise PermissionError(
                        f'Run init with sudo to own {path} as {owner[0]}:{owner[1]}')
                os.chown(path, *owner)
            path.chmod(0o2750)
    directory = ROOT / 'secrets'
    directory.mkdir(exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    for name in SECRETS:
        path = directory / name
        if not path.exists():
            # Readable by the container users; the host directory stays private.
            with path.open('x') as handle:
                handle.write(secrets.token_urlsafe(36) + '\n')
        if not path.read_text().strip():
            raise ValueError(f'Empty secret file: {path}')
        path.chmod(0o444)
    print('OK: Nextcloud directories and secrets are ready')


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


def up():
    lock()
    compose('config', '--quiet')
    compose('up', '-d', '--remove-orphans', '--wait', '--wait-timeout', '900')


def occ(*args, **kwargs):
    return compose('exec', '-T', '--user', '33:33', 'nextcloud', 'php', 'occ', *args, **kwargs)


def setup():
    """Enable files_external and cron, then reconcile the shared library mounts.

    The library lives on the shared data disk, so it is opened to every account
    that can log in: inviting someone in Authentik is the access decision. The
    mount is created without an applicable list (empty = everyone) and any
    leftover user/group restriction is removed on redeploy.
    """
    occ('app:enable', 'files_external')
    occ('background:cron')
    raw = json.loads(occ('files_external:list', '--output=json', capture_output=True).stdout)
    mounts = list(raw.values()) if isinstance(raw, dict) else raw
    for name, datadir in (('books', '/library/books'),
                          ('music', '/library/music'),
                          ('docs', '/docs'),
                          ('inbox', '/library/inbox')):
        matching = [m for m in mounts if m['mount_point'].strip('/') == name]
        if not matching:
            occ('files_external:create', '/' + name, 'local', 'null::null',
                '--config', f'datadir={datadir}')
            print(f'CHANGED: external storage created: /{name}')
            continue
        if len(matching) != 1 or matching[0]['configuration'].get('datadir') != datadir:
            raise RuntimeError(f'Conflicting external storage mount: {name}; inspect in Nextcloud')
        mount = matching[0]
        changed = False
        for user in mount.get('applicable_users') or []:
            occ('files_external:applicable', str(mount['mount_id']), f'--remove-user={user}')
            changed = True
        for group in mount.get('applicable_groups') or []:
            occ('files_external:applicable', str(mount['mount_id']), f'--remove-group={group}')
            changed = True
        if changed:
            print(f'CHANGED: external storage opened to every user: /{name}')
        else:
            print(f'OK: external storage available to every user: /{name}')


def upgrade():
    """Apply pending Nextcloud/app upgrades (needed after an app version bump)."""
    result = occ('upgrade', capture_output=True)
    if 'Everything up-to-date' in result.stdout:
        print('OK: Nextcloud already up to date')
    else:
        print('CHANGED: Nextcloud upgraded')


def apps(names):
    """Install and enable selected Nextcloud apps through occ.

    This keeps the container interaction in the portable unit script so
    Ansible can invoke the same operation on local and remote deployments.
    """
    requested = [name.strip() for name in names.split(',') if name.strip()]
    if not requested:
        print('OK: no additional Nextcloud apps requested')
        return
    state = json.loads(occ('app:list', '--output=json', capture_output=True).stdout)
    enabled = set(state.get('enabled', {}))
    disabled = set(state.get('disabled', {}))
    for name in requested:
        if name in enabled:
            print(f'OK: Nextcloud app already enabled: {name}')
        elif name in disabled:
            occ('app:enable', name)
            print(f'CHANGED: Nextcloud app enabled: {name}')
        else:
            occ('app:install', name)
            print(f'CHANGED: Nextcloud app installed: {name}')


def config_app(app, values):
    """Reconcile app config values and report only real changes.

    The token is a shared secret from SOPS and reaches this script through the
    environment; it is stored in Nextcloud's app config for the controller.
    """
    for key, value in values:
        try:
            current = occ('config:app:get', app, key,
                          capture_output=True).stdout.strip()
        except subprocess.CalledProcessError:
            current = ''
        if current == value:
            print(f'OK: {app} {key}')
        else:
            occ('config:app:set', app, key, f'--value={value}')
            print(f'CHANGED: {app} {key}')


def config_print():
    config_app('shake_print', (
        ('print_api_url', os.environ['PRINT_API_URL']),
        ('print_api_token', os.environ['PRINT_API_TOKEN']),
    ))


def config_localsend():
    config_app('shake_localsend', (
        ('send_api_url', os.environ['SEND_API_URL']),
        ('send_api_token', os.environ['SEND_API_TOKEN']),
    ))


def config_tags():
    config_app('shake_tags', (
        ('tags_api_url', os.environ['TAGS_API_URL']),
        ('tags_api_token', os.environ['TAGS_API_TOKEN']),
    ))


def config_notes():
    """Default Notes to the plain Markdown editor.

    The rich text editor hides the Markdown source; users can still choose
    Rich text or Preview in the Notes settings.
    """
    config_app('notes', (('noteMode', 'edit'),))


CALENDAR_PROPFIND = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:" xmlns:cs="urn:ietf:params:xml:ns:caldav">'
    '<d:prop><d:displayname/><d:resourcetype/><d:getetag/></d:prop>'
    '</d:propfind>')

CALENDAR_MKCALENDAR = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<C:mkcalendar xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav"'
    ' xmlns:I="http://apple.com/ns/ical/">'
    '<D:set><D:prop>'
    '<D:displayname>{name}</D:displayname>'
    '<I:calendar-color>#0082C9</I:calendar-color>'
    '<C:supported-calendar-component-set><C:comp name="VEVENT"/></C:supported-calendar-component-set>'
    '</D:prop></D:set></C:mkcalendar>')

CALENDAR_SHARE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<oc:share xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">'
    '<oc:set><d:href>principal:principals/users/{sharee}</d:href>{access}</oc:set>'
    '</oc:share>')


def unfold_ics(text):
    """Undo RFC 5545 line folding so properties can be edited."""
    lines = []
    for line in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        if line[:1] in (' ', '\t') and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def normalize_event(lines, default_minutes=60):
    """Fix the KF New Calendar quirks of one VEVENT and return (uid, lines).

    The export writes TZID as a standalone property and stamps DTEND as
    1970-01-01 for recurring entries; the former becomes a parameter on
    DTSTART/DTEND and the latter becomes DTSTART + default_minutes.
    """
    timezone = None
    properties = []
    for line in lines:
        if line.startswith('TZID:'):
            timezone = line.split(':', 1)[1]
        else:
            properties.append(line)
    start = None
    for line in properties:
        name, sep, value = line.partition(':')
        if sep and name.split(';')[0] == 'DTSTART' and 'VALUE=DATE' not in name:
            if re.fullmatch(r'\d{8}T\d{6}', value):
                start = value
    result = []
    uid = None
    for line in properties:
        name, sep, value = line.partition(':')
        base = name.split(';')[0]
        if sep and base in ('DTSTART', 'DTEND') and 'VALUE=DATE' not in name \
                and re.fullmatch(r'\d{8}T\d{6}', value):
            if base == 'DTEND' and value == '19700101T090000' and start:
                end = datetime.strptime(start, '%Y%m%dT%H%M%S')
                value = (end + timedelta(minutes=default_minutes)).strftime('%Y%m%dT%H%M%S')
            if 'TZID=' not in name and timezone:
                name = '{};TZID={}'.format(name, timezone)
        if sep and base == 'UID':
            uid = value
        result.append('{}:{}'.format(name, value) if sep else line)
    return uid, result


def normalize_ics(text, default_minutes=60):
    """Split an iCalendar export into (uid, single-event VCALENDAR) pairs."""
    events = []
    inside = False
    lines = []
    for line in unfold_ics(text):
        if line == 'BEGIN:VEVENT':
            inside = True
            lines = []
        elif line == 'END:VEVENT' and inside:
            inside = False
            uid, event = normalize_event(lines, default_minutes)
            if uid:
                events.append((uid, '\r\n'.join([
                    'BEGIN:VCALENDAR',
                    'VERSION:2.0',
                    'PRODID:-//Shake Cloud//Nextcloud calendar import//EN',
                    'CALSCALE:GREGORIAN',
                    'BEGIN:VEVENT',
                ] + event + ['END:VEVENT', 'END:VCALENDAR', ''])))
        elif inside:
            lines.append(line)
    return events


def parse_share(value):
    """Parse a --share value like uid or uid:read into (user, read_only)."""
    sharee, _, access = value.partition(':')
    if not sharee or access not in ('', 'read', 'read-write'):
        raise ValueError('Use --share user or --share user:read')
    return sharee, access == 'read'


def token_ids(listing, name):
    """Return the token ids of a user:auth-tokens:list table by name."""
    ids = []
    for line in listing.splitlines():
        fields = [field.strip() for field in line.strip().strip('|').split('|')]
        if len(fields) >= 2 and fields[1] == name:
            ids.append(fields[0])
    return ids


def create_app_password(user, name='calendar-import'):
    """Create a temporary app password through occ and return (token, id)."""
    listing = occ('user:auth-tokens:list', user, capture_output=True).stdout
    for stale in token_ids(listing, name):
        occ('user:auth-tokens:delete', user, stale)
    created = occ('user:auth-tokens:add', user, '--name={}'.format(name), '-n',
                  capture_output=True).stdout
    lines = [line.strip() for line in created.splitlines() if line.strip()]
    token = lines[-1] if lines else ''
    if len(token) < 20:
        raise RuntimeError('Could not read the generated app password')
    listing = occ('user:auth-tokens:list', user, capture_output=True).stdout
    ids = token_ids(listing, name)
    if not ids:
        raise RuntimeError('Could not find the generated app password')
    return token, ids[-1]


def dav_base(config):
    address = config.get('BIND_ADDRESS', '127.0.0.1')
    if address in ('0.0.0.0', '::'):
        address = '127.0.0.1'
    return 'http://{}:{}'.format(address, config.get('NEXTCLOUD_PORT', '8080'))


def dav_request(config, user, token, method, path, body=None, headers=None,
                ok=(200, 201, 204, 207)):
    request = urllib.request.Request(
        dav_base(config) + path,
        data=body.encode('utf-8') if body is not None else None,
        method=method)
    request.add_header('Authorization', 'Basic ' + base64.b64encode(
        '{}:{}'.format(user, token).encode()).decode())
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as error:
        if error.code in ok:
            return error.code, error.read().decode('utf-8', 'replace')
        raise RuntimeError('CalDAV {} {} failed: HTTP {}'.format(method, path, error.code))


def find_calendar(config, user, token, name):
    """Return the href of the user's calendar with this display name, if any."""
    home = '/remote.php/dav/calendars/{}/'.format(urllib.parse.quote(user))
    _, body = dav_request(config, user, token, 'PROPFIND', home, CALENDAR_PROPFIND,
                          {'Depth': '1'})
    for response in xml.etree.ElementTree.fromstring(body).findall('{DAV:}response'):
        prop = response.find('{DAV:}propstat/{DAV:}prop')
        if prop is None or prop.findtext('{DAV:}displayname') != name:
            continue
        types = prop.find('{DAV:}resourcetype')
        if types is not None and types.find(
                '{urn:ietf:params:xml:ns:caldav}calendar') is not None:
            return response.findtext('{DAV:}href')
    return None


def calendar_objects(config, user, token, href):
    """Return the object file names already present in the calendar."""
    _, body = dav_request(config, user, token, 'PROPFIND', href, CALENDAR_PROPFIND,
                          {'Depth': '1'})
    names = set()
    for response in xml.etree.ElementTree.fromstring(body).findall('{DAV:}response'):
        path = response.findtext('{DAV:}href') or ''
        if path.rstrip('/') == href.rstrip('/'):
            continue
        names.add(urllib.parse.unquote(path.rsplit('/', 1)[-1]))
    return names


def import_calendar(user, path, name, shares, default_minutes=60):
    """Import an exported iCalendar file into a user's calendar.

    Existing events (matched by UID) are left untouched, so re-running after
    an import only adds what is missing. The calendar is shared with the
    requested users; the temporary app password is always removed.
    """
    events = normalize_ics(Path(path).read_text(encoding='utf-8-sig'), default_minutes)
    if not events:
        raise RuntimeError('No VEVENT found in {}'.format(path))
    config = settings()
    token, token_id = create_app_password(user)
    try:
        home = '/remote.php/dav/calendars/{}/'.format(urllib.parse.quote(user))
        href = find_calendar(config, user, token, name)
        if href:
            print('OK: calendar exists: {}'.format(name))
        else:
            href = home + str(uuid.uuid4()) + '/'
            dav_request(config, user, token, 'MKCALENDAR', href,
                        CALENDAR_MKCALENDAR.format(
                            name=xml.sax.saxutils.escape(name)),
                        {'Content-Type': 'application/xml; charset=utf-8'})
            print('CHANGED: calendar created: {}'.format(name))
        present = calendar_objects(config, user, token, href)
        imported = 0
        for uid, object_text in events:
            filename = urllib.parse.quote(uid, safe='') + '.ics'
            if urllib.parse.unquote(filename) in present:
                continue
            dav_request(config, user, token, 'PUT', href + filename, object_text,
                        {'Content-Type': 'text/calendar; charset=utf-8'})
            imported += 1
        if imported:
            print('CHANGED: imported {} events into {}'.format(imported, name))
        else:
            print('OK: {} events already imported into {}'.format(len(events), name))
        for sharee, read_only in shares:
            status, _ = dav_request(
                config, user, token, 'POST', href,
                CALENDAR_SHARE.format(
                    sharee=xml.sax.saxutils.escape(sharee),
                    access='<oc:read/>' if read_only else '<oc:read-write/>'),
                {'Content-Type': 'application/xml; charset=utf-8'},
                ok=(200, 403))
            access = 'read' if read_only else 'read-write'
            if status == 200:
                print('CHANGED: shared with {} ({})'.format(sharee, access))
            else:
                print('OK: already shared with {} ({})'.format(sharee, access))
    finally:
        occ('user:auth-tokens:delete', user, token_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',
                        choices=['init', 'lock', 'up', 'upgrade', 'setup', 'apps',
                                 'config-notes', 'config-print', 'config-localsend',
                                 'config-tags', 'import-calendar', 'status', 'down'])
    parser.add_argument('--apps', dest='app_names', help='Comma-separated Nextcloud app IDs')
    parser.add_argument('--user', dest='calendar_user',
                        help='Nextcloud user id for import-calendar')
    parser.add_argument('--file', dest='calendar_file',
                        help='iCalendar file on the host for import-calendar')
    parser.add_argument('--name', dest='calendar_name',
                        help='Calendar display name for import-calendar')
    parser.add_argument('--share', dest='calendar_shares', action='append', default=[],
                        help='User or user:read to share with, repeatable')
    parser.add_argument('--default-minutes', dest='calendar_minutes', type=int, default=60,
                        help='Duration for events with the broken 1970 end')
    args = parser.parse_args()
    if args.action in ('init', 'up'):
        init()
    if args.action == 'lock':
        lock()
    elif args.action == 'up':
        up()
    elif args.action == 'upgrade':
        upgrade()
    elif args.action == 'setup':
        setup()
    elif args.action == 'apps':
        if args.app_names is None:
            raise ValueError('Use --apps app1,app2 with the apps action')
        apps(args.app_names)
    elif args.action == 'import-calendar':
        if not (args.calendar_user and args.calendar_file and args.calendar_name):
            raise ValueError('Use --user, --file and --name with the import-calendar action')
        import_calendar(args.calendar_user, args.calendar_file, args.calendar_name,
                        [parse_share(value) for value in args.calendar_shares],
                        args.calendar_minutes)
    elif args.action == 'config-notes':
        config_notes()
    elif args.action == 'config-print':
        config_print()
    elif args.action == 'config-localsend':
        config_localsend()
    elif args.action == 'config-tags':
        config_tags()
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
