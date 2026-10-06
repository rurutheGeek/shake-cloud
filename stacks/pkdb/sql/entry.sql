-- ポケモンDBの登録API（pkdb-entry の画面から使う）。基盤とポケモン・作品。
--
-- 画面は値を集めてここの関数を呼ぶだけにして、どの表へ何を入れるか・IDをどう採るかは
-- ここに置く。関数は所有者（postgres）の権限で動くので、画面用のロール pkdb_entry は
-- 表へ直接書けない。誰が何をしたかは entry_log に before/after 付きで残る。
--
-- 何度流してもよい（CREATE OR REPLACE と IF NOT EXISTS）。引数を変えた関数は、
-- 旧い引数のものを落としてから作り直す。
--
-- ドメインごとの続き:
--   entry_moves.sql   わざ・特性
--   entry_learnsets.sql 覚えるわざ
--   entry_pokedex.sql 図鑑情報・地方図鑑番号
--   entry_evolution.sql 進化方法・進化
--   entry_rankings.sql 対戦使用率

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
CREATE INDEX IF NOT EXISTS entry_log_created_at_idx ON pokemondb.entry_log (created_at DESC);

-- 引数を変えた関数は旧いものを落としてから作る（残すと別関数として残ってしまう）。
DO $$
DECLARE
  v_signature text;
BEGIN
  FOR v_signature IN
    SELECT p.oid::regprocedure::text
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'pokemondb'
      AND p.proname IN ('register_pokemon', 'update_pokemon')
  LOOP
    EXECUTE 'DROP FUNCTION ' || v_signature;
  END LOOP;
END
$$;

-- マテリアライズドビューを作り直す。元の表を直したら必ず依存の順に全部。
CREATE OR REPLACE FUNCTION pokemondb.refresh_views() RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
BEGIN
  REFRESH MATERIALIZED VIEW mv_latest_pokemon_status;
  REFRESH MATERIALIZED VIEW mv_quiz_status;
  REFRESH MATERIALIZED VIEW mv_bsquiz_status;
  REFRESH MATERIALIZED VIEW mv_pokemon_shiritori_status;
  REFRESH MATERIALIZED VIEW mv_shiritori_words;
  REFRESH MATERIALIZED VIEW mv_lang_quiz;
END
$fn$;

-- わざの名前・タイプが変わったときだけで足りる（しりとり用の語だけがわざを見る）。
CREATE OR REPLACE FUNCTION pokemondb.refresh_move_views() RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
BEGIN
  REFRESH MATERIALIZED VIEW mv_shiritori_words;
END
$fn$;

-- タイプ名（日本語）からIDを返す。
CREATE OR REPLACE FUNCTION pokemondb.entry_type_id(p_name text) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_id integer;
BEGIN
  SELECT type_id INTO v_id FROM type_data WHERE name = btrim(coalesce(p_name, ''));
  IF v_id IS NULL THEN
    RAISE EXCEPTION 'タイプ「%」がありません', p_name USING ERRCODE = '22023';
  END IF;
  RETURN v_id;
END
$fn$;

-- 特性名から、その作品での特性IDを返す。その作品の行が無ければ直近の作品から写し、
-- どの作品にも無い名前なら新しい特性として足す。IDは裏で採る。
CREATE OR REPLACE FUNCTION pokemondb.entry_ability_id(p_name text, p_title_group_id text)
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_name text := btrim(coalesce(p_name, ''));
  v_id integer;
BEGIN
  IF v_name = '' THEN
    RAISE EXCEPTION '特性名を入れてください' USING ERRCODE = '22023';
  END IF;
  SELECT ability_id INTO v_id FROM ability_data
  WHERE name = v_name AND title_group_id = p_title_group_id;
  IF v_id IS NOT NULL THEN
    RETURN v_id;
  END IF;
  SELECT ability_id INTO v_id FROM ability_data
  WHERE name = v_name ORDER BY title_group_id DESC LIMIT 1;
  IF v_id IS NOT NULL THEN
    INSERT INTO ability_data (ability_id, name, english_name, description, title_group_id)
    SELECT ability_id, name, english_name, description, p_title_group_id
    FROM ability_data WHERE name = v_name ORDER BY title_group_id DESC LIMIT 1;
    RETURN v_id;
  END IF;
  SELECT coalesce(max(ability_id), 0) + 1 INTO v_id FROM ability_data;
  INSERT INTO ability_data (ability_id, name, title_group_id) VALUES (v_id, v_name, p_title_group_id);
  RETURN v_id;
END
$fn$;

-- わざ名から、その作品でのわざIDを返す。その作品の行が無ければ直近の作品の内容を写し、
-- どの作品にも無い名前なら新しいわざとして足す。IDは裏で採る。
CREATE OR REPLACE FUNCTION pokemondb.entry_move_id(p_name text, p_title_group_id text)
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_name text := btrim(coalesce(p_name, ''));
  v_id integer;
