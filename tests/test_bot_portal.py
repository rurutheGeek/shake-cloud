"""Guard the bot portal: allowlisted actions only, loopback-only, SSO inside.

The portal runs manage.py and talks to the Docker socket, so it is effectively
as powerful as the host. It must stay on loopback, behind Forward Auth, and it
must only run the actions listed in services.yaml.
"""
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/bot-portal'
SPEC = importlib.util.spec_from_file_location('bot_portal_actions', STACK / 'app/actions.py')
actions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(actions)
QUIZ_SPEC = importlib.util.spec_from_file_location('bot_portal_quizlog', STACK / 'app/quizlog.py')
quizlog = importlib.util.module_from_spec(QUIZ_SPEC)
QUIZ_SPEC.loader.exec_module(quizlog)

REGISTRY = '''
services:
  - name: ubsleepy
    title: UBSLEEPY
    description: test bot
    container: ubsleepy-bot-1
    project_dir: /opt/ubsleepy
    source_dir: /srv/ubsleepy/source
    actions: [restart, status, update]
    help: これはテストです。
    checks:
      - 確認手順その1
      - 確認手順その2
'''


class RegistryTests(unittest.TestCase):
    def load(self, text=REGISTRY):
        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False, encoding='utf-8') as file:
            file.write(text)
            path = file.name
        self.addCleanup(lambda: Path(path).unlink(missing_ok=True))
        return actions.load_services(path)

    def test_loads_services_and_their_actions(self):
        service = self.load()[0]
        self.assertEqual(service.name, 'ubsleepy')
        self.assertTrue(service.allows('update'))
        self.assertFalse(service.allows('down'))

    def test_loads_help_and_checks(self):
        service = self.load()[0]
        self.assertEqual(service.help, 'これはテストです。')
        self.assertEqual(service.checks, ('確認手順その1', '確認手順その2'))

    def test_action_buttons_carry_labels_and_danger(self):
        buttons = {button['name']: button for button in self.load()[0].action_buttons()}
        self.assertEqual(buttons['restart']['label'], '再起動')
        self.assertFalse(buttons['restart']['dangerous'])
        self.assertTrue(buttons['update']['dangerous'])

    def test_unknown_action_is_rejected_at_load(self):
        with self.assertRaises(ValueError):
            self.load(REGISTRY.replace('[restart, status, update]', '[rm -rf]'))

    def test_command_for_manage_action(self):
        service = self.load()[0]
        self.assertEqual(actions.command_for(service, 'status'),
                         ['python3', '/opt/ubsleepy/manage.py', 'status'])

    def test_command_for_restart(self):
        service = self.load()[0]
        self.assertEqual(actions.command_for(service, 'restart'),
                         ['docker', 'restart', 'ubsleepy-bot-1'])

    def test_command_for_disallowed_action(self):
        service = self.load()[0]
        with self.assertRaises(ValueError):
            actions.command_for(service, 'down')

    def test_loads_the_debug_flag(self):
        self.assertFalse(self.load()[0].debug)
        text = REGISTRY.replace(
            'actions: [restart, status, update]',
            'actions: [restart, status, update]\n    debug: true')
        self.assertTrue(self.load(text)[0].debug)

    def test_debug_command_runs_the_cli_in_the_container(self):
        text = REGISTRY.replace(
            'actions: [restart, status, update]',
            'actions: [restart, status, update]\n    debug: true')
        service = self.load(text)[0]
        self.assertEqual(actions.debug_command(service), [
            'docker', 'exec', '-i', 'ubsleepy-bot-1',
            'python', 'debug_cli.py', '--stdin'])
        self.assertEqual(actions.debug_command(service, save=True)[-1], '--save')

    def test_debug_command_is_rejected_when_not_enabled(self):
        with self.assertRaises(ValueError):
            actions.debug_command(self.load()[0])


