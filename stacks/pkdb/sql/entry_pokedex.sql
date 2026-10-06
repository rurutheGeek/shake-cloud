-- 図鑑情報（pokemon_pokedex）と地方図鑑番号（pokemon_rdexnumber）の登録API。
--
-- 図鑑情報は1つの姿について1行（作品列はどの作品の情報かの目印）。地方図鑑番号は
-- 1つの姿について1行で、地方ごとの列に3桁の番号を持つ。どちらもIDや行の有無は
-- 画面が気にしなくてよい（無ければ作る）。
--
-- 何度流してもよい。entry.sql のあとに流す。

-- 図鑑情報を保存する（無ければ作り、あれば直す）。数値は範囲を確かめ、タマゴグループは
-- egg_group にある名前だけを受け付ける。
CREATE OR REPLACE FUNCTION pokemondb.save_pokedex(
  p_actor text,
  p_ndex_number text,
  p_form_id text,
  p_title_group_id text,
  p_category text,
  p_height text,
  p_weight text,
  p_gender_ratio integer,
  p_egg_group_1 text,
  p_egg_group_2 text,
  p_leveling_rate integer,
  p_carch_rate integer,
  p_ev_h integer, p_ev_a integer, p_ev_b integer, p_ev_c integer, p_ev_d integer, p_ev_s integer
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_ndex text := lpad(btrim(coalesce(p_ndex_number, '')), 4, '0');
  v_form text := lpad(btrim(coalesce(nullif(btrim(p_form_id), ''), '00')), 2, '0');
  v_title text := coalesce(nullif(btrim(coalesce(p_title_group_id, '')), ''), '000');
  v_egg1 text := nullif(btrim(coalesce(p_egg_group_1, '')), '');
  v_egg2 text := nullif(btrim(coalesce(p_egg_group_2, '')), '');
  v_name text;
  v_before jsonb;
  v_created boolean := false;
BEGIN
  SELECT n.name INTO v_name FROM pokemon_name n WHERE n.ndex_number = v_ndex;
  IF v_name IS NULL THEN
    RAISE EXCEPTION '図鑑番号 % の登録がありません', v_ndex USING ERRCODE = '22023';
  END IF;
  IF NOT EXISTS (SELECT FROM pokemon_name_form WHERE ndex_number = v_ndex AND form_id = v_form) THEN
    RAISE EXCEPTION '図鑑番号 %・フォーム % の登録がありません', v_ndex, v_form USING ERRCODE = '22023';
  END IF;
  PERFORM entry_check_title(v_title);
  IF length(coalesce(p_height, '')) > 5 OR length(coalesce(p_weight, '')) > 5 THEN
    RAISE EXCEPTION 'たかさ・おもさは5文字までです' USING ERRCODE = '22023';
  END IF;
  IF p_gender_ratio IS NOT NULL AND NOT (p_gender_ratio BETWEEN 0 AND 255) THEN
    RAISE EXCEPTION '性別比は0〜255です' USING ERRCODE = '22023';
  END IF;
  IF p_carch_rate IS NOT NULL AND NOT (p_carch_rate BETWEEN 0 AND 255) THEN
    RAISE EXCEPTION '被捕獲度は0〜255です' USING ERRCODE = '22023';
  END IF;
  IF p_leveling_rate IS NOT NULL AND NOT (p_leveling_rate BETWEEN 0 AND 99) THEN
    RAISE EXCEPTION '経験値タイプは0〜99です' USING ERRCODE = '22023';
  END IF;
  IF v_egg1 IS NOT NULL AND NOT EXISTS (SELECT FROM egg_group WHERE egg_group_name = v_egg1) THEN
    RAISE EXCEPTION 'タマゴグループ「%」がありません', v_egg1 USING ERRCODE = '22023';
  END IF;
  IF v_egg2 IS NOT NULL AND NOT EXISTS (SELECT FROM egg_group WHERE egg_group_name = v_egg2) THEN
    RAISE EXCEPTION 'タマゴグループ「%」がありません', v_egg2 USING ERRCODE = '22023';
  END IF;

  SELECT to_jsonb(p) INTO v_before FROM pokemon_pokedex p
  WHERE p.ndex_number = v_ndex AND p.form_id = v_form;
  v_created := v_before IS NULL;

  INSERT INTO pokemon_pokedex
    (ndex_number, form_id, title_group_id, category, height, weight, gender_ratio,
     egg_group_1, egg_group_2, leveling_rate, carch_rate,
     evyield_h, evyield_a, evyield_b, evyield_c, evyield_d, evyield_s)
  VALUES (v_ndex, v_form, v_title, nullif(btrim(coalesce(p_category, '')), ''),
          nullif(btrim(coalesce(p_height, '')), ''), nullif(btrim(coalesce(p_weight, '')), ''),
          p_gender_ratio, v_egg1, v_egg2, p_leveling_rate, p_carch_rate,
          coalesce(p_ev_h, 0), coalesce(p_ev_a, 0), coalesce(p_ev_b, 0),
          coalesce(p_ev_c, 0), coalesce(p_ev_d, 0), coalesce(p_ev_s, 0))
  ON CONFLICT (ndex_number, form_id) DO UPDATE
    SET title_group_id = excluded.title_group_id, category = excluded.category,
        height = excluded.height, weight = excluded.weight,
        gender_ratio = excluded.gender_ratio, egg_group_1 = excluded.egg_group_1,
        egg_group_2 = excluded.egg_group_2, leveling_rate = excluded.leveling_rate,
        carch_rate = excluded.carch_rate, evyield_h = excluded.evyield_h,
        evyield_a = excluded.evyield_a, evyield_b = excluded.evyield_b,
        evyield_c = excluded.evyield_c, evyield_d = excluded.evyield_d,
        evyield_s = excluded.evyield_s;

  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'save_pokedex', jsonb_build_object(
    'entity', 'pokedex', 'ndex_number', v_ndex, 'form_id', v_form,
    'before', v_before,
    'after', (SELECT to_jsonb(p) FROM pokemon_pokedex p
              WHERE p.ndex_number = v_ndex AND p.form_id = v_form)));

  RETURN format('%s（フォーム %s）の図鑑情報を%sしました', v_name, v_form,
    CASE WHEN v_created THEN '追加' ELSE '修正' END);
