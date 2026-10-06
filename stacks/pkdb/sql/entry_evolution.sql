-- 進化（pokemon_evolution）と進化方法（evolution_method）の登録API。
--
-- 進化方法は今まで表が無く、method_id が空のままだった。名前からIDを自動で採る
-- マスタ表を足し、画面は名前を選ぶ・打ち込むだけでよいようにする。
--
-- 何度流してもよい。entry.sql のあとに流す。

CREATE TABLE IF NOT EXISTS pokemondb.evolution_method (
  method_id text PRIMARY KEY,
  method_name text NOT NULL UNIQUE,
  description text
);
COMMENT ON TABLE pokemondb.evolution_method IS '進化の方法のマスタ（名前からIDを自動で採る）';

-- 進化方法の名前からIDを返す。無ければ新しく採番して足す。
CREATE OR REPLACE FUNCTION pokemondb.entry_evolution_method_id(p_name text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_name text := btrim(coalesce(p_name, ''));
  v_id text;
BEGIN
  IF v_name = '' THEN
    RAISE EXCEPTION '進化方法を入れてください' USING ERRCODE = '22023';
  END IF;
  SELECT method_id INTO v_id FROM evolution_method WHERE method_name = v_name;
  IF v_id IS NOT NULL THEN
    RETURN v_id;
  END IF;
  SELECT (coalesce(max(method_id::integer) FILTER (WHERE method_id ~ '^[0-9]+$'), 0) + 1)::text
  INTO v_id FROM evolution_method;
  INSERT INTO evolution_method (method_id, method_name) VALUES (v_id, v_name);
  RETURN v_id;
END
$fn$;

-- 進化の1段（進化前 → 進化後）を保存する。同じ組み合わせがあれば方法と作品を直す。
-- 進化方法は名前からIDを採り、作品は空でもよい（どの作品で分かるかの目印）。
CREATE OR REPLACE FUNCTION pokemondb.set_evolution(
  p_actor text,
  p_before_ndex_number text, p_before_form_id text,
  p_after_ndex_number text, p_after_form_id text,
  p_method_name text,
  p_title_group_id text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_before_ndex text := lpad(btrim(coalesce(p_before_ndex_number, '')), 4, '0');
  v_before_form text := lpad(btrim(coalesce(nullif(btrim(p_before_form_id), ''), '00')), 2, '0');
  v_after_ndex text := lpad(btrim(coalesce(p_after_ndex_number, '')), 4, '0');
  v_after_form text := lpad(btrim(coalesce(nullif(btrim(p_after_form_id), ''), '00')), 2, '0');
  v_title text := nullif(btrim(coalesce(p_title_group_id, '')), '');
  v_method_id text;
  v_before jsonb;
  v_created boolean;
BEGIN
  IF NOT EXISTS (SELECT FROM pokemon_name_form WHERE ndex_number = v_before_ndex AND form_id = v_before_form) THEN
    RAISE EXCEPTION '進化前 %（フォーム %）がありません', v_before_ndex, v_before_form USING ERRCODE = '22023';
  END IF;
  IF NOT EXISTS (SELECT FROM pokemon_name_form WHERE ndex_number = v_after_ndex AND form_id = v_after_form) THEN
    RAISE EXCEPTION '進化後 %（フォーム %）がありません', v_after_ndex, v_after_form USING ERRCODE = '22023';
  END IF;
  IF v_before_ndex = v_after_ndex AND v_before_form = v_after_form THEN
    RAISE EXCEPTION '同じ姿へは進化できません' USING ERRCODE = '22023';
  END IF;
  IF v_title IS NOT NULL THEN
    PERFORM entry_check_title(v_title);
  END IF;
  v_method_id := CASE WHEN btrim(coalesce(p_method_name, '')) = '' THEN NULL
                      ELSE entry_evolution_method_id(p_method_name) END;

  SELECT to_jsonb(e) INTO v_before FROM pokemon_evolution e
  WHERE e.before_ndex_number = v_before_ndex AND e.before_form_id = v_before_form
    AND e.after_ndex_number = v_after_ndex AND e.after_form_id = v_after_form;
  v_created := v_before IS NULL;

  INSERT INTO pokemon_evolution
    (before_ndex_number, before_form_id, after_ndex_number, after_form_id, method_id, title_group_id)
  VALUES (v_before_ndex, v_before_form, v_after_ndex, v_after_form, v_method_id, v_title)
  ON CONFLICT (before_ndex_number, before_form_id, after_ndex_number, after_form_id)
  DO UPDATE SET method_id = excluded.method_id, title_group_id = excluded.title_group_id;

  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'set_evolution', jsonb_build_object(
    'entity', 'evolution', 'before', v_before,
    'after', (SELECT to_jsonb(e) FROM pokemon_evolution e
              WHERE e.before_ndex_number = v_before_ndex AND e.before_form_id = v_before_form
                AND e.after_ndex_number = v_after_ndex AND e.after_form_id = v_after_form)));

  PERFORM refresh_views();
  RETURN format('進化 %s（フォーム %s）→ %s（フォーム %s）を%sしました',
    v_before_ndex, v_before_form, v_after_ndex, v_after_form,
    CASE WHEN v_created THEN '追加' ELSE '修正' END);
END
$fn$;

-- 進化の1段を消す。
CREATE OR REPLACE FUNCTION pokemondb.delete_evolution(
  p_actor text,
  p_before_ndex_number text, p_before_form_id text,
  p_after_ndex_number text, p_after_form_id text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_before_ndex text := lpad(btrim(coalesce(p_before_ndex_number, '')), 4, '0');
  v_before_form text := lpad(btrim(coalesce(nullif(btrim(p_before_form_id), ''), '00')), 2, '0');
  v_after_ndex text := lpad(btrim(coalesce(p_after_ndex_number, '')), 4, '0');
  v_after_form text := lpad(btrim(coalesce(nullif(btrim(p_after_form_id), ''), '00')), 2, '0');
  v_row jsonb;
BEGIN
  SELECT to_jsonb(e) INTO v_row FROM pokemon_evolution e
  WHERE e.before_ndex_number = v_before_ndex AND e.before_form_id = v_before_form
    AND e.after_ndex_number = v_after_ndex AND e.after_form_id = v_after_form;
  IF v_row IS NULL THEN
    RAISE EXCEPTION '進化 %（% ）→ %（% ）がありません',
      v_before_ndex, v_before_form, v_after_ndex, v_after_form USING ERRCODE = '22023';
  END IF;
  DELETE FROM pokemon_evolution
  WHERE before_ndex_number = v_before_ndex AND before_form_id = v_before_form
    AND after_ndex_number = v_after_ndex AND after_form_id = v_after_form;
  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'delete_evolution', jsonb_build_object(
    'entity', 'evolution', 'before', v_row, 'after', NULL));
  PERFORM refresh_views();
  RETURN format('進化 %s（フォーム %s）→ %s（フォーム %s）を消しました',
    v_before_ndex, v_before_form, v_after_ndex, v_after_form);
END
$fn$;

REVOKE ALL ON FUNCTION pokemondb.entry_evolution_method_id(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.set_evolution(text, text, text, text, text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.delete_evolution(text, text, text, text, text) FROM PUBLIC;

GRANT SELECT ON pokemondb.evolution_method TO pkdb_entry, pkdb_reader, pkdb_editor;
GRANT EXECUTE ON FUNCTION pokemondb.set_evolution(text, text, text, text, text, text, text) TO pkdb_entry, pkdb_editor;
GRANT EXECUTE ON FUNCTION pokemondb.delete_evolution(text, text, text, text, text) TO pkdb_entry, pkdb_editor;
