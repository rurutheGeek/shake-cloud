# -*- coding: utf-8 -*-
"""Botポータルの純ロジック。

サービス登録の読み込みと、許可した操作の組み立てだけを行う。
FastAPIに依存しないので、テストはここを直接見る。
"""
import json
import csv
import io
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
    debug: bool = False
    db: dict = None
    links: tuple = ()

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


def load_db(entry: dict) -> dict:
    """services.yaml の db 指定を検証して返す。無ければ None。"""
    db = entry.get('db') or None
    if db is None:
        return None
    kind = db.get('kind')
    if kind not in ('postgres', 'sqlite'):
        raise ValueError(f"{entry['name']}: unknown db kind: {kind}")
    required = ('container', 'database', 'user') if kind == 'postgres' else ('path',)
    missing = [key for key in required if not db.get(key)]
    if missing:
        raise ValueError(f"{entry['name']}: db is missing {missing}")
    if db.get('quiz_log') and kind != 'postgres':
        raise ValueError(f"{entry['name']}: quiz_log needs a postgres db")
    return db


def load_links(entry: dict) -> tuple:
    """services.yaml の links（ボットの紹介リンク）を検証して返す。"""
    links = []
    for item in entry.get('links', ()) or ():
        label = item.get('label', '')
        url = item.get('url', '')
        if not label or not url:
            raise ValueError(f"{entry['name']}: link needs label and url")
        if not url.startswith('https://'):
            raise ValueError(f"{entry['name']}: link url must be https: {url}")
        links.append({'label': label, 'url': url})
    return tuple(links)


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
            debug=bool(entry.get('debug', False)),
            db=load_db(entry),
            links=load_links(entry),
        ))
    return services


def db_tables(service: Service) -> dict:
    """DBのテーブル一覧と行数を返す（読み取り専用）。"""
    if not service.db:
        return {'error': 'DBが設定されていません', 'tables': []}
    if service.db['kind'] == 'sqlite':
        return _sqlite_tables(service.db)
    return _postgres_tables(service.db)


# 画面の1ページに出す上限と、CSVダウンロードで一度に出す上限。
PAGE_LIMIT = 200
EXPORT_LIMIT = 100000


def db_rows(service: Service, table: str, offset: int = 0,
            limit: int = 50, needle: str = '', cap: int = PAGE_LIMIT) -> dict:
    """1テーブルをページ単位で返す。needle は全列の部分一致。"""
    if not service.db:
        raise ValueError('DBが設定されていません')
    offset = max(0, int(offset))
    limit = min(max(1, int(limit)), cap)
    if service.db['kind'] == 'sqlite':
        return _sqlite_rows(service.db, table, offset, limit, needle)
    return _postgres_rows(service.db, table, offset, limit, needle)


def db_export(service: Service, table: str, needle: str = '') -> dict:
    """CSVダウンロード用にテーブルの全行（上限 EXPORT_LIMIT）を返す。"""
    return db_rows(service, table, offset=0, limit=EXPORT_LIMIT,
                   needle=needle, cap=EXPORT_LIMIT)


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _quote_literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _csv_rows(output: str) -> tuple:
    rows = list(csv.reader(io.StringIO(output)))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def _psql(spec: dict, sql: str) -> tuple:
    """pkdbコンテナの中で読み取り専用のpsqlを実行する。"""
    return run_command([
        'docker', 'exec',
        '-e', 'PGOPTIONS=-c default_transaction_read_only=on',
        spec['container'], 'psql',
        '-U', spec['user'], '-d', spec['database'],
        '--csv', '--no-psqlrc', '-v', 'ON_ERROR_STOP=1',
        '-c', sql,
    ], timeout=60)


def quiz_log_query(service: Service):
    """クイズ分析用に、読み取り専用でSQLを実行する関数を返す。

    SQLは app/quizlog.py が組み立てたものだけを渡す（画面からの自由入力は渡さない）。
    """
    if not service.db or not service.db.get('quiz_log'):
        raise ValueError(f'{service.name}: quiz log not configured')
    spec = service.db

    def query(sql: str) -> tuple:
        code, output = _psql(spec, sql)
        if code != 0:
            raise RuntimeError(output.strip()[-2000:])
        return _csv_rows(output)

    return query