END
$fn$;

-- 地方図鑑番号を保存する。p_values は {"kanto": "001", ...} のような形で、
-- 渡された列だけを直す（列名は決められたものだけ）。
CREATE OR REPLACE FUNCTION pokemondb.update_rdex(
  p_actor text, p_ndex_number text, p_form_id text, p_values jsonb
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_ndex text := lpad(btrim(coalesce(p_ndex_number, '')), 4, '0');
  v_form text := lpad(btrim(coalesce(nullif(btrim(p_form_id), ''), '00')), 2, '0');
  v_stored_form text := CASE WHEN v_form = '00' THEN NULL ELSE v_form END;
  v_columns text[] := ARRAY[
    'kanto', 'new', 'hoenn', 'sinnoh', 'enhanced_sinnoh', 'johto', 'unova', 'unova_b2w2',
    'central_kalos', 'coastal_kalos', 'mountain_kalos', 'hoenn_oras', 'alola', 'melemele',
    'akala', 'ulaula', 'poni', 'alola_usum', 'melemele_usum', 'akala_usum', 'ulaula_usum',
    'poni_usum', 'kanto_pe', 'galar', 'isle_of_armor', 'crown_tundra', 'hisui', 'paldea',
    'kitakami', 'blueberry', 'kalos', 'hyperspace', 'champions'];
  v_name text;
  v_key text;
  v_value text;
  v_before jsonb;
  v_changed integer := 0;
BEGIN
  SELECT n.name INTO v_name FROM pokemon_name n WHERE n.ndex_number = v_ndex;
  IF v_name IS NULL THEN
    RAISE EXCEPTION '図鑑番号 % の登録がありません', v_ndex USING ERRCODE = '22023';
  END IF;
  IF NOT EXISTS (SELECT FROM pokemon_name_form WHERE ndex_number = v_ndex AND form_id = v_form) THEN
    RAISE EXCEPTION '図鑑番号 %・フォーム % の登録がありません', v_ndex, v_form USING ERRCODE = '22023';
  END IF;

  SELECT to_jsonb(r) - 'ndex_number' - 'form_id' INTO v_before
  FROM pokemon_rdexnumber r
  WHERE r.ndex_number = v_ndex AND coalesce(r.form_id, '') = coalesce(v_stored_form, '');
  IF v_before IS NULL THEN
    v_before := 'null'::jsonb;
  END IF;

  IF EXISTS (SELECT FROM jsonb_object_keys(coalesce(p_values, '{}'::jsonb)) AS k(key)
             WHERE key <> ALL (v_columns)) THEN
    RAISE EXCEPTION '知らない地方図鑑の列があります: %',
      (SELECT string_agg(key, ', ') FROM jsonb_object_keys(coalesce(p_values, '{}'::jsonb)) AS k(key)
       WHERE key <> ALL (v_columns)) USING ERRCODE = '22023';
  END IF;

  -- 行が無ければ作る（番号は後で入る）。
  INSERT INTO pokemon_rdexnumber (ndex_number, form_id)
  SELECT v_ndex, v_stored_form
  WHERE NOT EXISTS (SELECT FROM pokemon_rdexnumber
                    WHERE ndex_number = v_ndex AND coalesce(form_id, '') = coalesce(v_stored_form, ''));

  FOR v_key, v_value IN SELECT key, value FROM jsonb_each_text(coalesce(p_values, '{}'::jsonb)) LOOP
    IF v_value IS NULL OR btrim(v_value) = '' THEN
      EXECUTE format('UPDATE pokemon_rdexnumber SET %I = NULL
                      WHERE ndex_number = $1 AND coalesce(form_id, '''') = coalesce($2, '''')', v_key)
      USING v_ndex, v_stored_form;
    ELSE
      IF btrim(v_value) !~ '^[0-9]{1,3}$' THEN
        RAISE EXCEPTION '地方図鑑番号は3桁までの数字です（%: %）', v_key, v_value USING ERRCODE = '22023';
      END IF;
      EXECUTE format('UPDATE pokemon_rdexnumber SET %I = lpad(btrim($3), 3, ''0'')
                      WHERE ndex_number = $1 AND coalesce(form_id, '''') = coalesce($2, '''')', v_key)
      USING v_ndex, v_stored_form, btrim(v_value);
    END IF;
    v_changed := v_changed + 1;
  END LOOP;

  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'update_rdex', jsonb_build_object(
    'entity', 'rdex', 'ndex_number', v_ndex, 'form_id', v_form,
    'before', v_before,
    'after', (SELECT to_jsonb(r) - 'ndex_number' - 'form_id' FROM pokemon_rdexnumber r
              WHERE r.ndex_number = v_ndex AND coalesce(r.form_id, '') = coalesce(v_stored_form, ''))));

  RETURN format('%s（フォーム %s）の地方図鑑番号を%s件保存しました', v_name, v_form, v_changed);
END
$fn$;

REVOKE ALL ON FUNCTION pokemondb.save_pokedex(
  text, text, text, text, text, text, text, integer, text, text, integer, integer,
  integer, integer, integer, integer, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.update_rdex(text, text, text, jsonb) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION pokemondb.save_pokedex(
  text, text, text, text, text, text, text, integer, text, text, integer, integer,
  integer, integer, integer, integer, integer, integer) TO pkdb_entry, pkdb_editor;
GRANT EXECUTE ON FUNCTION pokemondb.update_rdex(text, text, text, jsonb) TO pkdb_entry, pkdb_editor;
