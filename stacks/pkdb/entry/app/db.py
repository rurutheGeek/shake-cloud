# -*- coding: utf-8 -*-
"""DBへの読み取りと、登録関数の呼び出し。

画面のロール pkdb_entry は表へ直接書けない。書くのは pokemondb の
SECURITY DEFINER 関数だけで、その呼び出しを call() に集める。
"""
import logging
import os

import psycopg
from psycopg import errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

log = logging.getLogger('pkdb-entry')


class DbError(Exception):
    """画面に出してよい、DBからの日本語メッセージ。"""


def _conninfo():
    values = {
        'host': os.environ.get('PKDB_ENTRY_HOST', 'db'),
        'port': os.environ.get('PKDB_ENTRY_PORT', '5432'),
        'dbname': os.environ.get('PKDB_ENTRY_DATABASE', 'sleepy_pkdb'),
        'user': os.environ.get('PKDB_ENTRY_USER', 'pkdb_entry'),
        'password': os.environ.get('PKDB_ENTRY_PASSWORD', ''),
        'application_name': 'pkdb-entry',
        'connect_timeout': '5',
    }
    return ' '.join(f'{key}={value}' for key, value in values.items() if value != '')


def _configure(connection):
    # 本番の sleepy_pkdb はデータベースの search_path に pokemondb を入れてあるが、
    # 復元直後やテストDBでも同じように使えるよう、接続ごとに明示する。
    # SET はトランザクションを開くので、プールへ返す前に確定させる。
    connection.execute('SET search_path = pokemondb, public')
    connection.commit()


pool = ConnectionPool(_conninfo(), min_size=1, max_size=4, open=False,
                      kwargs={'row_factory': dict_row}, configure=_configure)


def open_pool():
    pool.open()
    pool.wait(timeout=15)


def close_pool():
    pool.close()


def query(sql, params=None):
    with pool.connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()


def query_one(sql, params=None):
    rows = query(sql, params)
    return rows[0] if rows else None


def healthy():
    try:
        with pool.connection(timeout=3) as connection:
            connection.execute('SELECT 1')
        return True
    except psycopg.Error:
        return False


def call(function, params):
    """pokemondb の登録関数を呼び、返ってきたメッセージを返す。"""
    names = ', '.join(f'%({key})s' for key in params)
    statement = f'SELECT pokemondb.{function}({names}) AS result'
    try:
        with pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, params)
                return cursor.fetchone()['result']
    except errors.RaiseException as error:
        message = (error.diag.message_primary or '登録できませんでした').strip()
        raise DbError(message) from None
    except psycopg.Error:
        log.exception('pkdb-entry: %s failed', function)
        raise DbError('データベースのエラーで保存できませんでした') from None


def jsonb(value):
    return Jsonb(value)
