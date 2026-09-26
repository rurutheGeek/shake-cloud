-- An access key's scope: ReadWrite may call every operation, ReadOnly only
-- the ones that do not change state. Existing keys keep working: the default
-- is the behaviour they had before scopes existed.
ALTER TABLE access_keys ADD COLUMN scope text NOT NULL DEFAULT 'ReadWrite'
    CHECK (scope IN ('ReadOnly', 'ReadWrite'));