def _sqlite_table_names(connection) -> list:
    return [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def _sqlite_connect(spec: dict):
    path = Path(spec['path'])
    if not path.exists():
        raise FileNotFoundError(path)
    return sqlite3.connect(f'file:{path}?mode=ro', uri=True)


def _sqlite_tables(spec: dict) -> dict:
    try:
        connection = _sqlite_connect(spec)
    except FileNotFoundError:
        return {'error': f"ファイルがありません: {spec['path']}", 'tables': []}
    try:
        tables = [{'name': name, 'rows': connection.execute(
            f'SELECT count(*) FROM {_quote_ident(name)}').fetchone()[0]}
            for name in _sqlite_table_names(connection)]
    finally:
        connection.close()
    return {'tables': tables}


def _sqlite_rows(spec: dict, table: str, offset: int, limit: int, needle: str) -> dict:
    connection = _sqlite_connect(spec)
    try:
        if table not in _sqlite_table_names(connection):
            raise ValueError(f'unknown table: {table}')
        columns = [row[1] for row in connection.execute(
            f'PRAGMA table_info({_quote_ident(table)})')]
        where, params = '', []
        if needle:
            where = ' WHERE ' + ' OR '.join(
                f'CAST({_quote_ident(column)} AS TEXT) LIKE ?' for column in columns)
            params = [f'%{needle}%'] * len(columns)
        total = connection.execute(
            f'SELECT count(*) FROM {_quote_ident(table)}{where}', params).fetchone()[0]
        order = ', '.join(_quote_ident(column) for column in columns)
        rows = connection.execute(
            f'SELECT * FROM {_quote_ident(table)}{where} ORDER BY {order} LIMIT ? OFFSET ?',
            [*params, limit, offset]).fetchall()
    finally:
        connection.close()
    return _table_view(table, columns, rows, total, offset, limit, needle)


def _postgres_columns(spec: dict, table: str) -> list:
    code, output = _psql(spec, (
        'SELECT column_name FROM information_schema.columns '
        "WHERE table_schema = 'public' "
        f'AND table_name = {_quote_literal(table)} '
        'ORDER BY ordinal_position'))
    if code != 0:
        raise RuntimeError(output.strip()[-2000:])
    _, rows = _csv_rows(output)
    return [row[0] for row in rows]


def _postgres_tables(spec: dict) -> dict:
    code, output = _psql(spec, (
        'SELECT table_name FROM information_schema.tables '
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
        'ORDER BY table_name'))
    if code != 0:
        return {'error': output.strip()[-2000:], 'tables': []}
    _, rows = _csv_rows(output)
    names = [row[0] for row in rows]
    if not names:
        return {'tables': []}
    union = ' UNION ALL '.join(
        f'SELECT {_quote_literal(name)} AS name, count(*) AS rows '
        f'FROM {_quote_ident(name)}' for name in names)
    code, output = _psql(spec, union + ' ORDER BY name')
    if code != 0:
        return {'error': output.strip()[-2000:], 'tables': []}
    _, rows = _csv_rows(output)
    return {'tables': [{'name': row[0], 'rows': int(row[1])} for row in rows]}


def _postgres_rows(spec: dict, table: str, offset: int, limit: int, needle: str) -> dict:
    columns = _postgres_columns(spec, table)
    if not columns:
        raise ValueError(f'unknown table: {table}')
    where = ''
    if needle:
        pattern = _quote_literal(f'%{needle}%')
        where = ' WHERE ' + ' OR '.join(
            f'{_quote_ident(column)}::text ILIKE {pattern}' for column in columns)
    quoted = _quote_ident(table)
    code, output = _psql(spec, f'SELECT count(*) FROM {quoted}{where}')
    if code != 0:
        return {'error': output.strip()[-2000:], 'header': [], 'rows': []}
    _, rows = _csv_rows(output)
    total = int(rows[0][0]) if rows else 0
    order = ', '.join(_quote_ident(column) for column in columns)
    code, output = _psql(spec, (
        f'SELECT * FROM {quoted}{where} ORDER BY {order} LIMIT {limit} OFFSET {offset}'))
    if code != 0:
        return {'error': output.strip()[-2000:], 'header': [], 'rows': []}
    _, rows = _csv_rows(output)
    return _table_view(table, columns, rows, total, offset, limit, needle)


def _table_view(table, columns, rows, total, offset, limit, needle) -> dict:
    return {
        'table': table,
        'header': columns,
        'rows': [['' if cell is None else cell for cell in row] for row in rows],
        'total': total,
        'offset': offset,
        'limit': limit,
        'needle': needle,
    }


def command_for(service: Service, action: str) -> list[str]:
    """許可された操作のコマンドを返す。許可外は ValueError。"""
    if not service.allows(action):
        raise ValueError(f'{service.name}: action not allowed: {action}')
    if action in MANAGE_ACTIONS:
        return ['python3', f'{service.project_dir}/manage.py', MANAGE_ACTIONS[action]]
    return DOCKER_ACTIONS[action] + [service.container]


def debug_command(service: Service, save: bool = False) -> list[str]:
    """DiscordなしのデバッグCLIをコンテナ内で実行するコマンド。

    入力は標準入力から渡す（コマンド行をそのままdebug_cliが解釈する）。
    """
    if not service.debug:
        raise ValueError(f'{service.name}: debug not allowed')
    command = ['docker', 'exec', '-i', service.container,
               'python', 'debug_cli.py', '--stdin']
    if save:
        command.append('--save')
    return command


def run_command(command: list[str], timeout: int = 600,
                stdin: str | None = None) -> tuple[int, str]:
    """コマンドを実行し (returncode, 出力) を返す。"""
    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=timeout, input=stdin)
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