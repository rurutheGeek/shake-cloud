-- Database appliances (CloudNativePG).

-- One database appliance maps to one CloudNativePG Cluster in a namespace.
-- The id doubles as the cluster name, so it must be a DNS-safe label.
CREATE TABLE databases (
    database_id    text PRIMARY KEY CHECK (database_id ~ '^db-[0-9a-f]{17}$'),
    account_id     text NOT NULL REFERENCES accounts (id),
    name           text NOT NULL CHECK (name ~ '^[a-z][a-z0-9-]{1,29}$'),
    namespace      text NOT NULL,
    engine         text NOT NULL DEFAULT 'postgres',
    engine_version text NOT NULL,
    storage_gib    integer NOT NULL CHECK (storage_gib > 0),
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_id, name)
);
CREATE INDEX databases_account ON databases (account_id, created_at DESC);