BEGIN
  IF v_name = '' THEN
    RAISE EXCEPTION 'わざ名を入れてください' USING ERRCODE = '22023';
  END IF;
  SELECT move_id INTO v_id FROM move_data
  WHERE name = v_name AND title_group_id = p_title_group_id;
  IF v_id IS NOT NULL THEN
    RETURN v_id;
  END IF;
  SELECT move_id INTO v_id FROM move_data
  WHERE name = v_name ORDER BY title_group_id DESC LIMIT 1;
  IF v_id IS NOT NULL THEN
    INSERT INTO move_data (move_id, name, english_name, type, category, power, accuracy,
                           pp, priority, target, effect_chance, description, title_group_id, notes)
    SELECT move_id, name, english_name, type, category, power, accuracy,
           pp, priority, target, effect_chance, description, p_title_group_id, notes
    FROM move_data WHERE name = v_name ORDER BY title_group_id DESC LIMIT 1;
    RETURN v_id;
  END IF;
  SELECT coalesce(max(move_id), 0) + 1 INTO v_id FROM move_data;
  INSERT INTO move_data (move_id, name, title_group_id) VALUES (v_id, v_name, p_title_group_id);
  RETURN v_id;
END
$fn$;

-- 覚え方（レベルアップ・わざマシンなど）の日本語名からIDを返す。6種の固定。
CREATE OR REPLACE FUNCTION pokemondb.entry_method_id(p_name text) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_id bigint;
BEGIN
  SELECT method_id INTO v_id FROM move_learn_method
  WHERE method_name = btrim(coalesce(p_name, '')) OR pokeapi_name = lower(btrim(coalesce(p_name, '')));
  IF v_id IS NULL THEN
    RAISE EXCEPTION '覚え方「%」がありません', p_name USING ERRCODE = '22023';
  END IF;
  RETURN v_id;
END
$fn$;

-- 名前から、ポケモンの言語名の行を配列なしで組み立てる（before/after の記録用）。
CREATE OR REPLACE FUNCTION pokemondb.entry_lang_snapshot(p_ndex text, p_form text)
RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
  SELECT coalesce(
    (SELECT jsonb_build_object('jpn', l.jpn, 'eng', l.eng, 'fra', l.fra, 'ger', l.ger,
                               'ita', l.ita, 'kor', l.kor, 'spa', l.spa, 'chs', l.chs,
                               'cht', l.cht, 'romaji_trademarked', l.romaji_trademarked,
                               'romaji_hepburn', l.romaji_hepburn)
     FROM pokemon_name_lang l
     WHERE l.ndex_number = p_ndex AND l.form_id = p_form),
    'null'::jsonb)
$fn$;

-- ポケモンのあだ名の一覧を JSON で返す（before/after の記録用）。
CREATE OR REPLACE FUNCTION pokemondb.entry_alias_snapshot(p_ndex text, p_form text)
RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
  SELECT coalesce(
    (SELECT jsonb_agg(al.name_alias ORDER BY al.name_alias)
     FROM pokemon_name_alias al
     WHERE al.ndex_number = p_ndex AND al.form_id = p_form),
    '[]'::jsonb)
$fn$;

-- 新しい作品（世代）を足す。
CREATE OR REPLACE FUNCTION pokemondb.register_title(
  p_actor text, p_title_group_id text, p_title_name text, p_generation integer, p_region text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_id text := btrim(coalesce(p_title_group_id, ''));
  v_name text := btrim(coalesce(p_title_name, ''));
  v_region text := nullif(btrim(coalesce(p_region, '')), '');
BEGIN
  IF v_id !~ '^[0-9]{3}$' THEN
    RAISE EXCEPTION '作品IDは3桁の数字です: %', p_title_group_id USING ERRCODE = '22023';
  END IF;
  IF v_name = '' THEN
    RAISE EXCEPTION '作品名を入れてください' USING ERRCODE = '22023';
  END IF;
  IF EXISTS (SELECT FROM title_group WHERE title_group_id = v_id) THEN
    RAISE EXCEPTION '作品ID % はすでにあります', v_id USING ERRCODE = '23505';
  END IF;
  INSERT INTO title_group (title_group_id, title_name, generation, region)
  VALUES (v_id, v_name, p_generation, v_region);
  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'register_title', jsonb_build_object(
    'entity', 'title', 'before', NULL,
    'after', jsonb_build_object('title_group_id', v_id, 'title_name', v_name,
                                'generation', p_generation, 'region', v_region)));
  RETURN format('作品 %s（%s）を追加しました', v_name, v_id);
END
$fn$;

