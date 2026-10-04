# -*- coding: utf-8 -*-
"""Botポータルの純ロジック。

サービス登録の読み込みと、許可した操作の組み立てだけを行う。
FastAPIに依存しないので、テストはここを直接見る。
"""
import json
import csv
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

# manage.py の定型操作。キーがポータルでの操作名、値が manage.py に渡す引数。
MANAGE_ACTIONS = {
    'status': 'status',
    'update': 'update',
    'up': 'up',
    'down': 'down',
    'backup': 'backup',
}
# dockerを直接使う操作。値はコンテナ名の手前に付ける引数。
DOCKER_ACTIONS = {
    'restart': ['docker', 'restart'],
}
ALL_ACTIONS = tuple(MANAGE_ACTIONS) + tuple(DOCKER_ACTIONS)

# 画面に出す名前と説明。実行できるかの判断は Service.allows() が持つ。
ACTION_LABELS = {
    'restart': ('再起動', 'コンテナを再起動します。コードは変わりません。'),
    'status': ('状態確認', 'docker compose ps を実行して表示します。'),
    'update': ('更新', 'git から最新を取り込み、動いていれば作り直します。'),
    'up': ('起動', 'セーブデータを確かめてから起動します。'),
    'down': ('停止', 'コンテナを止めます。データは消えません。'),
    'backup': ('バックアップ', 'セーブデータを tar.gz に固めます。'),
}
# 確認チェックを必須にする操作。
DANGEROUS_ACTIONS = ('update', 'up', 'down', 'backup')


@dataclass(frozen=True)
class Service:
    name: str
    title: str
    description: str
    container: str
    project_dir: str
    source_dir: str = ''
    actions: tuple = ()
    help: str = ''
    checks: tuple = ()
    files: tuple = ()

    def allows(self, action: str) -> bool:
        return action in self.actions and action in ALL_ACTIONS

    def action_buttons(self) -> list:
        buttons = []
        for action in self.actions:
            label, description = ACTION_LABELS[action]
            buttons.append({
                'name': action,
                'label': label,
                'description': description,
                'dangerous': action in DANGEROUS_ACTIONS,
            })
        return buttons


def load_services(path) -> list[Service]:
    """services.yaml を読み、許可外の操作名があれば ValueError。"""
    raw = yaml.safe_load(Path(path).read_text(encoding='utf-8')) or {}
    services = []
    for entry in raw.get('services', []):
        actions = tuple(entry.get('actions', ()))
        unknown = [action for action in actions if action not in ALL_ACTIONS]
        if unknown:
            raise ValueError(f"{entry['name']}: unknown actions {unknown}")
        services.append(Service(
            name=entry['name'],
            title=entry.get('title', entry['name']),
            description=entry.get('description', ''),
            container=entry['container'],
            project_dir=entry['project_dir'],
            source_dir=entry.get('source_dir', ''),
            actions=actions,
            help=entry.get('help', ''),
            checks=tuple(entry.get('checks', ())),
            files=tuple(entry.get('files', ())),
        ))
    return services


def read_file_view(spec: dict) -> dict:
    """services.yaml の files 指定を画面用のデータにする。

    kind: csv なら header/rows（末尾 tail 行）、sqlite なら query の結果、
    それ以外は text。
    """
    path = Path(spec['path'])
    view = {'label': spec.get('label', path.name), 'path': str(path)}
    if not path.exists():
        view['error'] = 'ファイルがありません'
        return view
    if spec.get('kind') == 'sqlite':
        connection = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        try:
            cursor = connection.execute(spec['query'])
            view['header'] = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            view['rows'] = [list(row) for row in rows]
            view['total'] = len(view['rows'])
        finally:
            connection.close()
        return view
    text = path.read_text(encoding='utf-8', errors='replace')
    if spec.get('kind') == 'csv':
        rows = list(csv.reader(text.splitlines()))
        header = rows[0] if rows else []
        body = rows[1:]
        total = len(body)
        tail = int(spec.get('tail', 50))
        view.update({'header': header, 'rows': body[-tail:], 'total': total})
    else:
        view['text'] = text[-20000:]
    return view


def command_for(service: Service, action: str) -> list[str]:
    """許可された操作のコマンドを返す。許可外は ValueError。"""
    if not service.allows(action):
        raise ValueError(f'{service.name}: action not allowed: {action}')
    if action in MANAGE_ACTIONS:
        return ['python3', f'{service.project_dir}/manage.py', MANAGE_ACTIONS[action]]
    return DOCKER_ACTIONS[action] + [service.container]


def run_command(command: list[str], timeout: int = 600) -> tuple[int, str]:
    """コマンドを実行し (returncode, 出力) を返す。"""
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f'timeout: {" ".join(command)}'
    except OSError as error:
        return 127, f'failed to run: {" ".join(command)}: {error}'
    output = (completed.stdout or '') + (completed.stderr or '')
    return completed.returncode, output


def container_state(container: str) -> dict:
    """docker inspect の State を返す。無い場合は missing。"""
    code, output = run_command(
        ['docker', 'inspect', '--format', '{{json .State}}', container], timeout=30)
    if code != 0:
        return {'Status': 'missing', 'detail': output.strip()}
    try:
        return json.loads(output.strip())
    except ValueError:
        return {'Status': 'unknown', 'detail': output.strip()}


def git_revision(source_dir: str) -> str:
    """checkout の短いSHAを返す。取れなければ空文字。"""
    if not source_dir:
        return ''
    code, output = run_command(['git', '-C', source_dir, 'rev-parse', '--short', 'HEAD'], timeout=30)
    return output.strip() if code == 0 else ''