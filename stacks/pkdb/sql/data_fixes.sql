-- pokemondb のデータの直し。見つけた誤り・抜けを、直した内容が残るようここへ足す。
-- どれも「まだ直っていなければ直す」形にして、何度流してもよいようにする。
-- 直したら、依存の順にマテリアライズドビューを作り直す。

DO $$
DECLARE
  affected integer;
  changed integer := 0;
BEGIN
  -- バタフリー: XY（060）でとくこうが 80 → 90 になった行が抜けていた（2026-10-04）。
  -- 特性は種族値と同じ作品の行に付くので、BW（050）の枠をそのまま引き継ぐ。
  INSERT INTO pokemon_status
    (ndex_number, form_id, title_group_id, basestats_h, basestats_a, basestats_b,
     basestats_c, basestats_d, basestats_s, type_1_id, type_2_id)
  SELECT ndex_number, form_id, '060', basestats_h, basestats_a, basestats_b,
         90, basestats_d, basestats_s, type_1_id, type_2_id
  FROM pokemon_status
  WHERE ndex_number = '0012' AND form_id = '00' AND title_group_id = '050'
  ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS affected = ROW_COUNT;
  changed := changed + affected;

  INSERT INTO pokemon_ability (ndex_number, form_id, title_group_id, slot, ability_id)
  SELECT a.ndex_number, a.form_id, '060', a.slot, a.ability_id
  FROM pokemon_ability a
  WHERE a.ndex_number = '0012' AND a.form_id = '00' AND a.title_group_id = '050'
    AND EXISTS (SELECT 1 FROM pokemon_status s
                WHERE s.ndex_number = '0012' AND s.form_id = '00' AND s.title_group_id = '060')
  ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS affected = ROW_COUNT;
  changed := changed + affected;

  -- アルセウス: 18フォームの姿の名前がすべて「アルセウスのすがた」だった（2026-10-04）。
  -- フォームごとのタイプから「ほのおタイプ」の形にする。
  UPDATE pokemon_name_form f
  SET form_name = latest.type_name || 'タイプ'
  FROM (
    SELECT DISTINCT ON (s.form_id) s.form_id, t.name AS type_name
    FROM pokemon_status s
    JOIN type_data t ON t.type_id = s.type_1_id
    WHERE s.ndex_number = '0493'
    ORDER BY s.form_id, s.title_group_id DESC
  ) latest
  WHERE f.ndex_number = '0493' AND f.form_id = latest.form_id
    AND f.form_name IS DISTINCT FROM latest.type_name || 'タイプ';
  GET DIAGNOSTICS affected = ROW_COUNT;
  changed := changed + affected;

  -- 進化の表（pokemon_evolution）のフォームの誤り・抜け（2026-10-10）。
  -- 進化段階はフォームごとに、この表の行の有無で決まる（mv_quiz_status）。進化する
  -- フォームが「無進化」になり、UBSLEEPY の種族値クイズ（既定は最終進化・無進化だけ）に
  -- 出ていた。
  -- とくべつなイワンコ（0744-01）: たそがれのすがた（0745-02）へ進化するのはこのフォーム
  -- だけ。ふつうのイワンコ（00）からの行になっていた。
  UPDATE pokemon_evolution SET before_form_id = '01'
  WHERE before_ndex_number = '0744' AND before_form_id = '00'
    AND after_ndex_number = '0745' AND after_form_id = '02';
  GET DIAGNOSTICS affected = ROW_COUNT;
  changed := changed + affected;

  -- ウパー（パルデアのすがた）は 0194-02。ドオー（0980）への行が 01 からになっていた。
  UPDATE pokemon_evolution SET before_form_id = '02'
  WHERE before_ndex_number = '0194' AND before_form_id = '01'
    AND after_ndex_number = '0980' AND after_form_id = '00';
  GET DIAGNOSTICS affected = ROW_COUNT;
  changed := changed + affected;

  -- ヌメイル（ヒスイのすがた、0705-01）: ヌメラからの行が無く、「進化前」になっていた。
  INSERT INTO pokemon_evolution
    (method_id, before_ndex_number, before_form_id, after_ndex_number, after_form_id,
     title_group_id)
  VALUES ('level-up-level-40', '0704', '00', '0705', '01', '084')
  ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS affected = ROW_COUNT;
  changed := changed + affected;

  IF changed > 0 THEN
    REFRESH MATERIALIZED VIEW mv_latest_pokemon_status;
    REFRESH MATERIALIZED VIEW mv_quiz_status;
    REFRESH MATERIALIZED VIEW mv_bsquiz_status;
    REFRESH MATERIALIZED VIEW mv_pokemon_shiritori_status;
    REFRESH MATERIALIZED VIEW mv_shiritori_words;
    REFRESH MATERIALIZED VIEW mv_lang_quiz;
    RAISE NOTICE 'CHANGED: fixed % rows and refreshed the materialized views', changed;
  END IF;
END
$$;