-- 作品の名前・世代・地方を直す。
CREATE OR REPLACE FUNCTION pokemondb.update_title(
  p_actor text, p_title_group_id text, p_title_name text, p_generation integer, p_region text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_before jsonb;
  v_name text := btrim(coalesce(p_title_name, ''));
  v_region text := nullif(btrim(coalesce(p_region, '')), '');
BEGIN
  IF v_name = '' THEN
    RAISE EXCEPTION '作品名を入れてください' USING ERRCODE = '22023';
  END IF;
  SELECT jsonb_build_object('title_group_id', title_group_id, 'title_name', title_name,
                            'generation', generation, 'region', region)
  INTO v_before FROM title_group WHERE title_group_id = p_title_group_id;
  IF v_before IS NULL THEN
    RAISE EXCEPTION '作品 % がありません', p_title_group_id USING ERRCODE = '22023';
  END IF;
  UPDATE title_group SET title_name = v_name, generation = p_generation, region = v_region
  WHERE title_group_id = p_title_group_id;
  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'update_title', jsonb_build_object(
    'entity', 'title', 'before', v_before,
    'after', jsonb_build_object('title_group_id', p_title_group_id, 'title_name', v_name,
                                'generation', p_generation, 'region', v_region)));
  RETURN format('作品 %s（%s）を修正しました', v_name, p_title_group_id);
END
$fn$;

-- 作品1本（発売年月日つき）を足す・直す。同じ4桁IDなら置き換える。
CREATE OR REPLACE FUNCTION pokemondb.save_title_solo(
  p_actor text, p_title_id text, p_title_name text, p_title_group_id text,
  p_release_year integer, p_release_month integer, p_release_date integer
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_id text := btrim(coalesce(p_title_id, ''));
  v_name text := btrim(coalesce(p_title_name, ''));
  v_before jsonb;
  v_created boolean := false;
BEGIN
  IF v_id !~ '^[0-9]{4}$' THEN
    RAISE EXCEPTION '作品IDは4桁の数字です: %', p_title_id USING ERRCODE = '22023';
  END IF;
  IF v_name = '' THEN
    RAISE EXCEPTION '作品名を入れてください' USING ERRCODE = '22023';
  END IF;
  IF NOT EXISTS (SELECT FROM title_group WHERE title_group_id = p_title_group_id) THEN
    RAISE EXCEPTION '作品グループ % がありません', p_title_group_id USING ERRCODE = '22023';
  END IF;
  IF p_release_month IS NOT NULL AND NOT (p_release_month BETWEEN 1 AND 12) THEN
    RAISE EXCEPTION '発売月は1〜12です' USING ERRCODE = '22023';
  END IF;
  IF p_release_date IS NOT NULL AND NOT (p_release_date BETWEEN 1 AND 31) THEN
    RAISE EXCEPTION '発売日は1〜31です' USING ERRCODE = '22023';
  END IF;
  SELECT jsonb_build_object('title_id', title_id, 'title_name', title_name,
                            'title_group_id', title_group_id, 'release_year', release_year,
                            'release_month', release_month, 'release_date', release_date)
  INTO v_before FROM title_solo WHERE title_id = v_id;
  INSERT INTO title_solo (title_id, title_name, title_group_id, release_year, release_month, release_date)
  VALUES (v_id, v_name, p_title_group_id, p_release_year, p_release_month, p_release_date)
  ON CONFLICT (title_id) DO UPDATE
    SET title_name = excluded.title_name, title_group_id = excluded.title_group_id,
        release_year = excluded.release_year, release_month = excluded.release_month,
        release_date = excluded.release_date;
  v_created := v_before IS NULL;
  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, CASE WHEN v_created THEN 'register_title_solo' ELSE 'update_title_solo' END,
    jsonb_build_object(
      'entity', 'title_solo', 'before', v_before,
      'after', jsonb_build_object('title_id', v_id, 'title_name', v_name,
                                  'title_group_id', p_title_group_id,
                                  'release_year', p_release_year, 'release_month', p_release_month,
                                  'release_date', p_release_date)));
  RETURN format('作品 %s（%s）を%sしました', v_name, v_id, CASE WHEN v_created THEN '追加' ELSE '修正' END);
END
$fn$;

