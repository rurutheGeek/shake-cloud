-- 対戦の使用率順位（battle_ratematch）の取り込みAPI。
--
-- 1シーズンぶんの「順位・図鑑番号・フォーム」をまとめて貼り付けて、その
-- 作品・シーズン・形式の行を入れ替える（部分的に足すのではなく置き換える）。
-- 行数が多いので、entry_log には件数だけを残す。
--
-- 何度流してもよい。entry.sql のあとに流す。

CREATE OR REPLACE FUNCTION pokemondb.import_rankings(
  p_actor text,
  p_title_group_id text,
  p_battle_season integer,
  p_battle_type text,
  p_rows jsonb
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pokemondb, pg_temp AS $fn$
DECLARE
  v_type text := btrim(coalesce(p_battle_type, ''));
  v_before integer;
  v_count integer := 0;
  v_ranks integer[] := ARRAY[]::integer[];
  v_forms text[] := ARRAY[]::text[];
  v_row jsonb;
  v_rank integer;
  v_ndex text;
  v_form text;
BEGIN
  PERFORM entry_check_title(p_title_group_id);
  IF p_battle_season IS NULL OR NOT (p_battle_season BETWEEN 1 AND 999) THEN
    RAISE EXCEPTION 'シーズンは1〜999です' USING ERRCODE = '22023';
  END IF;
  IF v_type = '' THEN
    RAISE EXCEPTION '形式（シングル・ダブルなど）を入れてください' USING ERRCODE = '22023';
  END IF;

  SELECT count(*) INTO v_before FROM battle_ratematch
  WHERE title_group_id = p_title_group_id AND battle_season = p_battle_season
    AND battle_type = v_type;
  -- 渡された一覧で丸ごと置き換える。途中で失敗したら関数ごと巻き戻る。
  DELETE FROM battle_ratematch
  WHERE title_group_id = p_title_group_id AND battle_season = p_battle_season
    AND battle_type = v_type;

  FOR v_row IN SELECT value FROM jsonb_array_elements(coalesce(p_rows, '[]'::jsonb)) LOOP
    v_rank := nullif(btrim(coalesce(v_row ->> 'rank', '')), '')::integer;
    IF v_rank IS NULL OR NOT (v_rank BETWEEN 1 AND 99999) THEN
      RAISE EXCEPTION '順位は1〜99999です: %', v_row ->> 'rank' USING ERRCODE = '22023';
    END IF;
    IF v_rank = ANY (v_ranks) THEN
      RAISE EXCEPTION '順位 % が重複しています', v_rank USING ERRCODE = '23505';
    END IF;
    v_ranks := v_ranks || v_rank;
    v_ndex := lpad(btrim(coalesce(v_row ->> 'ndex', '')), 4, '0');
    v_form := lpad(btrim(coalesce(nullif(btrim(coalesce(v_row ->> 'form', '')), ''), '00')), 2, '0');
    IF NOT EXISTS (SELECT FROM pokemon_name_form
                   WHERE ndex_number = v_ndex AND form_id = v_form) THEN
      RAISE EXCEPTION '順位 % の %（フォーム %）が見つかりません', v_rank, v_ndex, v_form
        USING ERRCODE = '22023';
    END IF;
    IF (v_ndex || v_form) = ANY (v_forms) THEN
      RAISE EXCEPTION '%（フォーム %）が一覧に2回出てきます', v_ndex, v_form USING ERRCODE = '23505';
    END IF;
    v_forms := v_forms || (v_ndex || v_form);
    INSERT INTO battle_ratematch
      (title_group_id, battle_season, battle_type, ndex_number, form_id, battle_ranking)
    VALUES (p_title_group_id, p_battle_season, v_type, v_ndex, v_form, v_rank);
    v_count := v_count + 1;
  END LOOP;

  INSERT INTO entry_log (actor, action, detail)
  VALUES (p_actor, 'import_rankings', jsonb_build_object(
    'entity', 'rankings', 'title_group_id', p_title_group_id,
    'battle_season', p_battle_season, 'battle_type', v_type,
    'before_rows', v_before, 'after_rows', v_count));

  RETURN format('作品 %s シーズン %s（%s）の順位 %s 件を取り込みました（前の %s 件は置き換え）',
    p_title_group_id, p_battle_season, v_type, v_count, v_before);
END
$fn$;

REVOKE ALL ON FUNCTION pokemondb.import_rankings(text, text, integer, text, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pokemondb.import_rankings(text, text, integer, text, jsonb) TO pkdb_entry, pkdb_editor;
