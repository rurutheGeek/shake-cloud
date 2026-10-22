-- クイズ（Discord Bot「UBSLEEPY」）のデータ。トレーナーの手持ちと、野生の出現。
--
-- アプリのために作った表は `app_<アプリ名>_` で始める（図鑑の表と見分けるため）。
-- 作品は title_solo.title_id（4桁）、ポケモンは pokemon_name_form と同じ
-- ndex_number（4桁）・form_id（2桁）で持つ。名前は図鑑の表から引く。
-- 中身は UBSLEEPY-next の temp/quizdata（pret・Bulbapedia・PokeAPI・PKHeX などから集めたもの）を
-- pkdb_editor で入れる。
-- 冪等。何度流しても同じ。

-- トレーナーの手持ち。1行が1つの対戦の1匹。
CREATE TABLE IF NOT EXISTS pokemondb.app_quiz_trainer (
    id SERIAL PRIMARY KEY,
    title_id VARCHAR(4) NOT NULL,   -- 作品
    trainer_key TEXT NOT NULL,      -- 対戦の識別子（同じ値の行が1つの対戦）
    battle_no INTEGER,              -- 何戦目か（再戦の区別）
    role TEXT,                      -- ジムリーダー・四天王・チャンピオン・ライバル など。NULL は一般トレーナー
    named BOOLEAN NOT NULL,         -- ネームドか
    class_en TEXT,                  -- 職業（英語）
    class_ja TEXT,                  -- 職業（日本語）
    name_en TEXT,                   -- 名前（英語）
    name_ja TEXT,                   -- 名前（日本語。ネームドだけ）
    location_en TEXT,               -- 場所（英語）
    double_battle BOOLEAN,          -- ダブルバトルか（分からなければ NULL）
    slot INTEGER NOT NULL,          -- 手持ちの何匹目か
    ndex_number VARCHAR(4) NOT NULL,
    form_id VARCHAR(2),             -- 分からなければ NULL
    level INTEGER,                  -- バトル施設の候補などで決まっていなければ NULL
    item TEXT,                      -- 持ち物（日本語）
    ability TEXT,                   -- 特性（日本語）
    move1 TEXT, move2 TEXT, move3 TEXT, move4 TEXT,  -- わざ（日本語）
    note TEXT                       -- 補足（pool=yes: バトル施設の候補の一覧 など）
);
CREATE INDEX IF NOT EXISTS app_quiz_trainer_title ON pokemondb.app_quiz_trainer (title_id, trainer_key);
CREATE INDEX IF NOT EXISTS app_quiz_trainer_pokemon ON pokemondb.app_quiz_trainer (ndex_number, form_id);

-- 野生の出現。1行が、場所・出方・時間帯・条件ごとの1匹。
CREATE TABLE IF NOT EXISTS pokemondb.app_quiz_wild (
    id SERIAL PRIMARY KEY,
    title_id VARCHAR(4) NOT NULL,   -- 作品
    version TEXT,                   -- 1つの作品に版が2つあるときの版（剣盾の DLC など）
    location TEXT NOT NULL,         -- 場所（日本語）
    method TEXT NOT NULL,           -- 出方（くさむら・どうくつ、なみのり、ボロのつりざお など）
    time TEXT,                      -- 時間帯・季節・天気など。NULL はいつでも
    condition TEXT,                 -- 条件（大量発生、ポケトレ など）。NULL は条件なし
    ndex_number VARCHAR(4) NOT NULL,
    form_id VARCHAR(2),             -- 分からないとき・姿がいろいろなときは NULL
    form_note TEXT,                 -- form_id が無いときの姿の説明（いろいろな姿 など）
    level_min INTEGER,
    level_max INTEGER,
    rate NUMERIC,                   -- 出やすさ。NULL は不明
    rate_unit TEXT                  -- % か weight（重み）
);
CREATE INDEX IF NOT EXISTS app_quiz_wild_title ON pokemondb.app_quiz_wild (title_id, location);
CREATE INDEX IF NOT EXISTS app_quiz_wild_pokemon ON pokemondb.app_quiz_wild (ndex_number, form_id);

-- アルセウスの出現テーブルの重み。テーブルとヒスイの地名を結ぶ表は無いので、地方の単位。
CREATE TABLE IF NOT EXISTS pokemondb.app_quiz_wild_weight (
    id SERIAL PRIMARY KEY,
    title_id VARCHAR(4) NOT NULL,
    region TEXT NOT NULL,           -- 地方（黒曜の原野 など）
    table_id TEXT NOT NULL,         -- 出現テーブル（lnd_no_00 など）
    table_kind TEXT,                -- 地上・ふつう、空・めずらしい、オヤブン・とくべつ など
    time TEXT,                      -- NULL はいつでも
    weather TEXT,                   -- NULL はどの天気でも
    ndex_number VARCHAR(4) NOT NULL,
    form_id VARCHAR(2),
    alpha BOOLEAN NOT NULL,         -- オヤブンか
    weight NUMERIC NOT NULL,       -- 元データは小数（誤差を丸めた）
    percent NUMERIC                 -- そのテーブル・時間帯・天気の中での割合
);

GRANT SELECT ON pokemondb.app_quiz_trainer, pokemondb.app_quiz_wild,
    pokemondb.app_quiz_wild_weight TO pkdb_reader, pkdb_entry;
GRANT SELECT, INSERT, UPDATE, DELETE ON pokemondb.app_quiz_trainer, pokemondb.app_quiz_wild,
    pokemondb.app_quiz_wild_weight TO pkdb_editor;
GRANT USAGE ON SEQUENCE pokemondb.app_quiz_trainer_id_seq, pokemondb.app_quiz_wild_id_seq,
    pokemondb.app_quiz_wild_weight_id_seq TO pkdb_editor;
