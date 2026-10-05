-- ポケモンの登録（pkdb-entry の画面から使う）。
--
-- 新しいポケモン・新しい姿・既存ポケモンの新作での値を、1回の呼び出しで関係する表へ
-- まとめて入れる。画面は値を集めてこの関数を呼ぶだけにして、どの表へ何を入れるかは
-- ここに置く。関数は所有者（postgres）の権限で動くので、画面用のロール pkdb_entry は
-- 表へ直接書けない。誰が何を登録したかは entry_log に残る。
--
-- 何度流してもよい（CREATE OR REPLACE と IF NOT EXISTS）。

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pkdb_entry') THEN
    CREATE ROLE pkdb_entry LOGIN;
    RAISE NOTICE 'CHANGED: created role pkdb_entry';
  END IF;
END
$$;

CREATE TABLE IF NOT EXISTS pokemondb.entry_log (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  actor text NOT NULL,
  action text NOT NULL,
  detail jsonb NOT NULL
);
COMMENT ON TABLE pokemondb.entry_log IS '登録画面（pkdb-entry）からの登録の記録';

CREATE OR REPLACE FUNCTION pokemondb.refresh_views() RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
BEGIN
  -- 依存の順。元の表を直したら必ず全部作り直す。
  REFRESH MATERIALIZED VIEW mv_latest_pokemon_status;
  REFRESH MATERIALIZED VIEW mv_quiz_status;
  REFRESH MATERIALIZED VIEW mv_bsquiz_status;
  REFRESH MATERIALIZED VIEW mv_pokemon_shiritori_status;
  REFRESH MATERIALIZED VIEW mv_shiritori_words;
  REFRESH MATERIALIZED VIEW mv_lang_quiz;
END
$fn$;

-- 新しい作品（世代）を足す。
CREATE OR REPLACE FUNCTION pokemondb.register_title(
  p_actor text, p_title_group_id text, p_title_name text, p_generation integer, p_region text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
BEGIN
  IF p_title_group_id !~ '^[0-9]{3}$' THEN
    RAISE EXCEPTION '作品IDは3桁の数字です: %', p_title_group_id USING ERRCODE = '22023';
  END IF;
  IF btrim(coalesce(p_title_name, '')) = '' THEN
    RAISE EXCEPTION '作品名を入れてください' USING ERRCODE = '22023';
  END IF;
  IF EXISTS (SELECT FROM title_group WHERE title_group_id = p_title_group_id) THEN
    RAISE EXCEPTION '作品ID % はすでにあります', p_title_group_id USING ERRCODE = '23505';
  END IF;
  INSERT INTO title_group (title_group_id, title_name, generation, region)
  VALUES (p_title_group_id, btrim(p_title_name), p_generation, nullif(btrim(coalesce(p_region, '')), ''));
  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'register_title', jsonb_build_object(
    'title_group_id', p_title_group_id, 'title_name', btrim(p_title_name),
    'generation', p_generation, 'region', p_region));
  RETURN format('作品 %s（%s）を追加しました', btrim(p_title_name), p_title_group_id);
END
$fn$;

-- 特性名から、その作品での特性IDを返す。その作品の行が無ければ直近の作品から写し、
-- どの作品にも無い名前なら新しい特性として足す。
CREATE OR REPLACE FUNCTION pokemondb.entry_ability_id(p_name text, p_title_group_id text)
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_id integer;
BEGIN
  SELECT ability_id INTO v_id FROM ability_data
  WHERE name = p_name AND title_group_id = p_title_group_id;
  IF v_id IS NOT NULL THEN
    RETURN v_id;
  END IF;
  SELECT ability_id INTO v_id FROM ability_data
  WHERE name = p_name ORDER BY title_group_id DESC LIMIT 1;
  IF v_id IS NOT NULL THEN
    INSERT INTO ability_data (ability_id, name, english_name, description, title_group_id)
    SELECT ability_id, name, english_name, description, p_title_group_id
    FROM ability_data WHERE name = p_name ORDER BY title_group_id DESC LIMIT 1;
    RETURN v_id;
  END IF;
  SELECT coalesce(max(ability_id), 0) + 1 INTO v_id FROM ability_data;
  INSERT INTO ability_data (ability_id, name, title_group_id) VALUES (v_id, p_name, p_title_group_id);
  RETURN v_id;
END
$fn$;

