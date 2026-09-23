#!/usr/bin/env python3
"""Reconcile the managed Homarr board from apps.json. Standard library only.

Runs on services-01 against the local Homarr. The first run finishes Homarr's
onboarding with the generated local administrator; later runs log in with the
same account. apps.json is the source of truth for the board's app tiles:
declared apps are created or updated in place, and tiles that apps.json no
longer declares are removed. Tile positions, integration widgets and the app
records themselves are left alone.
"""
import html
import http.cookiejar
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
DEFAULT_COLOR = '#475569'


def base_url(value):
    """Refuse to guess: the board URL must be an absolute http(s) URL."""
    if not value.startswith(('http://', 'https://')):
        raise ValueError('HOMARR_URL must be an absolute http(s) URL')
    return value.rstrip('/')


def trpc_path(path, data=None):
    suffix = ''
    if data is not None:
        suffix = '?' + urllib.parse.urlencode({'input': json.dumps({'json': data})})
    return f'/api/trpc/{path}{suffix}'


def trpc_payload(data):
    return json.dumps({'json': data}).encode()


def item_app_id(item):
    """A board item's options arrive as a dict or as a JSON string."""
    options = item.get('options', {})
    if isinstance(options, str):
        options = json.loads(options)
    return options.get('json', options).get('appId')


def load_apps(path):
    rows = json.loads(Path(path).read_text())
    if not isinstance(rows, list):
        raise ValueError('apps.json must be a list')
    for row in rows:
        for key in ('name', 'href'):
            if not row.get(key):
                raise ValueError(f'apps.json entry needs {key}: {row!r}')
        if not row['href'].startswith(('http://', 'https://')):
            raise ValueError(f'apps.json href must be absolute: {row["href"]}')
    return rows


def icon_data_uri(label, color=DEFAULT_COLOR):
    text = html.escape(label)
    fill = html.escape(color, quote=True)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">'
           f'<rect x="8" y="8" width="112" height="112" rx="24" fill="{fill}"/>'
           f'<text x="64" y="73" text-anchor="middle" fill="white" '
           f'font-family="sans-serif" font-size="28" font-weight="700">{text}</text></svg>')
    return 'data:image/svg+xml,' + urllib.parse.quote(svg)


class Homarr:
    """The subset of Homarr's HTTP API this stack manages."""

    def __init__(self, base):
        self.base = base
        self.session = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, method, path, body=None, form=None):
        headers = {}
        data = body
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        elif body is not None:
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(self.base + path, method=method, data=data, headers=headers)
        try:
            with self.session.open(request, timeout=30) as response:
                content = response.read()
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'{method} {path}: HTTP {error.code}; {error.read()[:300]!r}') from None
        if not content:
            return None
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # The auth callback answers with HTML; the session cookie is the result.
            return content.decode('utf-8', 'replace')
        # tRPC returns application errors with HTTP 200 and an `error` field.
        if isinstance(parsed, dict) and parsed.get('error'):
            raise RuntimeError(f'{method} {path}: {parsed["error"].get("json", parsed["error"])}')
        return parsed

    def trpc(self, path, data=None, post=False):
        if post:
            result = self.request('POST', '/api/trpc/' + path, body=trpc_payload(data))
        else:
            result = self.request('GET', trpc_path(path, data))
        return result['result']['data'].get('json')

    def onboard(self, username, password):
        """Finish the first-run wizard with the local administrator."""
        for _ in range(8):
            step = self.trpc('onboard.currentStep')['current']
            if step == 'finish':
                return
            if step == 'user':
                self.trpc('user.initUser', {'username': username, 'password': password,
                                            'confirmPassword': password}, post=True)
            elif step in ('start', 'group', 'settings', 'integrations'):
                self.trpc('onboard.nextStep', {}, post=True)
            else:
                raise RuntimeError('Unexpected onboarding step: ' + step)
        raise RuntimeError('Homarr onboarding did not finish')

    def login(self, username, password):
        csrf = self.request('GET', '/api/auth/csrf')['csrfToken']
        self.request('POST', '/api/auth/callback/credentials',
                     form={'csrfToken': csrf, 'name': username, 'password': password,
                           'callbackUrl': self.base, 'json': 'true'})
        session = self.request('GET', '/api/auth/session')
        if not session or not session.get('user'):
            raise RuntimeError('Homarr authentication failed')


def prune_unmanaged(homarr, board, managed_app_ids):
    """Remove app tiles that apps.json no longer declares.

    The API has no per-item delete, so saveBoard is called with the unmanaged
    items filtered out; it deletes whatever the payload is missing. Widget
    items (kind != 'app') and the app records themselves are kept, so a removed
    tile can come back by declaring it in apps.json again.
    """
    current = homarr.trpc('board.getBoardByName', {'name': board['name']})
    items = current.get('items', [])
    kept = [item for item in items
            if item.get('kind') != 'app' or item_app_id(item) in managed_app_ids]
    if len(kept) == len(items):
        return 0
    homarr.trpc('board.saveBoard', {
        'id': board['id'],
        'sections': current.get('sections', []),
        'items': kept,
    }, post=True)
    return len(items) - len(kept)


