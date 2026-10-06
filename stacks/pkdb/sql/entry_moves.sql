-- わざ（move_data）と特性（ability_data）の登録API。作品ごとに行があるので、
-- 画面は「作品」を選んでから足す・直す。IDは名前から裏で解決する。
--
-- 何度流してもよい。entry.sql のあとに流す。

-- 作品の指定を確かめる（わざ・特性で共通）。
CREATE OR REPLACE FUNCTION pokemondb.entry_check_title(p_title text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
BEGIN
  IF NOT EXISTS (SELECT FROM title_group WHERE title_group_id = p_title) THEN
    RAISE EXCEPTION '作品 % がありません', p_title USING ERRCODE = '22023';
  END IF;
END
$fn$;

-- わざの項目を確かめる（タイプ名・分類・数値の範囲）。
CREATE OR REPLACE FUNCTION pokemondb.entry_check_move(
  p_type text, p_category text, p_power integer, p_accuracy integer, p_pp integer,
  p_priority integer, p_effect_chance integer
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
BEGIN
  PERFORM entry_type_id(p_type);
  IF p_category NOT IN ('物理', '特殊', '変化') THEN
    RAISE EXCEPTION '分類は 物理・特殊・変化 のどれかです: %', p_category USING ERRCODE = '22023';
  END IF;
  IF p_power IS NOT NULL AND NOT (p_power BETWEEN 0 AND 999) THEN
    RAISE EXCEPTION '威力は0〜999です' USING ERRCODE = '22023';
  END IF;
  IF p_accuracy IS NOT NULL AND NOT (p_accuracy BETWEEN 0 AND 999) THEN
    RAISE EXCEPTION '命中率は0〜999です' USING ERRCODE = '22023';
  END IF;
  IF p_pp IS NOT NULL AND NOT (p_pp BETWEEN 0 AND 999) THEN
    RAISE EXCEPTION 'PPは0〜999です' USING ERRCODE = '22023';
  END IF;
  IF p_priority IS NOT NULL AND NOT (p_priority BETWEEN -10 AND 10) THEN
    RAISE EXCEPTION '優先度は-10〜10です' USING ERRCODE = '22023';
  END IF;
  IF p_effect_chance IS NOT NULL AND NOT (p_effect_chance BETWEEN 0 AND 100) THEN
    RAISE EXCEPTION '追加効果の確率は0〜100です' USING ERRCODE = '22023';
  END IF;
END
$fn$;

-- わざを足す。move_id が空なら、名前から探して（無ければ新しく採番して）決める。
-- 同じ作品に同じ名前があれば error。既に別の作品にある名前なら、直近の内容を写してから
-- 渡された値で上書きする。
CREATE OR REPLACE FUNCTION pokemondb.register_move(
  p_actor text, p_move_id text, p_name text, p_title_group_id text,
  p_english_name text, p_type text, p_category text,
  p_power integer, p_accuracy integer, p_pp integer, p_priority integer,
  p_target text, p_effect_chance integer, p_description text, p_notes text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_name text := btrim(coalesce(p_name, ''));
  v_id integer;
  v_existing integer;
BEGIN
  PERFORM entry_check_title(p_title_group_id);
  IF v_name = '' THEN
    RAISE EXCEPTION 'わざ名を入れてください' USING ERRCODE = '22023';
  END IF;
  PERFORM entry_check_move(p_type, p_category, p_power, p_accuracy, p_pp, p_priority, p_effect_chance);

  SELECT move_id INTO v_existing FROM move_data
  WHERE name = v_name AND title_group_id = p_title_group_id;
  IF v_existing IS NOT NULL THEN
    RAISE EXCEPTION 'わざ % は作品 % にすでにあります（ID %）', v_name, p_title_group_id, v_existing
      USING ERRCODE = '23505';
  END IF;

  IF btrim(coalesce(p_move_id, '')) <> '' THEN
    v_id := btrim(p_move_id)::integer;
    IF NOT EXISTS (SELECT FROM move_data WHERE move_id = v_id) THEN
      RAISE EXCEPTION 'わざID % はまだありません', v_id USING ERRCODE = '22023';
    END IF;
    INSERT INTO move_data (move_id, name, english_name, type, category, power, accuracy,
                           pp, priority, target, effect_chance, description, title_group_id, notes)
    SELECT move_id, name, english_name, type, category, power, accuracy,
           pp, priority, target, effect_chance, description, p_title_group_id, notes
    FROM move_data WHERE move_id = v_id ORDER BY title_group_id DESC LIMIT 1;
  ELSE
    v_id := entry_move_id(v_name, p_title_group_id);
  END IF;

  UPDATE move_data
  SET english_name = nullif(btrim(coalesce(p_english_name, '')), ''),
      type = btrim(p_type),
      category = p_category,
      power = p_power,
      accuracy = p_accuracy,
      pp = p_pp,
      priority = p_priority,
      target = nullif(btrim(coalesce(p_target, '')), ''),
      effect_chance = p_effect_chance,
      description = nullif(btrim(coalesce(p_description, '')), ''),
      notes = nullif(btrim(coalesce(p_notes, '')), '')
  WHERE move_id = v_id AND title_group_id = p_title_group_id;

  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'register_move', jsonb_build_object(
    'entity', 'move', 'before', NULL,
    'after', jsonb_build_object(
      'move_id', v_id, 'name', v_name, 'title_group_id', p_title_group_id,
      'english_name', nullif(btrim(coalesce(p_english_name, '')), ''),
      'type', btrim(p_type), 'category', p_category, 'power', p_power, 'accuracy', p_accuracy,
      'pp', p_pp, 'priority', p_priority, 'target', nullif(btrim(coalesce(p_target, '')), ''),
      'effect_chance', p_effect_chance,
      'description', nullif(btrim(coalesce(p_description, '')), ''))));

  PERFORM refresh_move_views();
  RETURN format('わざ %s（ID %s）を作品 %s に追加しました', v_name, v_id, p_title_group_id);
END
$fn$;

-- わざの1作品ぶんの行を直す。名前も直せる（同じ作品の別IDと重複したら error）。
CREATE OR REPLACE FUNCTION pokemondb.update_move(
  p_actor text, p_move_id text, p_title_group_id text,
  p_name text, p_english_name text, p_type text, p_category text,
  p_power integer, p_accuracy integer, p_pp integer, p_priority integer,
  p_target text, p_effect_chance integer, p_description text, p_notes text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_name text := btrim(coalesce(p_name, ''));
  v_before jsonb;
  v_after jsonb;
BEGIN
  PERFORM entry_check_title(p_title_group_id);
  IF v_name = '' THEN
    RAISE EXCEPTION 'わざ名を入れてください' USING ERRCODE = '22023';
  END IF;
  PERFORM entry_check_move(p_type, p_category, p_power, p_accuracy, p_pp, p_priority, p_effect_chance);

  SELECT to_jsonb(m) - 'title_group_id' INTO v_before
  FROM move_data m WHERE move_id = p_move_id::integer AND title_group_id = p_title_group_id;
  IF v_before IS NULL THEN
    RAISE EXCEPTION 'わざID %・作品 % の行がありません', p_move_id, p_title_group_id
      USING ERRCODE = '22023';
  END IF;
  IF EXISTS (SELECT FROM move_data
             WHERE name = v_name AND title_group_id = p_title_group_id
               AND move_id <> p_move_id::integer) THEN
    RAISE EXCEPTION 'わざ % は作品 % の別IDにすでにあります', v_name, p_title_group_id
      USING ERRCODE = '23505';
  END IF;

  UPDATE move_data
  SET name = v_name,
      english_name = nullif(btrim(coalesce(p_english_name, '')), ''),
      type = btrim(p_type),
      category = p_category,
      power = p_power,
      accuracy = p_accuracy,
      pp = p_pp,
      priority = p_priority,
      target = nullif(btrim(coalesce(p_target, '')), ''),
      effect_chance = p_effect_chance,
      description = nullif(btrim(coalesce(p_description, '')), ''),
      notes = nullif(btrim(coalesce(p_notes, '')), '')
  WHERE move_id = p_move_id::integer AND title_group_id = p_title_group_id;

  SELECT to_jsonb(m) - 'title_group_id' INTO v_after
  FROM move_data m WHERE move_id = p_move_id::integer AND title_group_id = p_title_group_id;

  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'update_move', jsonb_build_object(
    'entity', 'move', 'move_id', p_move_id::integer, 'title_group_id', p_title_group_id,
    'before', v_before, 'after', v_after));

  PERFORM refresh_move_views();
  RETURN format('わざ %s（ID %s）の作品 %s の値を修正しました', v_name, p_move_id, p_title_group_id);
END
$fn$;

-- わざの1作品ぶんの行を消す。覚えるポケモンがいる作品では消せない（先に覚えわざを外す）。
CREATE OR REPLACE FUNCTION pokemondb.delete_move_title(
  p_actor text, p_move_id text, p_title_group_id text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_before jsonb;
  v_learns integer;
BEGIN
  SELECT to_jsonb(m) - 'title_group_id' INTO v_before
  FROM move_data m WHERE move_id = p_move_id::integer AND title_group_id = p_title_group_id;
  IF v_before IS NULL THEN
    RAISE EXCEPTION 'わざID %・作品 % の行がありません', p_move_id, p_title_group_id
      USING ERRCODE = '22023';
  END IF;
  SELECT count(*) INTO v_learns FROM pokemon_move_learn
  WHERE move_id = p_move_id::integer AND title_group_id = p_title_group_id;
  IF v_learns > 0 THEN
    RAISE EXCEPTION 'このわざを覚えるポケモンが % 件あるので消せません（先に覚えわざを外してください）', v_learns
      USING ERRCODE = '23503';
  END IF;
  DELETE FROM move_data WHERE move_id = p_move_id::integer AND title_group_id = p_title_group_id;
  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'delete_move_title', jsonb_build_object(
    'entity', 'move', 'move_id', p_move_id::integer, 'title_group_id', p_title_group_id,
    'before', v_before, 'after', NULL));
  PERFORM refresh_move_views();
  RETURN format('わざ %s（ID %s）の作品 %s の行を消しました', v_before ->> 'name', p_move_id, p_title_group_id);
END
$fn$;

-- ある作品のわざを、まとめて別の作品へ写す（新作が出たとき用）。
CREATE OR REPLACE FUNCTION pokemondb.inherit_moves(
  p_actor text, p_from_title text, p_to_title text, p_overwrite boolean
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_count integer;
BEGIN
  PERFORM entry_check_title(p_from_title);
  PERFORM entry_check_title(p_to_title);
  IF p_from_title = p_to_title THEN
    RAISE EXCEPTION '写し元と写し先が同じです' USING ERRCODE = '22023';
  END IF;
  INSERT INTO move_data (move_id, name, english_name, type, category, power, accuracy,
                         pp, priority, target, effect_chance, description, title_group_id, notes)
  SELECT move_id, name, english_name, type, category, power, accuracy,
         pp, priority, target, effect_chance, description, p_to_title, notes
  FROM move_data WHERE title_group_id = p_from_title
  ON CONFLICT (move_id, title_group_id) DO UPDATE
    SET name = excluded.name, english_name = excluded.english_name, type = excluded.type,
        category = excluded.category, power = excluded.power, accuracy = excluded.accuracy,
        pp = excluded.pp, priority = excluded.priority, target = excluded.target,
        effect_chance = excluded.effect_chance, description = excluded.description,
        notes = excluded.notes
  WHERE p_overwrite;
  GET DIAGNOSTICS v_count = ROW_COUNT;
  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'inherit_moves', jsonb_build_object(
    'entity', 'move', 'from_title', p_from_title, 'to_title', p_to_title,
    'overwrite', p_overwrite, 'rows', v_count));
  PERFORM refresh_move_views();
  RETURN format('作品 %s のわざ %s 件を作品 %s へ写しました', p_from_title, v_count, p_to_title);
END
$fn$;

-- 特性を足す。ability_id が空なら名前から探し、無ければ新しく採番する。
CREATE OR REPLACE FUNCTION pokemondb.register_ability(
  p_actor text, p_ability_id text, p_name text, p_title_group_id text,
  p_english_name text, p_description text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_name text := btrim(coalesce(p_name, ''));
  v_id integer;
  v_existing integer;
BEGIN
  PERFORM entry_check_title(p_title_group_id);
  IF v_name = '' THEN
    RAISE EXCEPTION '特性名を入れてください' USING ERRCODE = '22023';
  END IF;
  SELECT ability_id INTO v_existing FROM ability_data
  WHERE name = v_name AND title_group_id = p_title_group_id;
  IF v_existing IS NOT NULL THEN
    RAISE EXCEPTION '特性 % は作品 % にすでにあります（ID %）', v_name, p_title_group_id, v_existing
      USING ERRCODE = '23505';
  END IF;

  IF btrim(coalesce(p_ability_id, '')) <> '' THEN
    v_id := btrim(p_ability_id)::integer;
    IF NOT EXISTS (SELECT FROM ability_data WHERE ability_id = v_id) THEN
      RAISE EXCEPTION '特性ID % はまだありません', v_id USING ERRCODE = '22023';
    END IF;
    INSERT INTO ability_data (ability_id, name, english_name, description, title_group_id)
    SELECT ability_id, name, english_name, description, p_title_group_id
    FROM ability_data WHERE ability_id = v_id ORDER BY title_group_id DESC LIMIT 1;
  ELSE
    v_id := entry_ability_id(v_name, p_title_group_id);
  END IF;

  UPDATE ability_data
  SET name = v_name,
      english_name = nullif(btrim(coalesce(p_english_name, '')), ''),
      description = nullif(btrim(coalesce(p_description, '')), '')
  WHERE ability_id = v_id AND title_group_id = p_title_group_id;

  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'register_ability', jsonb_build_object(
    'entity', 'ability', 'before', NULL,
    'after', jsonb_build_object(
      'ability_id', v_id, 'name', v_name, 'title_group_id', p_title_group_id,
      'english_name', nullif(btrim(coalesce(p_english_name, '')), ''),
      'description', nullif(btrim(coalesce(p_description, '')), ''))));

  PERFORM refresh_views();
  RETURN format('特性 %s（ID %s）を作品 %s に追加しました', v_name, v_id, p_title_group_id);
END
$fn$;

-- 特性の1作品ぶんの行（名前・英語名・説明）を直す。
CREATE OR REPLACE FUNCTION pokemondb.update_ability(
  p_actor text, p_ability_id text, p_title_group_id text,
  p_name text, p_english_name text, p_description text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_name text := btrim(coalesce(p_name, ''));
  v_before jsonb;
  v_after jsonb;
BEGIN
  IF v_name = '' THEN
    RAISE EXCEPTION '特性名を入れてください' USING ERRCODE = '22023';
  END IF;
  SELECT to_jsonb(a) - 'title_group_id' INTO v_before
  FROM ability_data a WHERE ability_id = p_ability_id::integer AND title_group_id = p_title_group_id;
  IF v_before IS NULL THEN
    RAISE EXCEPTION '特性ID %・作品 % の行がありません', p_ability_id, p_title_group_id
      USING ERRCODE = '22023';
  END IF;
  IF EXISTS (SELECT FROM ability_data
             WHERE name = v_name AND title_group_id = p_title_group_id
               AND ability_id <> p_ability_id::integer) THEN
    RAISE EXCEPTION '特性 % は作品 % の別IDにすでにあります', v_name, p_title_group_id
      USING ERRCODE = '23505';
  END IF;
  UPDATE ability_data
  SET name = v_name,
      english_name = nullif(btrim(coalesce(p_english_name, '')), ''),
      description = nullif(btrim(coalesce(p_description, '')), '')
  WHERE ability_id = p_ability_id::integer AND title_group_id = p_title_group_id;
  SELECT to_jsonb(a) - 'title_group_id' INTO v_after
  FROM ability_data a WHERE ability_id = p_ability_id::integer AND title_group_id = p_title_group_id;
  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'update_ability', jsonb_build_object(
    'entity', 'ability', 'ability_id', p_ability_id::integer, 'title_group_id', p_title_group_id,
    'before', v_before, 'after', v_after));
  PERFORM refresh_views();
  RETURN format('特性 %s（ID %s）の作品 %s の値を修正しました', v_name, p_ability_id, p_title_group_id);
END
$fn$;

-- ある作品の特性を、まとめて別の作品へ写す（新作が出たとき用）。
CREATE OR REPLACE FUNCTION pokemondb.inherit_abilities(
  p_actor text, p_from_title text, p_to_title text, p_overwrite boolean
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_count integer;
BEGIN
  PERFORM entry_check_title(p_from_title);
  PERFORM entry_check_title(p_to_title);
  IF p_from_title = p_to_title THEN
    RAISE EXCEPTION '写し元と写し先が同じです' USING ERRCODE = '22023';
  END IF;
  INSERT INTO ability_data (ability_id, name, english_name, description, title_group_id)
  SELECT ability_id, name, english_name, description, p_to_title
  FROM ability_data WHERE title_group_id = p_from_title
  ON CONFLICT (ability_id, title_group_id) DO UPDATE
    SET name = excluded.name, english_name = excluded.english_name,
        description = excluded.description
  WHERE p_overwrite;
  GET DIAGNOSTICS v_count = ROW_COUNT;
  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'inherit_abilities', jsonb_build_object(
    'entity', 'ability', 'from_title', p_from_title, 'to_title', p_to_title,
    'overwrite', p_overwrite, 'rows', v_count));
  PERFORM refresh_views();
  RETURN format('作品 %s の特性 %s 件を作品 %s へ写しました', p_from_title, v_count, p_to_title);
END
$fn$;

REVOKE ALL ON FUNCTION pokemondb.entry_check_title(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.entry_check_move(text, text, integer, integer, integer, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.register_move(text, text, text, text, text, text, text,
  integer, integer, integer, integer, text, integer, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.update_move(text, text, text, text, text, text, text,
  integer, integer, integer, integer, text, integer, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.delete_move_title(text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.inherit_moves(text, text, text, boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.register_ability(text, text, text, text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.update_ability(text, text, text, text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.inherit_abilities(text, text, text, boolean) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION pokemondb.register_move(text, text, text, text, text, text, text,
  integer, integer, integer, integer, text, integer, text, text) TO pkdb_entry, pkdb_editor;
GRANT EXECUTE ON FUNCTION pokemondb.update_move(text, text, text, text, text, text, text,
  integer, integer, integer, integer, text, integer, text, text) TO pkdb_entry, pkdb_editor;
GRANT EXECUTE ON FUNCTION pokemondb.delete_move_title(text, text, text) TO pkdb_entry, pkdb_editor;
GRANT EXECUTE ON FUNCTION pokemondb.inherit_moves(text, text, text, boolean) TO pkdb_entry, pkdb_editor;
GRANT EXECUTE ON FUNCTION pokemondb.register_ability(text, text, text, text, text, text) TO pkdb_entry, pkdb_editor;
GRANT EXECUTE ON FUNCTION pokemondb.update_ability(text, text, text, text, text, text) TO pkdb_entry, pkdb_editor;
GRANT EXECUTE ON FUNCTION pokemondb.inherit_abilities(text, text, text, boolean) TO pkdb_entry, pkdb_editor;
