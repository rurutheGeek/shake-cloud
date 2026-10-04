-- pokemondb の表・列・制約・索引・シーケンスの名前を小文字へ揃える。
--
-- 旧ホストでは大文字で作っていたため、どの名前も二重引用符が必須だった
-- （"POKEMON_STATUS"."BASESTATS_H"）。小文字にすると引用符なしで書ける。
-- ビューとマテリアライズドビューの定義は PostgreSQL が追従するので作り直さない。
-- 日本語の列名（pokemon_calendar・pokemon_senryu）は引用符なしで書けるので変えない。
--
-- 何度流してもよい。旧ホストから取り直して復元した後も、これを流せば揃う。
-- 利用者が schema を付けずに書けるよう、search_path も pokemondb にする。

DO $$
DECLARE
  item record;
  changed integer := 0;
BEGIN
  FOR item IN
    SELECT c.oid::regclass AS relation, a.attname
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    WHERE c.relnamespace = 'pokemondb'::regnamespace
      AND c.relkind IN ('r', 'v', 'm')
      AND a.attnum > 0 AND NOT a.attisdropped
      AND a.attname <> lower(a.attname)
  LOOP
    EXECUTE format('ALTER TABLE %s RENAME COLUMN %I TO %I',
                   item.relation, item.attname, lower(item.attname));
    changed := changed + 1;
  END LOOP;

  -- 主キーと一意制約は、制約の改名で裏の索引も同じ名前になる。
  FOR item IN
    SELECT conrelid::regclass AS relation, conname
    FROM pg_constraint
    WHERE connamespace = 'pokemondb'::regnamespace
      AND conrelid <> 0 AND conname <> lower(conname)
  LOOP
    EXECUTE format('ALTER TABLE %s RENAME CONSTRAINT %I TO %I',
                   item.relation, item.conname, lower(item.conname));
    changed := changed + 1;
  END LOOP;

  IF changed > 0 THEN
    RAISE NOTICE 'CHANGED: renamed % columns and constraints', changed;
  END IF;
END
$$;

-- 制約の改名で索引の名前が変わった後の状態を見るため、文を分ける。
DO $$
DECLARE
  item record;
  changed integer := 0;
BEGIN
  FOR item IN
    SELECT c.oid::regclass AS relation, c.relname, c.relkind
    FROM pg_class c
    WHERE c.relnamespace = 'pokemondb'::regnamespace
      AND c.relkind IN ('r', 'v', 'm', 'i', 'S')
      AND c.relname <> lower(c.relname)
  LOOP
    EXECUTE format('ALTER %s %s RENAME TO %I',
                   CASE item.relkind WHEN 'r' THEN 'TABLE' WHEN 'v' THEN 'VIEW'
                                     WHEN 'm' THEN 'MATERIALIZED VIEW'
                                     WHEN 'i' THEN 'INDEX' ELSE 'SEQUENCE' END,
                   item.relation, lower(item.relname));
    changed := changed + 1;
  END LOOP;

  IF changed > 0 THEN
    RAISE NOTICE 'CHANGED: renamed % tables, views, indexes and sequences', changed;
  END IF;
END
$$;

-- 関数の本体は文字列なので、表や列の改名に追従しない。引用符つきの大文字の名前を
-- 小文字へ書き換えて作り直す。
DO $$
DECLARE
  item record;
  identifier text;
  definition text;
  changed integer := 0;
BEGIN
  FOR item IN
    SELECT p.oid, pg_get_functiondef(p.oid) AS definition
    FROM pg_proc p
    WHERE p.pronamespace = 'pokemondb'::regnamespace
      AND p.prosrc ~ '"[A-Z][A-Z0-9_]*"'
  LOOP
    definition := item.definition;
    FOR identifier IN
      SELECT DISTINCT hit[1]
      FROM regexp_matches(item.definition, '"([A-Z][A-Z0-9_]*)"', 'g') AS hit
    LOOP
      definition := replace(definition, '"' || identifier || '"', lower(identifier));
    END LOOP;
    EXECUTE definition;
    changed := changed + 1;
  END LOOP;

  IF changed > 0 THEN
    RAISE NOTICE 'CHANGED: rewrote % functions', changed;
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_db_role_setting s
    JOIN pg_database d ON d.oid = s.setdatabase
    WHERE d.datname = current_database() AND s.setrole = 0
      AND 'search_path=pokemondb, public' = ANY (s.setconfig)
  ) THEN
    EXECUTE format('ALTER DATABASE %I SET search_path = pokemondb, public', current_database());
    RAISE NOTICE 'CHANGED: search_path set to pokemondb, public';
  END IF;
END
$$;