def configure(homarr, options):
    """Bring the board and its permissions to the declared state.

    Kept as a function over a Homarr-like object so the reconcile rules can be
    tested without a server (tests/test_homarr_stack.py).
    """
    homarr.onboard(options['username'], options['password'])
    homarr.login(options['username'], options['password'])
    homarr.trpc('serverSettings.saveSettings',
                {'settingsKey': 'culture', 'value': {'defaultLocale': options['locale']}}, post=True)

    board = next((row for row in homarr.trpc('board.getAllBoards')
                  if row['name'] == options['board']), None)
    if board is None:
        board = {'id': homarr.trpc('board.createBoard',
                                   {'name': options['board'], 'columnCount': 8,
                                    'isPublic': False}, post=True)['boardId'],
                 'name': options['board']}
    homarr.trpc('board.savePartialBoardSettings',
                {'id': board['id'], 'pageTitle': options['title'],
                 'metaTitle': options['title'], 'disableStatus': False}, post=True)

    known = {row['name']: row for row in homarr.trpc('app.all')}
    # 同じURLのアプリが別名で残っていたら、新規作成せず名前を直す（タイルの重複を防ぐ）。
    by_href = {row.get('href'): row for row in known.values() if row.get('href')}
    current = homarr.trpc('board.getBoardByName', {'name': options['board']})
    existing = current.get('items', [])
    managed = set()
    for row in load_apps(options['apps_file']):
        data = {key: row[key] for key in ('name', 'description', 'href') if key in row}
        data.update(iconUrl=row.get('iconUrl') or icon_data_uri(
            row.get('iconText', 'APP'), row.get('iconColor', DEFAULT_COLOR)),
            # タイルの緑/赤はこのURLへの疎通で決まる。指定が無ければ開くURLを使う。
            pingUrl=row.get('pingUrl') or row['href'])
        existing_app = known.get(row['name']) or by_href.get(row['href'])
        if existing_app:
            app_id = existing_app['id']
            homarr.trpc('app.update', {**data, 'id': app_id}, post=True)
        else:
            app_id = homarr.trpc('app.create', data, post=True)['appId']
        managed.add(app_id)
        if not any(item_app_id(item) == app_id for item in existing):
            homarr.trpc('board.addItem',
                        {'boardId': board['id'], 'kind': 'app', 'options': {'appId': app_id}}, post=True)
    removed = prune_unmanaged(homarr, board, managed)

    groups = homarr.trpc('group.getAll')
    everyone = next(row for row in groups if row['name'] == 'everyone')
    homarr.trpc('group.savePartialSettings',
                {'id': everyone['id'], 'settings': {'homeBoardId': board['id']}}, post=True)
    homarr.trpc('board.saveGroupBoardPermissions',
                {'entityId': board['id'],
                 'permissions': [{'principalId': everyone['id'], 'permission': 'view'}]}, post=True)

    admin = next((row for row in groups if row['name'] == options['admin_group']), None)
    if admin is None:
        homarr.trpc('group.createGroup', {'name': options['admin_group']}, post=True)
        admin = next(row for row in homarr.trpc('group.getAll')
                     if row['name'] == options['admin_group'])
    homarr.trpc('group.savePermissions', {'groupId': admin['id'], 'permissions': ['admin']}, post=True)
    # 管理者グループにもボード編集を明示（全体管理者でも編集できるが、意図を残す）。
    homarr.trpc('board.saveGroupBoardPermissions', {
        'entityId': board['id'],
        'permissions': [{'principalId': everyone['id'], 'permission': 'view'},
                        {'principalId': admin['id'], 'permission': 'modify'}],
    }, post=True)
    print(f"Homarr board '{options['board']}' reconciled "
          f"({len(existing)} items before, {len(known)} apps known, {removed} tiles removed)")


def main():
    if not os.environ.get('HOMARR_ADMIN_PASSWORD'):
        raise SystemExit('HOMARR_ADMIN_PASSWORD is missing; run manage.py configure')
    options = {
        'username': os.environ.get('HOMARR_ADMIN_USERNAME', 'admin'),
        'password': os.environ['HOMARR_ADMIN_PASSWORD'],
        'board': os.environ.get('BOARD_NAME', 'home'),
        'apps_file': os.environ.get('APPS_FILE', str(ROOT / 'apps.json')),
        'admin_group': os.environ.get('ADMIN_GROUP', 'admins'),
        'locale': os.environ.get('LOCALE', 'ja'),
        'title': os.environ.get('BOARD_TITLE', 'Shake Lab'),
    }
    configure(Homarr(base_url(os.environ.get('HOMARR_URL', 'http://localhost:7575'))), options)


if __name__ == '__main__':
    main()
