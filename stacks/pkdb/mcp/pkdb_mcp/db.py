# -*- coding: utf-8 -*-
"""DB への読み取りと、登録関数の呼び出し。

ロール pkdb_mcp は pkdb_entry の権限（全表の閲覧と登録関数の実行）だけを持ち、
表へ直接は書けない。書き込みは pokemondb の SECURITY DEFINER 関数を通す。
"""
from dataclasses import dataclass
import logging
import os

import psycopg
from psycopg import errors, sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

log = logging.getLogger('pkdb-mcp')

# 読み取りの問い合わせの上限。AI が大きな表を丸ごと引いても DB とトークンを使い切らない。
QUERY_TIMEOUT_MS = 10000
QUERY_MAX_ROWS = 500


class DbError(Exception):
    """AI に返してよい、DB からの日本語メッセージ。"""


@dataclass
class Call:
    """登録関数の1回の呼び出し。args は関数の引数の順（p_actor を除く）。"""
    function: str
    args: list


def _conninfo():
    values = {
        'host': os.environ.get('PKDB_MCP_DB_HOST', 'db'),
        'port': os.environ.get('PKDB_MCP_DB_PORT', '5432'),
        'dbname': os.environ.get('PKDB_MCP_DB_NAME', 'sleepy_pkdb'),
        'user': os.environ.get('PKDB_MCP_DB_USER', 'pkdb_mcp'),
        'password': os.environ.get('PKDB_MCP_DB_PASSWORD', ''),
        'application_name': 'pkdb-mcp',
        'connect_timeout': '5',
    }
    return ' '.join(f'{key}={value}' for key, value in values.items() if value != '')


def _configure(connection):
    # 復元直後やテストDBでも同じように使えるよう、接続ごとに明示する。
    connection.execute('SET search_path = pokemondb, public')
    connection.commit()


pool = ConnectionPool(_conninfo(), min_size=1, max_size=4, open=False,
                      kwargs={'row_factory': dict_row}, configure=_configure)


def open_pool():
    # 待たずに起動する。初回の配備では、ロール pkdb_mcp とパスワードがコンテナの
    # 起動（compose up --wait）のあとに入る。つながるまでは /healthz の db が false。
    pool.open(wait=False)


def close_pool():
    pool.close()


def _message(error):
    return (error.diag.message_primary or str(error)).strip()


def read(statement, params=None, max_rows=QUERY_MAX_ROWS):
    """読み取り専用のトランザクションで問い合わせ、(列名, 行, 切り詰めたか) を返す。"""
    try:
        with pool.connection() as connection:
            connection.read_only = True
            try:
                with connection.transaction():
                    connection.execute(
                        sql.SQL('SET LOCAL statement_timeout = {}').format(QUERY_TIMEOUT_MS))
                    with connection.cursor() as cursor:
                        cursor.execute(statement, params)
                        if cursor.description is None:
                            return [], [], False
                        columns = [column.name for column in cursor.description]
                        rows = cursor.fetchmany(max_rows + 1)
            finally:
                connection.read_only = False
    except psycopg.Error as error:
        raise DbError(_message(error)) from None
    return columns, rows[:max_rows], len(rows) > max_rows


def execute(actor, source, strict, calls):
    """登録関数を1つのトランザクションで順に呼び、各結果を返す。

    pkdb.source は entry_log の source へ、pkdb.strict は名前の自動作成の禁止へ、
    pkdb.defer_refresh はマテリアライズドビューの作り直しを最後の1回にまとめる。
    1つでも失敗すれば全部取り消す。
    """
    results = []
    try:
        with pool.connection() as connection:
            with connection.transaction(), connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('pkdb.source', %s, true),"
                    " set_config('pkdb.strict', %s, true),"
                    " set_config('pkdb.defer_refresh', 'on', true),"
                    " set_config('pkdb.refresh_pending', '', true)",
                    (source, 'on' if strict else 'off'))
                for index, call in enumerate(calls):
                    placeholders = sql.SQL(', ').join([sql.Placeholder()] * (len(call.args) + 1))
                    statement = sql.SQL('SELECT pokemondb.{}({}) AS result').format(
                        sql.Identifier(call.function), placeholders)
                    try:
                        cursor.execute(statement, [actor, *call.args])
                    except errors.RaiseException as error:
                        prefix = f'{index + 1}件目（{call.function}）: ' if len(calls) > 1 else ''
                        raise DbError(prefix + _message(error)) from None
                    results.append(cursor.fetchone()['result'])
                cursor.execute("SELECT set_config('pkdb.defer_refresh', 'off', true),"
                               " current_setting('pkdb.refresh_pending', true) AS pending")
                pending = cursor.fetchone()['pending']
                if pending == 'all':
                    cursor.execute('SELECT pokemondb.refresh_views()')
                elif pending == 'moves':
                    cursor.execute('SELECT pokemondb.refresh_move_views()')
    except DbError:
        raise
    except psycopg.Error as error:
        log.exception('pkdb-mcp: %s failed', ', '.join(call.function for call in calls))
        raise DbError(_message(error)) from None
    return results


def jsonb(value):
    return Jsonb(value)


def healthy():
    try:
        with pool.connection(timeout=3) as connection:
            connection.execute('SELECT 1')
        return True
    except psycopg.Error:
        return False
