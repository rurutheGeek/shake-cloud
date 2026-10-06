-- 覚えるわざ（pokemon_move_learn）の登録API。
--
-- 画面は1匹・1姿・1作品ぶんの一覧をまとめて送る。わざ名は move_data に無ければ
-- entry_move_id が直近の作品から写して自動で足す（覚えわざを入れる前に、わざを
-- 作らなくてよい）。削除もここで行う（IDを指定したものだけ）。
--
-- 何度流してもよい。entry.sql のあとに流す。

-- 1匹の覚えわざの一覧を JSON で返す（before/after の記録用）。
CREATE OR REPLACE FUNCTION pokemondb.entry_learn_snapshot(
  p_ndex text, p_form text, p_title text
) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
  SELECT coalesce(jsonb_agg(jsonb_build_object(
           'learn_id', l.learn_id,
           'move_id', l.move_id,
           'move_name', coalesce(m.name, (SELECT name FROM move_data WHERE move_id = l.move_id
                                          ORDER BY title_group_id DESC LIMIT 1)),
           'method_id', l.method_id,
           'method_name', ml.method_name,
           'level', l.level_learned_at,
           'learn_order', l.learn_order,
           'source', l.source_version_group_name,
           'notes', l.notes)
         ORDER BY l.method_id, l.learn_order, l.level_learned_at, l.move_id), '[]'::jsonb)
  FROM pokemon_move_learn l
  JOIN move_learn_method ml ON ml.method_id = l.method_id
  LEFT JOIN move_data m ON m.move_id = l.move_id AND m.title_group_id = l.title_group_id
  WHERE l.ndex_number = p_ndex AND l.form_id = p_form AND l.title_group_id = p_title
$fn$;

-- 覚えわざをまとめて保存する。p_rows の各行は
-- {learn_id, move_name, method_name, level, learn_order, source, notes}。
-- learn_id があればその行を直し、無ければ（ポケモン・姿・作品・わざ・覚え方）で足す。
-- p_delete_ids の行は消す。画面の表をそのまま送る想定。
CREATE OR REPLACE FUNCTION pokemondb.save_learnset(
  p_actor text, p_ndex_number text, p_form_id text, p_title_group_id text,
  p_rows jsonb, p_delete_ids bigint[]
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_ndex text := lpad(btrim(coalesce(p_ndex_number, '')), 4, '0');
  v_form text := lpad(btrim(coalesce(nullif(btrim(p_form_id), ''), '00')), 2, '0');
  v_name text;
  v_row jsonb;
  v_move_name text;
  v_method_name text;
  v_move_id integer;
  v_method_id bigint;
  v_learn_id bigint;
  v_level integer;
  v_order integer;
  v_source text;
  v_notes text;
  v_added integer := 0;
  v_updated integer := 0;
  v_deleted integer := 0;
  v_before jsonb;
  v_after jsonb;
BEGIN
  SELECT n.name INTO v_name FROM pokemon_name n WHERE n.ndex_number = v_ndex;
  IF v_name IS NULL THEN
    RAISE EXCEPTION '図鑑番号 % の登録がありません', v_ndex USING ERRCODE = '22023';
  END IF;
  IF NOT EXISTS (SELECT FROM pokemon_name_form WHERE ndex_number = v_ndex AND form_id = v_form) THEN
    RAISE EXCEPTION '図鑑番号 %・フォーム % の登録がありません', v_ndex, v_form USING ERRCODE = '22023';
  END IF;
  PERFORM entry_check_title(p_title_group_id);

  v_before := entry_learn_snapshot(v_ndex, v_form, p_title_group_id);

  IF p_delete_ids IS NOT NULL AND array_length(p_delete_ids, 1) IS NOT NULL THEN
    DELETE FROM pokemon_move_learn
    WHERE learn_id = ANY (p_delete_ids)
      AND ndex_number = v_ndex AND form_id = v_form AND title_group_id = p_title_group_id;
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
  END IF;

  FOR v_row IN SELECT value FROM jsonb_array_elements(coalesce(p_rows, '[]'::jsonb)) LOOP
    v_move_name := btrim(coalesce(v_row ->> 'move_name', ''));
    CONTINUE WHEN v_move_name = '';
    v_method_name := btrim(coalesce(v_row ->> 'method_name', ''));
    IF v_method_name = '' THEN
      RAISE EXCEPTION 'わざ % の覚え方を選んでください', v_move_name USING ERRCODE = '22023';
    END IF;
    v_move_id := entry_move_id(v_move_name, p_title_group_id);
    v_method_id := entry_method_id(v_method_name);
    v_learn_id := nullif(btrim(coalesce(v_row ->> 'learn_id', '')), '')::bigint;
    v_level := nullif(btrim(coalesce(v_row ->> 'level', '')), '')::integer;
    v_order := nullif(btrim(coalesce(v_row ->> 'learn_order', '')), '')::integer;
    v_source := nullif(btrim(coalesce(v_row ->> 'source', '')), '');
    v_notes := nullif(btrim(coalesce(v_row ->> 'notes', '')), '');
    IF v_level IS NOT NULL AND NOT (v_level BETWEEN 0 AND 100) THEN
      RAISE EXCEPTION 'レベルは0〜100です: %', v_level USING ERRCODE = '22023';
    END IF;

    IF v_learn_id IS NOT NULL THEN
      UPDATE pokemon_move_learn
      SET move_id = v_move_id, method_id = v_method_id, level_learned_at = v_level,
          learn_order = v_order, source_version_group_name = v_source, notes = v_notes,
          updated_at = now()
      WHERE learn_id = v_learn_id AND ndex_number = v_ndex AND form_id = v_form
        AND title_group_id = p_title_group_id;
      IF NOT FOUND THEN
        RAISE EXCEPTION '覚えわざの行（% % % / %）が見つかりません',
          v_ndex, v_form, p_title_group_id, v_learn_id USING ERRCODE = '22023';
      END IF;
      v_updated := v_updated + 1;
    ELSE
      INSERT INTO pokemon_move_learn
        (ndex_number, form_id, title_group_id, move_id, method_id,
         level_learned_at, learn_order, source_version_group_name, notes)
      VALUES (v_ndex, v_form, p_title_group_id, v_move_id, v_method_id,
              v_level, v_order, v_source, v_notes)
      ON CONFLICT (ndex_number, form_id, title_group_id, move_id, method_id) DO UPDATE
        SET level_learned_at = excluded.level_learned_at, learn_order = excluded.learn_order,
            source_version_group_name = excluded.source_version_group_name, notes = excluded.notes,
            updated_at = now();
      v_added := v_added + 1;
    END IF;
  END LOOP;

  v_after := entry_learn_snapshot(v_ndex, v_form, p_title_group_id);

  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'save_learnset', jsonb_build_object(
    'entity', 'learnset', 'ndex_number', v_ndex, 'form_id', v_form,
    'title_group_id', p_title_group_id, 'name', v_name,
    'added', v_added, 'updated', v_updated, 'deleted', v_deleted,
    'before', v_before, 'after', v_after));

  RETURN format('%s（フォーム %s・作品 %s）の覚えわざを保存しました（追加 %s・修正 %s・削除 %s）',
    v_name, v_form, p_title_group_id, v_added, v_updated, v_deleted);
