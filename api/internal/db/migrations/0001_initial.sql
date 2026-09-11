-- Accounts, access keys, browser sessions and the audit log (Phase 1).

-- One Authentik user is one account. The ID is 12 digits, like an AWS account ID.
CREATE TABLE accounts (
    id text PRIMARY KEY CHECK (id ~ '^[0-9]{12}$'),
    kind text NOT NULL CHECK (kind IN ('user', 'bootstrap')),
    -- Authentik sub with sub_mode=user_uuid, which survives re-creating the
    -- OIDC provider. NULL only for the bootstrap account, which has no login.
    subject text UNIQUE,
    username text NOT NULL,
    email text NOT NULL DEFAULT '',
    is_admin boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz,
    CHECK ((kind = 'user') = (subject IS NOT NULL))
);
CREATE UNIQUE INDEX accounts_one_bootstrap ON accounts (kind) WHERE kind = 'bootstrap';
-- A known email arriving with an unknown sub is refused, not given a second account.
CREATE UNIQUE INDEX accounts_user_email ON accounts (lower(email)) WHERE kind = 'user' AND email <> '';

-- Rows are revoked, never deleted, so audit events keep pointing at a real key.
CREATE TABLE access_keys (
    access_key_id text PRIMARY KEY CHECK (access_key_id ~ '^[a-z2-7]{20}$'),
    account_id text NOT NULL REFERENCES accounts (id),
    secret_sha256 bytea NOT NULL CHECK (length(secret_sha256) = 32),
    description text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    revoked_at timestamptz,
    last_used_at timestamptz
);
CREATE INDEX access_keys_account ON access_keys (account_id);

-- The cookie holds a random token; only its hash is stored.
CREATE TABLE sessions (
    token_sha256 bytea PRIMARY KEY CHECK (length(token_sha256) = 32),
    account_id text NOT NULL REFERENCES accounts (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);
CREATE INDEX sessions_expires ON sessions (expires_at);

-- An OIDC login in flight. Deleted when the callback arrives, so each state is
-- usable once.
CREATE TABLE login_attempts (
    state_sha256 bytea PRIMARY KEY CHECK (length(state_sha256) = 32),
    nonce text NOT NULL,
    code_verifier text NOT NULL,
    expires_at timestamptz NOT NULL
);

-- Field names follow CloudTrail's LookupEvents.
CREATE TABLE audit_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_time timestamptz NOT NULL DEFAULT now(),
    event_name text NOT NULL,
    account_id text REFERENCES accounts (id),
    -- No foreign key: failed attempts name keys that may not exist.
    access_key_id text,
    credential_type text NOT NULL CHECK (credential_type IN ('none', 'session', 'access_key')),
    source_ip_address text NOT NULL,
    user_agent text NOT NULL DEFAULT '',
    request_id text NOT NULL,
    resource_id text,
    -- NULL on success.
    error_code text,
    detail jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX audit_events_account ON audit_events (account_id, event_id DESC);
CREATE INDEX audit_events_access_key ON audit_events (access_key_id, event_id DESC) WHERE access_key_id IS NOT NULL;

-- The API never rewrites history, so a bug that tries to is an error, not a quiet loss.
CREATE FUNCTION audit_events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only';
END
$$;
CREATE TRIGGER audit_events_no_update_or_delete BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_append_only();
CREATE TRIGGER audit_events_no_truncate BEFORE TRUNCATE ON audit_events
    FOR EACH STATEMENT EXECUTE FUNCTION audit_events_append_only();