-- 新しいポケモン・新しい姿・既存ポケモンの新作での値を、1回の呼び出しで
-- 関係する表へまとめて入れる。タイプID・特性ID・言語の行・進化のリンク・あだ名は
-- 必要なら裏で作る。既にある図鑑番号・姿・作品の組み合わせは error（修正は update_pokemon）。
CREATE OR REPLACE FUNCTION pokemondb.register_pokemon(
  p_actor text,
  p_ndex_number text,
  p_name text,
  p_form_id text,
  p_form_name text,
  p_gender text,
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
  p_evolution_method text,
  p_aliases text[]
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_ndex text := lpad(btrim(coalesce(p_ndex_number, '')), 4, '0');
  v_form text := lpad(btrim(coalesce(nullif(btrim(p_form_id), ''), '00')), 2, '0');
  v_name text := btrim(coalesce(p_name, ''));
  v_form_name text := nullif(btrim(coalesce(p_form_name, '')), '');
  v_gender text := nullif(btrim(coalesce(p_gender, '')), '');
  v_existing_name text;
  v_type_1 integer;
  v_type_2 integer;
  v_slot text;
  v_ability text;
  v_ability_id integer;
  v_seen integer[] := ARRAY[]::integer[];
  v_alias text;
  v_wanted text[] := ARRAY[]::text[];
  v_owner record;
  v_before text := nullif(btrim(coalesce(p_before_ndex_number, '')), '');
  v_before_form text := lpad(btrim(coalesce(nullif(btrim(p_before_form_id), ''), '00')), 2, '0');
  v_method_id text;
  v_new_species boolean := false;
  v_new_form boolean := false;
  v_langs jsonb;
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
  v_type_1 := entry_type_id(p_type_1);
  IF btrim(coalesce(p_type_2, '')) <> '' THEN
    v_type_2 := entry_type_id(p_type_2);
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
    INSERT INTO pokemon_name_form (ndex_number, form_id, form_name, gender)
    VALUES (v_ndex, v_form, v_form_name, v_gender);
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
    v_ability_id := entry_ability_id(v_ability, p_title_group_id);
    IF v_ability_id = ANY (v_seen) THEN
      RAISE EXCEPTION '同じ特性が複数の枠に入っています: %', v_ability USING ERRCODE = '22023';
    END IF;
    v_seen := v_seen || v_ability_id;
    INSERT INTO pokemon_ability (ndex_number, form_id, title_group_id, slot, ability_id)
    VALUES (v_ndex, v_form, p_title_group_id, v_slot, v_ability_id);
  END LOOP;

  IF v_before IS NOT NULL THEN
    v_before := lpad(v_before, 4, '0');
    IF NOT EXISTS (SELECT FROM pokemon_name_form
                   WHERE ndex_number = v_before AND form_id = v_before_form) THEN
      RAISE EXCEPTION '進化前のポケモン %（フォーム %）がありません', v_before, v_before_form
        USING ERRCODE = '22023';
    END IF;
    v_method_id := CASE WHEN btrim(coalesce(p_evolution_method, '')) = '' THEN NULL
                        ELSE entry_evolution_method_id(p_evolution_method) END;
    INSERT INTO pokemon_evolution
      (before_ndex_number, before_form_id, after_ndex_number, after_form_id, method_id, title_group_id)
    VALUES (v_before, v_before_form, v_ndex, v_form, v_method_id, p_title_group_id)
    ON CONFLICT (before_ndex_number, before_form_id, after_ndex_number, after_form_id)
    DO UPDATE SET method_id = coalesce(excluded.method_id, pokemon_evolution.method_id),
                  title_group_id = coalesce(excluded.title_group_id, pokemon_evolution.title_group_id);
  END IF;

  FOREACH v_alias IN ARRAY coalesce(p_aliases, ARRAY[]::text[]) LOOP
    v_alias := btrim(v_alias);
    CONTINUE WHEN v_alias = '';
    v_wanted := v_wanted || v_alias;
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
    'entity', 'pokemon', 'before', NULL,
    'after', jsonb_build_object(
      'ndex_number', v_ndex, 'form_id', v_form, 'name', v_name, 'form_name', v_form_name,
      'gender', v_gender, 'title_group_id', p_title_group_id,
      'type_1', p_type_1, 'type_2', nullif(btrim(coalesce(p_type_2, '')), ''),
      'stats', jsonb_build_array(p_h, p_a, p_b, p_c, p_d, p_s),
      'abilities', jsonb_build_array(p_ability_1, p_ability_2, p_ability_h),
      'english', nullif(btrim(coalesce(p_english_name, '')), ''),
      'before_ndex_number', v_before, 'before_form_id', CASE WHEN v_before IS NULL THEN NULL ELSE v_before_form END,
      'evolution_method', nullif(btrim(coalesce(p_evolution_method, '')), ''),
      'aliases', to_jsonb(v_wanted),
      'new_species', v_new_species, 'new_form', v_new_form)));

  PERFORM refresh_views();

  RETURN format('%s %s%s を作品 %s の値で登録しました（%s）',
    v_ndex, v_name, coalesce('（' || v_form_name || '）', ''), p_title_group_id,
    CASE WHEN v_new_species THEN '新しいポケモン'
         WHEN v_new_form THEN '新しい姿'
         ELSE '既存のポケモンの新しい値' END);
END
$fn$;

