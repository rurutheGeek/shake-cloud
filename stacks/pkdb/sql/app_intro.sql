-- イントロクイズ（Discord Bot「UBSLEEPY」）の対応リスト。
--
-- アプリのために作った表は `app_<アプリ名>_` で始める（図鑑の表と見分けるため）。
-- Bot は pkdb_reader で1分ごとに読み直すので、ここを直せば配備なしで反映される。
-- 直すのは UBSLEEPY-next の tools/intro_db.py（pkdb_editor で書く）。
--
-- 作品は略称（SV・BW2 など。UBSLEEPY-next の resource/intro_works.csv の先頭の略称）、
-- 曲名は曲リストの曲名で持つ。対応リストを直している間は正規化しない
-- （作品・曲のマスタを作るのは、リストが固まってから）。
-- 冪等。何度流しても同じ。

-- 曲の別名。1行に別名1つ。
CREATE TABLE IF NOT EXISTS pokemondb.app_intro_alias (
    work TEXT NOT NULL,      -- 原曲の作品（略称）
    title TEXT NOT NULL,     -- 曲名
    in_work TEXT NOT NULL,   -- この呼び方が通る作品（略称）。ふつうは work と同じ。
                             -- 違うときは、再録でその作品に流れるときだけの呼び名
    alias TEXT NOT NULL,
    note TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (work, title, in_work, alias)
);

-- 曲がほかに流れる作品（再録・流用）。その作品の略称でも答えられ、絞り込みにも入る。
CREATE TABLE IF NOT EXISTS pokemondb.app_intro_appearance (
    work TEXT NOT NULL,        -- 原曲の作品（略称）
    title TEXT NOT NULL,       -- 曲名
    appears_in TEXT NOT NULL,  -- 流れる作品（略称）
    note TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (work, title, appears_in)
);

-- ふだんは出題しない音源（未使用曲・古いバージョンなど）。
CREATE TABLE IF NOT EXISTS pokemondb.app_intro_secret (
    work TEXT NOT NULL,    -- 作品（略称）
    title TEXT NOT NULL,   -- 曲名（音源ごと。「（Ver. 1.0）」なども含めてそのまま）
    reason TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (work, title)
);

GRANT SELECT ON pokemondb.app_intro_alias, pokemondb.app_intro_appearance,
    pokemondb.app_intro_secret TO pkdb_reader, pkdb_entry;
GRANT SELECT, INSERT, UPDATE, DELETE ON pokemondb.app_intro_alias,
    pokemondb.app_intro_appearance, pokemondb.app_intro_secret TO pkdb_editor;
-- pkdb_editor は表の権限は持っていたが、スキーマに入る権限が無く、実際には使えなかった。
GRANT USAGE ON SCHEMA pokemondb TO pkdb_editor;
