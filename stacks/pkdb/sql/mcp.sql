-- MCP サーバ（pkdb-mcp、AI からの登録）のロール。
--
-- 登録画面のロール pkdb_entry の権限（全表の閲覧と登録の関数の実行）をそのまま
-- 受け継ぎ、表へ直接は書けない。entry_log の db_role で画面の操作と見分ける。
-- パスワードは apps-01 の secrets/mcp_password にだけあり、manage.py が設定する。
--
-- 何度流してもよい。entry*.sql のあとに流す。

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pkdb_mcp') THEN
    CREATE ROLE pkdb_mcp LOGIN;
    RAISE NOTICE 'CHANGED: created role pkdb_mcp';
  END IF;
  IF NOT pg_has_role('pkdb_mcp', 'pkdb_entry', 'MEMBER') THEN
    GRANT pkdb_entry TO pkdb_mcp;
    RAISE NOTICE 'CHANGED: pkdb_mcp inherits pkdb_entry';
  END IF;
END
$$;

-- まとめて登録したあと（pkdb.defer_refresh）に、ビューを1回だけ作り直すため。
GRANT EXECUTE ON FUNCTION pokemondb.refresh_views() TO pkdb_mcp;
GRANT EXECUTE ON FUNCTION pokemondb.refresh_move_views() TO pkdb_mcp;
