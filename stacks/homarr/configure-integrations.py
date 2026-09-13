#!/usr/bin/env python3
"""Reconcile the Homarr integrations and board widgets. Standard library only.

Runs on services-01 after configure.py. Integrations are matched by name and
granted to the `everyone` group so every viewer sees data. Widgets are added
once with their integrations attached. Secrets are only written on create and
on explicit rotation; an update keeps the stored values.
"""
import json
import os
from pathlib import Path
import sys

from configure import Homarr, base_url

ROOT = Path(__file__).resolve().parent


def proxmox_secrets(values):
    """Proxmox の読み取り専用トークンを4つの secret に分ける。"""
    return [
        {'kind': 'username', 'value': values['PVE_USERNAME']},
        {'kind': 'realm', 'value': values['PVE_REALM']},
        {'kind': 'tokenId', 'value': values['PVE_TOKEN_ID']},
        {'kind': 'apiKey', 'value': values['PVE_TOKEN_SECRET']},
    ]


def peanut_secrets(values):
    return [
        {'kind': 'username', 'value': values['PEANUT_USERNAME']},
        {'kind': 'password', 'value': values['PEANUT_PASSWORD']},
    ]


def widget_options(kind):
    """Return the widget options; the widget definition fills the rest."""
    if kind == 'healthMonitoring':
        return {
            'fahrenheit': False, 'cpu': True, 'memory': True, 'gpu': True,
            'showUptime': True, 'fileSystem': True,
            'visibleClusterSections': ['node', 'qemu', 'lxc', 'storage'],
            'defaultTab': 'system', 'sectionIndicatorRequirement': 'all',
        }
    if kind == 'ups':
        return {'showBattery': True, 'showLoad': True, 'showVoltage': True}
    raise ValueError(f'unknown widget: {kind}')


# ウィジェットの大きさ（列数は8）。アプリのタイルは2x2で見やすくする。
WIDGET_SIZES = {'healthMonitoring': (8, 5), 'ups': (4, 3)}
DEFAULT_SIZE = (2, 2)


def pack_layouts(items, width, sizes=None):
    """Return copies of the items with a gap-free layout, largest first.

    A pure function so the arrangement can be tested without a board
    (tests/test_homarr_stack.py). Keeps each item's layout and section ids.
    """
    sizes = sizes or WIDGET_SIZES
    occupied = set()
    packed = []

    def place(w, h):
        y = 0
        while True:
            for x in range(width - w + 1):
                cells = {(x + dx, y + dy) for dx in range(w) for dy in range(h)}
                if not cells & occupied:
                    occupied.update(cells)
                    return x, y
            y += 1

    def area(item):
        w, h = sizes.get(item['kind'], DEFAULT_SIZE)
        return w * h

    for item in sorted(items, key=lambda row: -area(row)):
        w, h = sizes.get(item['kind'], DEFAULT_SIZE)
        x, y = place(w, h)
        layouts = [
            {**layout, 'xOffset': x, 'yOffset': y, 'width': w, 'height': h}
            for layout in item['layouts']
        ]
        packed.append({**item, 'layouts': layouts})
    return packed


def arrange_board(homarr, board):
    """Save the packed layout through board.saveBoard."""
    width = next(layout['columnCount'] for layout in board['layouts'] if layout['breakpoint'] == 0)
    items = pack_layouts(board['items'], width)
    homarr.trpc('board.saveBoard',
                {'id': board['id'], 'sections': board['sections'], 'items': items}, post=True)


def find_integration(integrations, name):
    return next((row for row in integrations if row['name'] == name), None)


def has_widget(items, kind, integration_ids):
    """True when the board already has this widget for these integrations."""
    for item in items:
        if item.get('kind') != kind:
            continue
        if sorted(item.get('integrationIds') or []) == sorted(integration_ids):
            return True
    return False


def ensure_integration(homarr, everyone_id, name, kind, url, secrets):
    existing = find_integration(homarr.trpc('integration.all'), name)
    if existing:
        homarr.trpc('integration.update', {
            'id': existing['id'], 'name': name, 'url': url,
            'secrets': [{'kind': secret['kind'], 'value': None} for secret in secrets],
            'appId': None,
        }, post=True)
        integration_id = existing['id']
    else:
        response = homarr.trpc('integration.create', {
            'name': name, 'url': url, 'kind': kind, 'secrets': secrets,
            'attemptSearchEngineCreation': False,
        }, post=True)
        created = find_integration(homarr.trpc('integration.all'), name)
        if not created:
            # 接続テスト失敗は tRPC の成功応答内の {error: ...} で返る。
            raise RuntimeError(f'the integration {name} was not created: {response}')
        integration_id = created['id']
    homarr.trpc('integration.saveGroupIntegrationPermissions', {
        'entityId': integration_id,
        'permissions': [{'principalId': everyone_id, 'permission': 'use'}],
    }, post=True)
    return integration_id


def ensure_widget(homarr, board, kind, integration_ids):
    if has_widget(board.get('items', []), kind, integration_ids):
        return False
    homarr.trpc('board.addItem', {
        'boardId': board['id'], 'kind': kind,
        'options': widget_options(kind), 'integrationIds': integration_ids,
    }, post=True)
    return True


def main():
    values = json.loads((ROOT / 'secrets' / 'integration_values.json').read_text())
    password = os.environ.get('HOMARR_ADMIN_PASSWORD')
    if not password:
        raise SystemExit('HOMARR_ADMIN_PASSWORD is missing; run manage.py configure')
    homarr = Homarr(base_url(os.environ.get('HOMARR_URL', 'http://localhost:7575')))
    homarr.onboard(os.environ.get('HOMARR_ADMIN_USERNAME', 'admin'), password)
    homarr.login(os.environ.get('HOMARR_ADMIN_USERNAME', 'admin'), password)

    everyone = next(row for row in homarr.trpc('group.getAll') if row['name'] == 'everyone')
    board = homarr.trpc('board.getBoardByName',
                        {'name': os.environ.get('BOARD_NAME', 'home')})

    proxmox = ensure_integration(homarr, everyone['id'], 'Proxmox', 'proxmox',
                                 values['PVE_URL'], proxmox_secrets(values))
    if ensure_widget(homarr, board, 'healthMonitoring', [proxmox]):
        print('CHANGED: added the system health widget')
    else:
        print('OK: system health widget')

    if values.get('PEANUT_PASSWORD'):
        peanut = ensure_integration(homarr, everyone['id'], 'PeaNUT', 'peaNut',
                                    values['PEANUT_URL'], peanut_secrets(values))
        if ensure_widget(homarr, board, 'ups', [peanut]):
            print('CHANGED: added the UPS widget')
        else:
            print('OK: UPS widget')

    if '--arrange' in sys.argv:
        board = homarr.trpc('board.getBoardByName',
                            {'name': os.environ.get('BOARD_NAME', 'home')})
        arrange_board(homarr, board)
        print('CHANGED: arranged the board layout')


if __name__ == '__main__':
    main()