-- ある作品での種族値・タイプ・特性を直す。対象は（図鑑番号・フォーム・作品）で決まる1行。
-- 直す前の値は entry_log に残るので、画面の「履歴」から戻せる。
CREATE OR REPLACE FUNCTION pokemondb.update_pokemon(
  p_actor text,
  p_ndex_number text,
  p_form_id text,
  p_title_group_id text,
  p_type_1 text,
  p_type_2 text,
  p_h integer, p_a integer, p_b integer, p_c integer, p_d integer, p_s integer,
  p_ability_1 text,
  p_ability_2 text,
  p_ability_h text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_ndex text := lpad(btrim(coalesce(p_ndex_number, '')), 4, '0');
  v_form text := lpad(btrim(coalesce(nullif(btrim(p_form_id), ''), '00')), 2, '0');
  v_type_1 integer;
  v_type_2 integer;
  v_slot text;
  v_ability text;
  v_ability_id integer;
  v_seen integer[] := ARRAY[]::integer[];
  v_name text;
  v_before jsonb;
  v_after jsonb;
BEGIN
  IF NOT EXISTS (SELECT FROM pokemon_name_form WHERE ndex_number = v_ndex AND form_id = v_form) THEN
    RAISE EXCEPTION '図鑑番号 %・フォーム % の登録がありません', v_ndex, v_form USING ERRCODE = '22023';
  END IF;
  v_type_1 := entry_type_id(p_type_1);
  IF btrim(coalesce(p_type_2, '')) <> '' THEN
    v_type_2 := entry_type_id(p_type_2);
    IF v_type_2 = v_type_1 THEN
      RAISE EXCEPTION 'タイプ1とタイプ2が同じです' USING ERRCODE = '22023';
    END IF;
  END IF;
  IF NOT (p_h BETWEEN 1 AND 255 AND p_a BETWEEN 1 AND 255 AND p_b BETWEEN 1 AND 255
          AND p_c BETWEEN 1 AND 255 AND p_d BETWEEN 1 AND 255 AND p_s BETWEEN 1 AND 255) THEN
    RAISE EXCEPTION '種族値は6つとも1〜255で入れてください' USING ERRCODE = '22023';
  END IF;

  SELECT n.name,
         jsonb_build_object(
           'type_1', t1.name, 'type_2', t2.name,
           'stats', jsonb_build_array(s.basestats_h, s.basestats_a, s.basestats_b,
                                      s.basestats_c, s.basestats_d, s.basestats_s),
           'abilities', coalesce((SELECT jsonb_object_agg(a.slot, ad.name ORDER BY a.slot)
                                  FROM pokemon_ability a
                                  JOIN ability_data ad ON ad.ability_id = a.ability_id
                                                       AND ad.title_group_id = a.title_group_id
                                  WHERE a.ndex_number = s.ndex_number AND a.form_id = s.form_id
                                    AND a.title_group_id = s.title_group_id), '{}'::jsonb))
  INTO v_name, v_before
  FROM pokemon_status s
  JOIN pokemon_name n ON n.ndex_number = s.ndex_number
  JOIN type_data t1 ON t1.type_id = s.type_1_id
  LEFT JOIN type_data t2 ON t2.type_id = s.type_2_id
  WHERE s.ndex_number = v_ndex AND s.form_id = v_form AND s.title_group_id = p_title_group_id;
  IF v_before IS NULL THEN
    RAISE EXCEPTION '図鑑番号 %・フォーム %・作品 % の登録がありません', v_ndex, v_form, p_title_group_id
      USING ERRCODE = '22023';
  END IF;

  UPDATE pokemon_status
  SET basestats_h = p_h, basestats_a = p_a, basestats_b = p_b,
      basestats_c = p_c, basestats_d = p_d, basestats_s = p_s,
      type_1_id = v_type_1, type_2_id = v_type_2
  WHERE ndex_number = v_ndex AND form_id = v_form AND title_group_id = p_title_group_id;

  DELETE FROM pokemon_ability
  WHERE ndex_number = v_ndex AND form_id = v_form AND title_group_id = p_title_group_id;
  FOR v_slot, v_ability IN
    SELECT * FROM (VALUES ('1', p_ability_1), ('2', p_ability_2), ('H', p_ability_h)) AS slots(slot, ability)
  LOOP
    v_ability := btrim(coalesce(v_ability, ''));
    CONTINUE WHEN v_ability = '';
    v_ability_id := entry_ability_id(v_ability, p_title_group_id);
    IF v_ability_id = ANY (v_seen) THEN
      RAISE EXCEPTION '同じ特性が複数の枠に入っています: %', v_ability USING ERRCODE = '22023';
    END IF;
    v_seen := v_seen || v_ability_id;
    INSERT INTO pokemon_ability (ndex_number, form_id, title_group_id, slot, ability_id)
    VALUES (v_ndex, v_form, p_title_group_id, v_slot, v_ability_id);
  END LOOP;

  v_after := jsonb_build_object(
    'type_1', p_type_1, 'type_2', nullif(btrim(coalesce(p_type_2, '')), ''),
    'stats', jsonb_build_array(p_h, p_a, p_b, p_c, p_d, p_s),
    'abilities', jsonb_build_object(
      '1', nullif(btrim(coalesce(p_ability_1, '')), ''),
      '2', nullif(btrim(coalesce(p_ability_2, '')), ''),
      'H', nullif(btrim(coalesce(p_ability_h, '')), '')));

  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'update_pokemon', jsonb_build_object(
    'entity', 'pokemon', 'ndex_number', v_ndex, 'form_id', v_form, 'name', v_name,
    'title_group_id', p_title_group_id, 'before', v_before, 'after', v_after));

  PERFORM refresh_views();
  RETURN format('%s %s（フォーム %s）の作品 %s の値を修正しました', v_ndex, v_name, v_form, p_title_group_id);
