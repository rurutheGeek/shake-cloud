-- UBSLEEPY のセーブ用テーブル。Bot も CREATE TABLE IF NOT EXISTS するが、
-- 所有者と読み取り権限まで配備で揃える。
CREATE TABLE IF NOT EXISTS save_user (
    user_id BIGINT PRIMARY KEY,
    user_name TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS save_value (
    user_id BIGINT NOT NULL REFERENCES save_user(user_id) ON DELETE CASCADE,
    save_key TEXT NOT NULL,
    value BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, save_key)
);

ALTER TABLE save_user OWNER TO ubsleepy_writer;
ALTER TABLE save_value OWNER TO ubsleepy_writer;

GRANT USAGE ON SCHEMA public TO ubsleepy_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ubsleepy_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE ubsleepy_writer IN SCHEMA public
    GRANT SELECT ON TABLES TO ubsleepy_reader;