END
$fn$;

-- ある作品の覚えわざを、同じポケモンの別の作品へまとめて写す。
CREATE OR REPLACE FUNCTION pokemondb.copy_learnset(
  p_actor text, p_ndex_number text, p_form_id text,
  p_from_title text, p_to_title text, p_overwrite boolean
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_ndex text := lpad(btrim(coalesce(p_ndex_number, '')), 4, '0');
  v_form text := lpad(btrim(coalesce(nullif(btrim(p_form_id), ''), '00')), 2, '0');
  v_name text;
  v_count integer;
BEGIN
  SELECT n.name INTO v_name FROM pokemon_name n WHERE n.ndex_number = v_ndex;
  IF v_name IS NULL THEN
    RAISE EXCEPTION '図鑑番号 % の登録がありません', v_ndex USING ERRCODE = '22023';
  END IF;
  PERFORM entry_check_title(p_from_title);
  PERFORM entry_check_title(p_to_title);
  IF p_from_title = p_to_title THEN
    RAISE EXCEPTION '写し元と写し先が同じです' USING ERRCODE = '22023';
  END IF;
  INSERT INTO pokemon_move_learn
    (ndex_number, form_id, title_group_id, move_id, method_id,
     level_learned_at, learn_order, source_version_group_name, notes)
  SELECT ndex_number, form_id, p_to_title, move_id, method_id,
         level_learned_at, learn_order, source_version_group_name, notes
  FROM pokemon_move_learn
  WHERE ndex_number = v_ndex AND form_id = v_form AND title_group_id = p_from_title
  ON CONFLICT (ndex_number, form_id, title_group_id, move_id, method_id) DO UPDATE
    SET level_learned_at = excluded.level_learned_at, learn_order = excluded.learn_order,
        source_version_group_name = excluded.source_version_group_name, notes = excluded.notes,
        updated_at = now()
  WHERE p_overwrite;
  GET DIAGNOSTICS v_count = ROW_COUNT;
  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'copy_learnset', jsonb_build_object(
    'entity', 'learnset', 'ndex_number', v_ndex, 'form_id', v_form,
    'from_title', p_from_title, 'to_title', p_to_title,
    'overwrite', p_overwrite, 'rows', v_count));
  RETURN format('%s（フォーム %s）の覚えわざ %s 件を作品 %s から %s へ写しました',
    v_name, v_form, v_count, p_from_title, p_to_title);
END
$fn$;

REVOKE ALL ON FUNCTION pokemondb.entry_learn_snapshot(text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.save_learnset(text, text, text, text, jsonb, bigint[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION pokemondb.copy_learnset(text, text, text, text, text, boolean) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION pokemondb.save_learnset(text, text, text, text, jsonb, bigint[]) TO pkdb_entry, pkdb_editor;
GRANT EXECUTE ON FUNCTION pokemondb.copy_learnset(text, text, text, text, text, boolean) TO pkdb_entry, pkdb_editor;