CREATE OR REPLACE FUNCTION pokemondb.register_pokemon(
  p_actor text,
  p_ndex_number text,
  p_name text,
  p_form_id text,
  p_form_name text,
  p_title_group_id text,
  p_type_1 text,
  p_type_2 text,
  p_h integer, p_a integer, p_b integer, p_c integer, p_d integer, p_s integer,
  p_ability_1 text,
  p_ability_2 text,
  p_ability_h text,
  p_english_name text,
  p_before_ndex_number text,
  p_before_form_id text,
  p_aliases text[]
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_ndex text := lpad(btrim(coalesce(p_ndex_number, '')), 4, '0');
  v_form text := lpad(btrim(coalesce(nullif(btrim(p_form_id), ''), '00')), 2, '0');
  v_name text := btrim(coalesce(p_name, ''));
  v_form_name text := nullif(btrim(coalesce(p_form_name, '')), '');
  v_existing_name text;
  v_type_1 integer;
  v_type_2 integer;
  v_slot text;
  v_ability text;
  v_alias text;
  v_owner record;
  v_before text := nullif(btrim(coalesce(p_before_ndex_number, '')), '');
  v_before_form text := lpad(btrim(coalesce(nullif(btrim(p_before_form_id), ''), '00')), 2, '0');
  v_new_species boolean := false;
  v_new_form boolean := false;
BEGIN
  IF v_ndex !~ '^[0-9]{4}$' OR v_ndex = '0000' THEN
    RAISE EXCEPTION '図鑑番号は1〜9999の数字です: %', p_ndex_number USING ERRCODE = '22023';
  END IF;
  IF v_form !~ '^[0-9]{2}$' THEN
    RAISE EXCEPTION 'フォーム番号は2桁までの数字です: %', p_form_id USING ERRCODE = '22023';
  END IF;
  IF NOT EXISTS (SELECT FROM title_group WHERE title_group_id = p_title_group_id) THEN
    RAISE EXCEPTION '作品 % がありません', p_title_group_id USING ERRCODE = '22023';
  END IF;
  SELECT type_id INTO v_type_1 FROM type_data WHERE name = btrim(coalesce(p_type_1, ''));
  IF v_type_1 IS NULL THEN
    RAISE EXCEPTION 'タイプ1を選んでください' USING ERRCODE = '22023';
  END IF;
  IF btrim(coalesce(p_type_2, '')) <> '' THEN
    SELECT type_id INTO v_type_2 FROM type_data WHERE name = btrim(p_type_2);
    IF v_type_2 IS NULL THEN
      RAISE EXCEPTION 'タイプ2 % がありません', p_type_2 USING ERRCODE = '22023';
    END IF;
    IF v_type_2 = v_type_1 THEN
      RAISE EXCEPTION 'タイプ1とタイプ2が同じです' USING ERRCODE = '22023';
    END IF;
  END IF;
  IF NOT (p_h BETWEEN 1 AND 255 AND p_a BETWEEN 1 AND 255 AND p_b BETWEEN 1 AND 255
          AND p_c BETWEEN 1 AND 255 AND p_d BETWEEN 1 AND 255 AND p_s BETWEEN 1 AND 255) THEN
    RAISE EXCEPTION '種族値は6つとも1〜255で入れてください' USING ERRCODE = '22023';
  END IF;

  SELECT name INTO v_existing_name FROM pokemon_name WHERE ndex_number = v_ndex;
  IF v_existing_name IS NULL THEN
    IF v_name = '' THEN
      RAISE EXCEPTION '名前を入れてください' USING ERRCODE = '22023';
    END IF;
    IF EXISTS (SELECT FROM pokemon_name WHERE name = v_name) THEN
      RAISE EXCEPTION '% は別の図鑑番号で登録済みです', v_name USING ERRCODE = '23505';
    END IF;
    INSERT INTO pokemon_name (ndex_number, name) VALUES (v_ndex, v_name);
    v_new_species := true;
  ELSIF v_name <> '' AND v_name <> v_existing_name THEN
    RAISE EXCEPTION '図鑑番号 % は % です（入力: %）', v_ndex, v_existing_name, v_name
      USING ERRCODE = '22023';
  ELSE
    v_name := v_existing_name;
  END IF;

  IF NOT EXISTS (SELECT FROM pokemon_name_form WHERE ndex_number = v_ndex AND form_id = v_form) THEN
    INSERT INTO pokemon_name_form (ndex_number, form_id, form_name) VALUES (v_ndex, v_form, v_form_name);
    v_new_form := true;
  END IF;

  IF v_form = '00'
     AND NOT EXISTS (SELECT FROM pokemon_name_lang WHERE ndex_number = v_ndex AND form_id = '00') THEN
    INSERT INTO pokemon_name_lang (ndex_number, form_id, jpn, eng)
    VALUES (v_ndex, '00', v_name, nullif(btrim(coalesce(p_english_name, '')), ''));
  END IF;

  IF EXISTS (SELECT FROM pokemon_status
             WHERE ndex_number = v_ndex AND form_id = v_form AND title_group_id = p_title_group_id) THEN
    RAISE EXCEPTION '%（フォーム %）の作品 % での値は登録済みです', v_name, v_form, p_title_group_id
      USING ERRCODE = '23505';
  END IF;
  INSERT INTO pokemon_status
    (ndex_number, form_id, title_group_id, basestats_h, basestats_a, basestats_b,
     basestats_c, basestats_d, basestats_s, type_1_id, type_2_id)
  VALUES (v_ndex, v_form, p_title_group_id, p_h, p_a, p_b, p_c, p_d, p_s, v_type_1, v_type_2);

  FOR v_slot, v_ability IN
    SELECT * FROM (VALUES ('1', p_ability_1), ('2', p_ability_2), ('H', p_ability_h)) AS slots(slot, ability)
  LOOP
    v_ability := btrim(coalesce(v_ability, ''));
    CONTINUE WHEN v_ability = '';
    INSERT INTO pokemon_ability (ndex_number, form_id, title_group_id, slot, ability_id)
    VALUES (v_ndex, v_form, p_title_group_id, v_slot, entry_ability_id(v_ability, p_title_group_id));
  END LOOP;

  IF v_before IS NOT NULL THEN
    v_before := lpad(v_before, 4, '0');
    IF NOT EXISTS (SELECT FROM pokemon_name_form
                   WHERE ndex_number = v_before AND form_id = v_before_form) THEN
      RAISE EXCEPTION '進化前のポケモン %（フォーム %）がありません', v_before, v_before_form
        USING ERRCODE = '22023';
    END IF;
    INSERT INTO pokemon_evolution
      (before_ndex_number, before_form_id, after_ndex_number, after_form_id)
    VALUES (v_before, v_before_form, v_ndex, v_form)
    ON CONFLICT DO NOTHING;
  END IF;

  FOREACH v_alias IN ARRAY coalesce(p_aliases, ARRAY[]::text[]) LOOP
    v_alias := btrim(v_alias);
    CONTINUE WHEN v_alias = '';
    SELECT ndex_number, form_id INTO v_owner FROM pokemon_name_alias WHERE name_alias = v_alias;
    IF FOUND THEN
      IF v_owner.ndex_number <> v_ndex OR v_owner.form_id <> v_form THEN
        RAISE EXCEPTION 'あだ名 % は別のポケモン（% / %）で使われています',
          v_alias, v_owner.ndex_number, v_owner.form_id USING ERRCODE = '23505';
      END IF;
    ELSE
      INSERT INTO pokemon_name_alias (ndex_number, form_id, name_alias) VALUES (v_ndex, v_form, v_alias);
    END IF;
  END LOOP;

  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'register_pokemon', jsonb_build_object(
    'ndex_number', v_ndex, 'form_id', v_form, 'name', v_name, 'form_name', v_form_name,
    'title_group_id', p_title_group_id, 'type_1', p_type_1, 'type_2', nullif(btrim(coalesce(p_type_2, '')), ''),
    'stats', jsonb_build_array(p_h, p_a, p_b, p_c, p_d, p_s),
    'abilities', jsonb_build_array(p_ability_1, p_ability_2, p_ability_h),
    'before', v_before, 'aliases', to_jsonb(coalesce(p_aliases, ARRAY[]::text[])),
    'new_species', v_new_species, 'new_form', v_new_form));

  PERFORM refresh_views();

  RETURN format('%s %s%s を作品 %s の値で登録しました（%s）',
    v_ndex, v_name, coalesce('（' || v_form_name || '）', ''), p_title_group_id,
    CASE WHEN v_new_species THEN '新しいポケモン'
         WHEN v_new_form THEN '新しい姿'
         ELSE '既存のポケモンの新しい値' END);
END
$fn$;

REVOKE ALL ON FUNCTION pokemondb.refresh_views() FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.register_title(text, text, text, integer, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.entry_ability_id(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.register_pokemon(
  text, text, text, text, text, text, text, text, integer, integer, integer, integer, integer, integer,
  text, text, text, text, text, text, text[]) FROM PUBLIC;

GRANT USAGE ON SCHEMA pokemondb TO pkdb_entry;
GRANT SELECT ON pokemondb.title_group, pokemondb.type_data, pokemondb.ability_data,
  pokemondb.pokemon_name, pokemondb.pokemon_name_form, pokemondb.mv_latest_pokemon_status,
  pokemondb.entry_log TO pkdb_entry;
GRANT EXECUTE ON FUNCTION pokemondb.register_title(text, text, text, integer, text) TO pkdb_entry, pkdb_editor;
GRANT EXECUTE ON FUNCTION pokemondb.register_pokemon(
  text, text, text, text, text, text, text, text, integer, integer, integer, integer, integer, integer,
  text, text, text, text, text, text, text[]) TO pkdb_entry, pkdb_editor;
GRANT SELECT ON pokemondb.entry_log TO pkdb_reader, pkdb_editor;