END
$fn$;

-- 名前・各言語名・姿の名前・性別・あだ名をまとめて直す。
-- 言語名の行は基本の姿（00）にだけ作る（クイズのビューが種類ごとに1行を前提にしている）。
CREATE OR REPLACE FUNCTION pokemondb.update_pokemon_names(
  p_actor text,
  p_ndex_number text,
  p_form_id text,
  p_jpn text,
  p_eng text, p_fra text, p_ger text, p_ita text, p_kor text, p_spa text, p_chs text, p_cht text,
  p_romaji_trademarked text,
  p_romaji_hepburn text,
  p_form_name text,
  p_gender text,
  p_aliases text[]
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_ndex text := lpad(btrim(coalesce(p_ndex_number, '')), 4, '0');
  v_form text := lpad(btrim(coalesce(nullif(btrim(p_form_id), ''), '00')), 2, '0');
  v_jpn text := btrim(coalesce(p_jpn, ''));
  v_form_name text := nullif(btrim(coalesce(p_form_name, '')), '');
  v_gender text := nullif(btrim(coalesce(p_gender, '')), '');
  v_old_name text;
  v_before jsonb;
  v_after jsonb;
  v_alias text;
  v_wanted text[] := ARRAY[]::text[];
  v_owner record;
  v_lang_present boolean := p_eng <> '' OR p_fra <> '' OR p_ger <> '' OR p_ita <> ''
    OR p_kor <> '' OR p_spa <> '' OR p_chs <> '' OR p_cht <> ''
    OR p_romaji_trademarked <> '' OR p_romaji_hepburn <> '';
BEGIN
  SELECT n.name INTO v_old_name FROM pokemon_name n WHERE n.ndex_number = v_ndex;
  IF v_old_name IS NULL THEN
    RAISE EXCEPTION '図鑑番号 % の登録がありません', v_ndex USING ERRCODE = '22023';
  END IF;
  IF NOT EXISTS (SELECT FROM pokemon_name_form WHERE ndex_number = v_ndex AND form_id = v_form) THEN
    RAISE EXCEPTION '図鑑番号 %・フォーム % の登録がありません', v_ndex, v_form USING ERRCODE = '22023';
  END IF;
  IF v_form <> '00' AND v_lang_present THEN
    RAISE EXCEPTION '言語名は基本の姿（フォーム 00）にだけ付けられます' USING ERRCODE = '22023';
  END IF;

  v_before := jsonb_build_object(
    'jpn', v_old_name,
    'form_name', (SELECT form_name FROM pokemon_name_form WHERE ndex_number = v_ndex AND form_id = v_form),
    'gender', (SELECT gender FROM pokemon_name_form WHERE ndex_number = v_ndex AND form_id = v_form),
    'languages', entry_lang_snapshot(v_ndex, v_form),
    'aliases', entry_alias_snapshot(v_ndex, v_form));

  IF v_jpn <> '' AND v_jpn <> v_old_name THEN
    IF EXISTS (SELECT FROM pokemon_name WHERE name = v_jpn) THEN
      RAISE EXCEPTION '% は別の図鑑番号で登録済みです', v_jpn USING ERRCODE = '23505';
    END IF;
    UPDATE pokemon_name SET name = v_jpn WHERE ndex_number = v_ndex;
    UPDATE pokemon_name_lang SET jpn = v_jpn WHERE ndex_number = v_ndex AND form_id = '00';
  ELSE
    v_jpn := v_old_name;
  END IF;

  UPDATE pokemon_name_form SET form_name = v_form_name, gender = v_gender
  WHERE ndex_number = v_ndex AND form_id = v_form;

  IF v_form = '00' THEN
    INSERT INTO pokemon_name_lang (ndex_number, form_id, jpn, eng, fra, ger, ita, kor, spa, chs, cht,
                                   romaji_trademarked, romaji_hepburn)
    VALUES (v_ndex, '00', v_jpn, nullif(btrim(coalesce(p_eng, '')), ''),
            nullif(btrim(coalesce(p_fra, '')), ''), nullif(btrim(coalesce(p_ger, '')), ''),
            nullif(btrim(coalesce(p_ita, '')), ''), nullif(btrim(coalesce(p_kor, '')), ''),
            nullif(btrim(coalesce(p_spa, '')), ''), nullif(btrim(coalesce(p_chs, '')), ''),
            nullif(btrim(coalesce(p_cht, '')), ''), nullif(btrim(coalesce(p_romaji_trademarked, '')), ''),
            nullif(btrim(coalesce(p_romaji_hepburn, '')), ''))
    ON CONFLICT (ndex_number, form_id) DO UPDATE
      SET jpn = excluded.jpn, eng = excluded.eng, fra = excluded.fra, ger = excluded.ger,
          ita = excluded.ita, kor = excluded.kor, spa = excluded.spa, chs = excluded.chs,
          cht = excluded.cht, romaji_trademarked = excluded.romaji_trademarked,
          romaji_hepburn = excluded.romaji_hepburn;
  END IF;

  FOREACH v_alias IN ARRAY coalesce(p_aliases, ARRAY[]::text[]) LOOP
    v_alias := btrim(v_alias);
    CONTINUE WHEN v_alias = '';
    v_wanted := v_wanted || v_alias;
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
  DELETE FROM pokemon_name_alias
  WHERE ndex_number = v_ndex AND form_id = v_form AND NOT (name_alias = ANY (v_wanted));

  v_after := jsonb_build_object(
    'jpn', v_jpn, 'form_name', v_form_name, 'gender', v_gender,
    'languages', entry_lang_snapshot(v_ndex, v_form),
    'aliases', entry_alias_snapshot(v_ndex, v_form));

  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'update_pokemon_names', jsonb_build_object(
    'entity', 'pokemon_names', 'ndex_number', v_ndex, 'form_id', v_form,
    'before', v_before, 'after', v_after));

  PERFORM refresh_views();
  RETURN format('%s %s（フォーム %s）の名前を修正しました', v_ndex, v_jpn, v_form);