DB_REGISTRY = REGISTRY.replace(
    '    checks:',
    '''    db:
      kind: postgres
      container: pkdb-db-1
      database: ubsleepy
      user: ubsleepy_reader
    checks:''')


class DbRegistryTests(unittest.TestCase):
    def load(self, text):
        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False, encoding='utf-8') as file:
            file.write(text)
            path = file.name
        self.addCleanup(lambda: Path(path).unlink(missing_ok=True))
        return actions.load_services(path)

    def test_postgres_db_spec_is_loaded(self):
        service = self.load(DB_REGISTRY)[0]
        self.assertEqual(service.db['kind'], 'postgres')
        self.assertEqual(service.db['database'], 'ubsleepy')
        self.assertEqual(service.db['user'], 'ubsleepy_reader')

    def test_sqlite_db_spec_is_loaded(self):
        text = REGISTRY.replace('    checks:', '    db: {kind: sqlite, path: /tmp/app.sqlite3}\n    checks:')
        self.assertEqual(self.load(text)[0].db['path'], '/tmp/app.sqlite3')

    def test_unknown_db_kind_is_rejected(self):
        text = REGISTRY.replace('    checks:', '    db: {kind: mysql, path: /tmp/app}\n    checks:')
        with self.assertRaises(ValueError):
            self.load(text)

    def test_postgres_db_spec_needs_connection_fields(self):
        text = REGISTRY.replace('    checks:', '    db: {kind: postgres, database: ubsleepy}\n    checks:')
        with self.assertRaises(ValueError):
            self.load(text)


LINKS_REGISTRY = REGISTRY.replace(
    '    checks:',
    '''    links:
      - label: Discordで見る
        url: https://discord.com/users/123
      - label: 招待URL
        url: https://discord.com/oauth2/authorize?client_id=123
    checks:''')


class LinkRegistryTests(unittest.TestCase):
    def load(self, text):
        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False, encoding='utf-8') as file:
            file.write(text)
            path = file.name
        self.addCleanup(lambda: Path(path).unlink(missing_ok=True))
        return actions.load_services(path)

    def test_links_keep_their_order_and_labels(self):
        links = self.load(LINKS_REGISTRY)[0].links
        self.assertEqual([link['label'] for link in links], ['Discordで見る', '招待URL'])
        self.assertEqual(links[1]['url'],
                         'https://discord.com/oauth2/authorize?client_id=123')

    def test_http_links_are_rejected(self):
        text = REGISTRY.replace(
            '    checks:', '    links: [{label: x, url: "http://example.com"}]\n    checks:')
        with self.assertRaises(ValueError):
            self.load(text)

    def test_links_need_a_label(self):
        text = REGISTRY.replace(
            '    checks:', '    links: [{url: "https://example.com"}]\n    checks:')
        with self.assertRaises(ValueError):
            self.load(text)


