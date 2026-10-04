-- manage.py: no-transaction
-- UBSLEEPY のセーブDB（ubsleepy）とロール。存在すれば何もしない。
-- パスワードはここでは触らない（既存ロールの値を変えない）。
-- 空のサーバーへ復元するときは globals.sql がロールとパスワードを入れる。
DO $do$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ubsleepy_writer') THEN
    CREATE ROLE ubsleepy_writer LOGIN;
    RAISE NOTICE 'CHANGED: created role ubsleepy_writer';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ubsleepy_reader') THEN
    CREATE ROLE ubsleepy_reader LOGIN;
    RAISE NOTICE 'CHANGED: created role ubsleepy_reader';
  END IF;
END
$do$;

GRANT ubsleepy_reader TO ubsleepy_writer;

SELECT 'CREATE DATABASE ubsleepy OWNER ubsleepy_writer'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ubsleepy')
\gexec