END
$fn$;

-- ある姿・作品の値（種族値・タイプ・特性）を、同じポケモンの複数の姿へまとめて写す。
-- 新しい姿を一気に足すとき用。同じ作品の行があれば、overwrite のときだけ直す。
CREATE OR REPLACE FUNCTION pokemondb.copy_pokemon_status(
  p_actor text,
  p_ndex_number text,
  p_from_form text,
  p_from_title text,
  p_to_forms text[],
  p_to_title text,
  p_overwrite boolean
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_ndex text := lpad(btrim(coalesce(p_ndex_number, '')), 4, '0');
  v_from_form text := lpad(btrim(coalesce(nullif(btrim(p_from_form), ''), '00')), 2, '0');
  v_to_title text := coalesce(nullif(btrim(coalesce(p_to_title, '')), ''), p_from_title);
  v_name text;
  v_form text;
  v_source record;
  v_copied integer := 0;
  v_skipped text[] := ARRAY[]::text[];
  v_slot text;
BEGIN
  SELECT n.name INTO v_name FROM pokemon_name n WHERE n.ndex_number = v_ndex;
  IF v_name IS NULL THEN
    RAISE EXCEPTION '図鑑番号 % の登録がありません', v_ndex USING ERRCODE = '22023';
  END IF;
  IF NOT EXISTS (SELECT FROM title_group WHERE title_group_id = v_to_title) THEN
    RAISE EXCEPTION '作品 % がありません', v_to_title USING ERRCODE = '22023';
  END IF;
  SELECT s.type_1_id, s.type_2_id, s.basestats_h, s.basestats_a, s.basestats_b,
         s.basestats_c, s.basestats_d, s.basestats_s
  INTO v_source
  FROM pokemon_status s
  WHERE s.ndex_number = v_ndex AND s.form_id = v_from_form AND s.title_group_id = p_from_title;
  IF NOT FOUND THEN
    RAISE EXCEPTION '%（フォーム %）の作品 % の値がありません', v_name, v_from_form, p_from_title
      USING ERRCODE = '22023';
  END IF;

  FOREACH v_form IN ARRAY coalesce(p_to_forms, ARRAY[]::text[]) LOOP
    IF v_form = v_from_form THEN
      CONTINUE;
    END IF;
    IF NOT EXISTS (SELECT FROM pokemon_name_form WHERE ndex_number = v_ndex AND form_id = v_form) THEN
      RAISE EXCEPTION 'フォーム % がありません', v_form USING ERRCODE = '22023';
    END IF;
    IF EXISTS (SELECT FROM pokemon_status
               WHERE ndex_number = v_ndex AND form_id = v_form AND title_group_id = v_to_title) THEN
      IF NOT p_overwrite THEN
        v_skipped := v_skipped || v_form;
        CONTINUE;
      END IF;
      UPDATE pokemon_status
      SET basestats_h = v_source.basestats_h, basestats_a = v_source.basestats_a,
          basestats_b = v_source.basestats_b, basestats_c = v_source.basestats_c,
          basestats_d = v_source.basestats_d, basestats_s = v_source.basestats_s,
          type_1_id = v_source.type_1_id, type_2_id = v_source.type_2_id
      WHERE ndex_number = v_ndex AND form_id = v_form AND title_group_id = v_to_title;
      DELETE FROM pokemon_ability
      WHERE ndex_number = v_ndex AND form_id = v_form AND title_group_id = v_to_title;
    ELSE
      INSERT INTO pokemon_status
        (ndex_number, form_id, title_group_id, basestats_h, basestats_a, basestats_b,
         basestats_c, basestats_d, basestats_s, type_1_id, type_2_id)
      VALUES (v_ndex, v_form, v_to_title, v_source.basestats_h, v_source.basestats_a,
              v_source.basestats_b, v_source.basestats_c, v_source.basestats_d,
              v_source.basestats_s, v_source.type_1_id, v_source.type_2_id);
    END IF;
    FOR v_slot IN SELECT a.slot FROM pokemon_ability a
                  WHERE a.ndex_number = v_ndex AND a.form_id = v_from_form
                    AND a.title_group_id = p_from_title
    LOOP
      INSERT INTO pokemon_ability (ndex_number, form_id, title_group_id, slot, ability_id)
      SELECT v_ndex, v_form, v_to_title, a.slot, a.ability_id
      FROM pokemon_ability a
      WHERE a.ndex_number = v_ndex AND a.form_id = v_from_form
        AND a.title_group_id = p_from_title AND a.slot = v_slot;
    END LOOP;
    v_copied := v_copied + 1;
  END LOOP;
  PERFORM refresh_views();
  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'copy_pokemon_status', jsonb_build_object(
    'entity', 'pokemon', 'ndex_number', v_ndex, 'from_form', v_from_form,
    'from_title', p_from_title, 'to_title', v_to_title,
    'forms', to_jsonb(coalesce(p_to_forms, ARRAY[]::text[])),
    'copied', v_copied, 'skipped', to_jsonb(v_skipped)));
  RETURN format('%s のフォーム %s（作品 %s）の値を作品 %s へ %s 件写しました%s',
    v_name, v_from_form, p_from_title, v_to_title, v_copied,
    CASE WHEN array_length(v_skipped, 1) IS NULL THEN ''
         ELSE format('（登録済みのため飛ばしたフォーム: %s）', array_to_string(v_skipped, ', ')) END);
