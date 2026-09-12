-- Serverless functions (Knative).

-- One function maps to one Knative Service in a namespace. The id doubles as
-- the service name, so it must be a DNS-safe label.
CREATE TABLE functions (
    function_id text PRIMARY KEY CHECK (function_id ~ '^fn-[0-9a-f]{17}$'),
    account_id  text NOT NULL REFERENCES accounts (id),
    name        text NOT NULL CHECK (name ~ '^[a-z][a-z0-9-]{1,29}$'),
    namespace   text NOT NULL,
    image       text NOT NULL CHECK (image <> ''),
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_id, name)
);
CREATE INDEX functions_account ON functions (account_id, created_at DESC);