class DbViewTests(unittest.TestCase):
    def service(self, db):
        return actions.Service(name='app', title='app', description='',
                               container='app-bot-1', project_dir='/opt/app', db=db)

    def sqlite_service(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'app.sqlite3'
        connection = sqlite3.connect(path)
        connection.execute('CREATE TABLE save_user (user_id INTEGER PRIMARY KEY, name TEXT)')
        connection.execute("INSERT INTO save_user VALUES (1, 'るる')")
        connection.execute("INSERT INTO save_user VALUES (2, 'しやん')")
        connection.commit()
        connection.close()
        return self.service({'kind': 'sqlite', 'path': str(path)})

    def test_sqlite_tables_lists_names_and_counts(self):
        view = actions.db_tables(self.sqlite_service())
        self.assertEqual(view['tables'], [{'name': 'save_user', 'rows': 2}])

    def test_sqlite_rows_paginate_and_filter(self):
        service = self.sqlite_service()
        view = actions.db_rows(service, 'save_user', offset=1, limit=1)
        self.assertEqual(view['header'], ['user_id', 'name'])
        self.assertEqual(view['rows'], [[2, 'しやん']])
        self.assertEqual(view['total'], 2)
        self.assertEqual(actions.db_rows(service, 'save_user', needle='しやん')['rows'],
                         [[2, 'しやん']])

    def test_sqlite_unknown_table_is_rejected(self):
        with self.assertRaises(ValueError):
            actions.db_rows(self.sqlite_service(), 'nope')

    def test_missing_sqlite_file_reports_an_error(self):
        view = actions.db_tables(self.service({'kind': 'sqlite', 'path': '/no/such.sqlite3'}))
        self.assertIn('ファイルがありません', view['error'])

    def test_rows_without_db_is_rejected(self):
        with self.assertRaises(ValueError):
            actions.db_rows(self.service(None), 'save_user')

    def test_limit_is_capped(self):
        self.assertEqual(
            actions.db_rows(self.sqlite_service(), 'save_user', limit=9999)['limit'], 200)

    def test_export_returns_all_rows_beyond_the_page_cap(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'big.sqlite3'
        connection = sqlite3.connect(path)
        connection.execute('CREATE TABLE log (id INTEGER PRIMARY KEY, note TEXT)')
        connection.executemany('INSERT INTO log (note) VALUES (?)',
                               [(f'n{i}',) for i in range(250)])
        connection.commit()
        connection.close()
        service = self.service({'kind': 'sqlite', 'path': str(path)})

        page = actions.db_rows(service, 'log', limit=9999)
        export = actions.db_export(service, 'log')
        self.assertEqual(page['total'], 250)
        self.assertEqual(len(page['rows']), 200)
        self.assertEqual(len(export['rows']), 250)


class PostgresDbViewTests(unittest.TestCase):
    def setUp(self):
        self.commands = []
        original = actions.run_command
        self.addCleanup(lambda: setattr(actions, 'run_command', original))

        def fake(command, timeout=600, stdin=None):
            self.commands.append(command)
            sql = command[-1]
            if 'information_schema.tables' in sql:
                return 0, 'table_name\nsave_user\n'
            if 'AS name, count(*)' in sql:
                return 0, 'name,rows\nsave_user,2\n'
            if 'information_schema.columns' in sql:
                return 0, 'column_name\nuser_id\nname\n'
            if 'count(*)' in sql:
                return 0, 'count\n2\n'
            if 'SELECT *' in sql:
                return 0, 'user_id,name\n1,るる\n2,しやん\n'
            return 1, 'unexpected sql'

        actions.run_command = fake

    def service(self):
        return actions.Service(
            name='ubsleepy', title='', description='', container='ubsleepy-bot-1',
            project_dir='/opt/ubsleepy',
            db={'kind': 'postgres', 'container': 'pkdb-db-1',
                'database': 'ubsleepy', 'user': 'ubsleepy_reader'})

    def test_tables_use_exact_counts(self):
        view = actions.db_tables(self.service())
        self.assertEqual(view['tables'], [{'name': 'save_user', 'rows': 2}])
        self.assertIn('count(*) AS rows', self.commands[-1][-1])

    def test_psql_runs_read_only_as_the_reader(self):
        actions.db_tables(self.service())
        for command in self.commands:
            self.assertEqual(command[:2], ['docker', 'exec'])
            self.assertIn('PGOPTIONS=-c default_transaction_read_only=on', command)
            self.assertIn('--csv', command)
            self.assertIn('ubsleepy_reader', command)

    def test_rows_page(self):
        view = actions.db_rows(self.service(), 'save_user', offset=0, limit=50)
        self.assertEqual(view['header'], ['user_id', 'name'])
        self.assertEqual(view['rows'], [['1', 'るる'], ['2', 'しやん']])
        self.assertEqual(view['total'], 2)
        self.assertIn('FROM "save_user"', self.commands[-1][-1])
        self.assertIn('LIMIT 50 OFFSET 0', self.commands[-1][-1])

    def test_filter_escapes_quotes(self):
        actions.db_rows(self.service(), 'save_user', needle="O'Brien")
        filtered = [command[-1] for command in self.commands
                    if 'count(*)' in command[-1] or 'SELECT *' in command[-1]]
        self.assertTrue(filtered)
        for sql in filtered:
            self.assertIn("O''Brien", sql)

    def test_unknown_table_is_rejected(self):
        actions.run_command = lambda command, timeout=600, stdin=None: (0, 'column_name\n')
        with self.assertRaises(ValueError):
            actions.db_rows(self.service(), 'nope')


class QuizLogQueryTests(unittest.TestCase):
    def service(self, **db):
        return actions.Service(
            name='ubsleepy', title='', description='', container='ubsleepy-bot-1',
            project_dir='/opt/ubsleepy',
            db={'kind': 'postgres', 'container': 'pkdb-db-1',
                'database': 'ubsleepy', 'user': 'ubsleepy_reader', **db})

    def test_the_query_runs_read_only_as_the_reader(self):
        commands = []
        original = actions.run_command
        self.addCleanup(lambda: setattr(actions, 'run_command', original))

        def fake(command, timeout=600, stdin=None):
            commands.append(command)
            return 0, 'n\n1\n'

        actions.run_command = fake
        header, rows = actions.quiz_log_query(self.service(quiz_log=True))('SELECT 1 AS n')
        self.assertEqual((header, rows), (['n'], [['1']]))
        self.assertIn('PGOPTIONS=-c default_transaction_read_only=on', commands[0])
        self.assertIn('ubsleepy_reader', commands[0])

    def test_a_failed_query_raises(self):
        original = actions.run_command
        self.addCleanup(lambda: setattr(actions, 'run_command', original))
        actions.run_command = lambda command, timeout=600, stdin=None: (1, 'boom')
        with self.assertRaises(RuntimeError):
            actions.quiz_log_query(self.service(quiz_log=True))('SELECT 1')

    def test_services_without_the_flag_are_rejected(self):
        with self.assertRaises(ValueError):
            actions.quiz_log_query(self.service())

    def test_the_flag_needs_postgres(self):
        with self.assertRaises(ValueError):
            actions.load_db({'name': 'x', 'db': {
                'kind': 'sqlite', 'path': '/tmp/x.sqlite3', 'quiz_log': True}})


class QuizLogReportTests(unittest.TestCase):
    """quizlog.report に偽のDBを渡し、集計と見立てを確かめる。"""

    def fake(self, has_answer=True, has_user=True):
        self.sqls = []

        def query(sql):
            self.sqls.append(sql)
            if 'information_schema.columns' in sql:
                names = ['id', 'quiz_name', 'at', 'judge', 'question',
                         'answer_input', 'recognized']
                if has_answer:
                    names += ['answer', 'quiz_message_id']
                if has_user:
                    names += ['user_id']
                return ['column_name'], [[name] for name in names]
            if sql.startswith('SELECT quiz_name'):
                return [], [
                    ['ctojq', '6', '4', '2', '1', '3', '2026-10-06', '2026-10-09'],
                    ['bq', '1', '0', '0', '0', '0', '2026-10-09', '2026-10-09'],
                ]
            if sql.startswith('SELECT l.answer'):
                return [], [
                    ['ムシャーナ', '夢夢蝕', 'ムウマ', '3'],
                    ['ムウマ', '夢妖', 'ムシャーナ', '1'],
                ]
            if sql.startswith('SELECT question, answer, ok'):
                return [], [['夢夢蝕', 'ムシャーナ', '1', '3', '1', '1']]
            if sql.startswith('SELECT answer_input, count'):
                return [], [['ムウマ', '4'], ['ルチャブル', '2']]
            if sql.startswith('SELECT a.user_id'):
                return [], [['42', 'るる', '5', '3', '2', '1', '0', '2026-10-09'],
                            ['77', '', '0', '0', '1', '0', '0', '2026-10-08']]
            if sql.startswith('SELECT user_name FROM save_user'):
                return [], [['るる']]
            if sql.startswith('SELECT u.answer_input'):
                return [], [
                    ['ムーマ', 'ムシャーナ', '2', '2026-10-09'],
                    ['ムシャナ', 'ムシャーナ', '1', '2026-10-08'],
                    ['ナニコレ', '摔角鷹人', '1', '2026-10-07'],
                ]
            raise AssertionError(f'unexpected sql: {sql}')

        return query

    def test_the_most_answered_quiz_is_the_default(self):
        view = quizlog.report(self.fake())
        self.assertEqual(view['quiz'], 'ctojq')
        self.assertEqual(view['quiz_label'], '中日翻訳クイズ')
        self.assertEqual(view['summary'][0]['answers'], 10)
        self.assertEqual(view['summary'][0]['correct_rate'], 60.0)
        self.assertEqual(view['summary'][0]['unknown'], 2)

    def test_an_unknown_quiz_name_falls_back_instead_of_reaching_sql(self):
        view = quizlog.report(self.fake(), quiz="x' OR '1'='1")
        self.assertEqual(view['quiz'], 'ctojq')
        for sql in self.sqls:
            self.assertNotIn("OR '1'", sql)

    def test_hard_questions_carry_the_rate_and_the_usual_wrong_answers(self):
        view = quizlog.report(self.fake(), quiz='ctojq', min_answers=4)
        row = view['hard'][0]
        # 割合は（誤答3＋ギブ1）÷（正答1＋誤答3＋ギブ1）
        self.assertEqual((row['answer'], row['answers'], row['wrong_rate']),
                         ('ムシャーナ', 4, 80.0))
        self.assertEqual(row['wrong_answers_text'], 'ムウマ×3')
        hard_sql = next(sql for sql in self.sqls if sql.startswith('SELECT question, answer, ok'))
        self.assertIn('ok + ng + giveup >= 4', hard_sql)
        self.assertIn("quiz_name = 'ctojq'", hard_sql)

    def test_confusions_in_both_directions_are_marked_mutual(self):
        view = quizlog.report(self.fake(), quiz='ctojq')
        self.assertEqual([pair['mutual'] for pair in view['pairs']], [True, True])

    def test_typos_are_matched_to_the_answer_then_to_known_names(self):
        typos = {row['answer_input']: row
                 for row in quizlog.report(self.fake(), quiz='ctojq')['typos']}
        self.assertEqual(typos['ムシャナ']['guess'], '正解の書き間違い')
        self.assertEqual(typos['ムシャナ']['nearest'], 'ムシャーナ')
        self.assertEqual(typos['ムーマ']['guess'], 'ほかの名前の書き間違い')
        self.assertEqual(typos['ムーマ']['nearest'], 'ムウマ')
        self.assertEqual(typos['ナニコレ']['nearest'], '')
        self.assertEqual(list(typos)[0], 'ムーマ')  # 回数の多い順

    def test_the_period_and_the_minimum_are_clamped(self):
        view = quizlog.report(self.fake(), quiz='ctojq', days=12345, min_answers=-5)
        self.assertEqual((view['days'], view['min_answers']), (0, 1))
        view = quizlog.report(self.fake(), quiz='ctojq', days=30)
        self.assertEqual(view['days'], 30)
        self.assertTrue(any("interval '30 days'" in sql for sql in self.sqls))

    def test_older_tables_without_the_answer_column_still_work(self):
        view = quizlog.report(self.fake(has_answer=False), quiz='ctojq')
        self.assertFalse(view['has_answer'])
        for sql in self.sqls:
            self.assertNotIn('max(answer)', sql)
        self.assertTrue(any('mode() WITHIN GROUP' in sql for sql in self.sqls))

    def test_accounts_are_listed_with_names_from_the_save_data(self):
        view = quizlog.report(self.fake(), quiz='ctojq')
        first, second = view['accounts']
        self.assertEqual((first['user_id'], first['user_name'], first['answers'],
                          first['correct_rate'], first['giveup']),
                         ('42', 'るる', 8, 62.5, 2))
        self.assertEqual((second['user_name'], second['correct_rate']), ('', None))
        sql = next(sql for sql in self.sqls if sql.startswith('SELECT a.user_id'))
        self.assertIn('user_id IS NOT NULL', sql)
        self.assertIn('u.guild_id = 0', sql)

    def test_one_account_narrows_every_table_to_that_person(self):
        view = quizlog.report(self.fake(), quiz='ctojq', user='42')
        self.assertEqual((view['user'], view['user_name']), (42, 'るる'))
        self.assertEqual(view['accounts'], [])  # 絞り込み中は一覧を出さない
        for prefix in ('SELECT quiz_name', 'SELECT l.answer', 'SELECT question, answer, ok',
                       'SELECT u.answer_input'):
            sql = next(sql for sql in self.sqls if sql.startswith(prefix))
            self.assertIn('user_id = 42', sql)
        # 書き間違いの照合先は、全員ぶんの語彙のまま
        vocabulary = next(sql for sql in self.sqls if sql.startswith('SELECT answer_input, count'))
        self.assertNotIn('user_id = 42', vocabulary)

    def test_a_bad_account_never_reaches_sql(self):
        view = quizlog.report(self.fake(), quiz='ctojq', user='42 OR 1=1')
        self.assertIsNone(view['user'])
        for sql in self.sqls:
            self.assertNotIn('OR 1=1', sql)

    def test_tables_without_the_user_column_skip_the_accounts(self):
        view = quizlog.report(self.fake(has_user=False), quiz='ctojq', user='42')
        self.assertFalse(view['has_user'])
        self.assertIsNone(view['user'])
        self.assertEqual(view['accounts'], [])
        for sql in self.sqls:
            self.assertNotIn('user_id', sql)

    def test_a_missing_table_is_reported(self):
        view = quizlog.report(lambda sql: (['column_name'], []))
        self.assertIn('quiz_log', view['error'])

    def test_export_matches_the_tables(self):
        view = quizlog.report(self.fake(), quiz='ctojq')
        header, rows = quizlog.export(view, 'pairs')
        self.assertEqual(header, ['正解', '問題', '誤答', '回数', '相互'])
        self.assertEqual(rows[0], ['ムシャーナ', '夢夢蝕', 'ムウマ', 3, '相互'])
        with self.assertRaises(ValueError):
            quizlog.export(view, 'nope')

    def test_similarity_ignores_kana_type_and_brackets(self):
        self.assertEqual(quizlog.normalize('ぎゃろっぷ(ガラルのすがた)'), 'ギャロップガラルノスガタ')
        self.assertEqual(quizlog.similarity('むうま', 'ムウマ'), 1.0)


class StackTests(unittest.TestCase):
    def compose(self):
        return yaml.safe_load((STACK / 'compose.yaml').read_text(encoding='utf-8'))

    def test_the_portal_is_loopback_only(self):
        ports = self.compose()['services']['portal']['ports']
        self.assertEqual(ports, ['127.0.0.1:${PORTAL_PORT:-8095}:8095'])

    def test_the_portal_reaches_docker_and_the_bot_directories(self):
        volumes = self.compose()['services']['portal']['volumes']
        self.assertIn('/var/run/docker.sock:/var/run/docker.sock', volumes)
        self.assertIn('/opt/ubsleepy:/opt/ubsleepy', volumes)
        self.assertIn('/opt/ubsleepy-next:/opt/ubsleepy-next', volumes)
        self.assertIn('/opt/circleauth:/opt/circleauth', volumes)
        self.assertIn('/srv/ubsleepy-next:/srv/ubsleepy-next', volumes)
        self.assertNotIn('/srv/circleauth-test:/srv/circleauth-test', volumes)

    def test_the_registry_marks_the_next_deployment_for_debug(self):
        services = {service.name: service
                    for service in actions.load_services(STACK / 'services.yaml')}
        self.assertTrue(services['ubsleepy-next'].debug)
        self.assertEqual(services['ubsleepy-next'].container, 'ubsleepy-next-bot-1')

    def test_the_registry_introduces_the_bots_with_links(self):
        services = {service.name: service
                    for service in actions.load_services(STACK / 'services.yaml')}
        ubsleepy_urls = [link['url'] for link in services['ubsleepy'].links]
        self.assertIn('https://discord.com/users/1140784885557112873', ubsleepy_urls)
        invite = next(url for url in ubsleepy_urls if 'authorize' in url)
        self.assertIn('client_id=1140784885557112873', invite)
        self.assertIn('https://ruruthegeek.github.io/UBSLEEPY-next/privacy.html',
                      ubsleepy_urls)
        circleauth_urls = [link['url'] for link in services['circleauth'].links]
        self.assertIn('https://discord.com/users/1556306139849957616', circleauth_urls)
        self.assertIn('client_id=1556306139849957616',
                      next(url for url in circleauth_urls if 'authorize' in url))
        self.assertTrue(all(url.startswith('https://')
                            for url in circleauth_urls + ubsleepy_urls))

    def test_the_registry_points_the_apps_at_their_databases(self):
        services = {service.name: service
                    for service in actions.load_services(STACK / 'services.yaml')}
        self.assertEqual(services['ubsleepy'].db['database'], 'ubsleepy')
        self.assertEqual(services['ubsleepy-next'].db['database'], 'ubsleepy_test')
        self.assertEqual(services['ubsleepy'].db['user'], 'ubsleepy_reader')
        self.assertEqual(services['circleauth'].db['path'],
                         '/srv/circleauth/state/save/auth.sqlite3')
        self.assertNotIn('circleauth-test', services)

    def test_the_registry_turns_on_quiz_analysis_for_ubsleepy_only(self):
        services = {service.name: service
                    for service in actions.load_services(STACK / 'services.yaml')}
        self.assertTrue(services['ubsleepy'].db.get('quiz_log'))
        self.assertTrue(services['ubsleepy-next'].db.get('quiz_log'))
        self.assertFalse(services['circleauth'].db.get('quiz_log'))

    def test_the_dns_record_goes_through_forward_auth(self):
        dns = yaml.safe_load((ROOT / 'platform/terraform/dns.yaml').read_text(encoding='utf-8'))
        record = dns['records']['portal']
        self.assertEqual(record['host'], 'apps-01')
        self.assertEqual(record['upstream'], '127.0.0.1:8095')
        self.assertTrue(record['auth'])

    def test_the_authentik_app_is_reconciled(self):
        spec = importlib.util.spec_from_file_location(
            'identity_configure', ROOT / 'stacks/identity/configure.py')
        configure = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(configure)
        self.assertEqual(configure.BOT_PORTAL, 'portal')
        source = (ROOT / 'stacks/identity/configure.py').read_text(encoding='utf-8')
        self.assertIn('configure_bot_portal(api, groups, flows, portal_url)', source)
        # コンテナとmanage.pyを触れる画面なので、adminsだけに開ける。
        self.assertIn("admins may use {BOT_PORTAL}", source)

    def test_the_playbook_targets_apps(self):
        play = yaml.safe_load(
            (ROOT / 'platform/ansible/bot-portal.yml').read_text(encoding='utf-8'))[0]
        self.assertEqual(play['hosts'], 'apps')
        self.assertEqual(play['roles'], ['docker', 'bot_portal', 'tls_proxy'])