END
$fn$;

REVOKE ALL ON FUNCTION pokemondb.refresh_views() FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.refresh_move_views() FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.entry_type_id(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.entry_ability_id(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.entry_move_id(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.entry_method_id(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.entry_lang_snapshot(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.entry_alias_snapshot(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.register_title(text, text, text, integer, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.update_title(text, text, text, integer, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.save_title_solo(text, text, text, text, integer, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.register_pokemon(
  text, text, text, text, text, text, text, text, text,
  integer, integer, integer, integer, integer, integer,
  text, text, text, text, text, text, text, text[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.update_pokemon(
  text, text, text, text, text, text,
  integer, integer, integer, integer, integer, integer,
  text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.update_pokemon_names(
  text, text, text, text, text, text, text, text, text, text, text, text, text, text, text, text, text[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.copy_pokemon_status(
  text, text, text, text, text[], text, boolean) FROM PUBLIC;

GRANT USAGE ON SCHEMA pokemondb TO pkdb_entry;
-- 画面は登録済みの値を一覧して見せるので、読むのは全表。書くのは関数だけ。
GRANT SELECT ON ALL TABLES IN SCHEMA pokemondb TO pkdb_entry;
GRANT EXECUTE ON FUNCTION pokemondb.register_title(text, text, text, integer, text) TO pkdb_entry, pkdb_editor;
GRANT EXECUTE ON FUNCTION pokemondb.update_title(text, text, text, integer, text) TO pkdb_entry, pkdb_editor;
GRANT EXECUTE ON FUNCTION pokemondb.save_title_solo(text, text, text, text, integer, integer, integer) TO pkdb_entry, pkdb_editor;
GRANT EXECUTE ON FUNCTION pokemondb.register_pokemon(
  text, text, text, text, text, text, text, text, text,
  integer, integer, integer, integer, integer, integer,
  text, text, text, text, text, text, text, text[]) TO pkdb_entry, pkdb_editor;
GRANT EXECUTE ON FUNCTION pokemondb.update_pokemon(
  text, text, text, text, text, text,
  integer, integer, integer, integer, integer, integer,
  text, text, text) TO pkdb_entry, pkdb_editor;
GRANT EXECUTE ON FUNCTION pokemondb.update_pokemon_names(
  text, text, text, text, text, text, text, text, text, text, text, text, text, text, text, text, text[]) TO pkdb_entry, pkdb_editor;
GRANT EXECUTE ON FUNCTION pokemondb.copy_pokemon_status(
  text, text, text, text, text[], text, boolean) TO pkdb_entry, pkdb_editor;
GRANT SELECT ON pokemondb.entry_log TO pkdb_reader, pkdb_editor;
