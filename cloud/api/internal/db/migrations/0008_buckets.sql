-- Buckets and S3 keys (Phase 7).

-- A bucket is an S3 bucket in Garage, owned by one account. The name is the
-- global alias and is unique across the cloud, as in S3. garage_id is Garage's
-- own identifier, which the admin API uses to delete the bucket.
CREATE TABLE buckets (
    bucket_name text PRIMARY KEY CHECK (bucket_name ~ '^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$'),
    account_id  text NOT NULL REFERENCES accounts (id),
    garage_id   text NOT NULL UNIQUE,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX buckets_account ON buckets (account_id, created_at DESC);

-- An S3 access key. Only the key id and its name are kept: Garage shows the
-- secret once, at creation, and never again, so the cloud API cannot store it.
CREATE TABLE s3_keys (
    key_id     text PRIMARY KEY,
    account_id text NOT NULL REFERENCES accounts (id),
    name       text NOT NULL CHECK (name ~ '^[A-Za-z0-9][A-Za-z0-9 ._:@-]{0,63}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_id, name)
);
CREATE INDEX s3_keys_account ON s3_keys (account_id, created_at DESC);

-- What a key may do with a bucket. Garage's permissions are read/write/owner.
CREATE TABLE bucket_keys (
    bucket_name text NOT NULL REFERENCES buckets (bucket_name) ON DELETE CASCADE,
    key_id      text NOT NULL REFERENCES s3_keys (key_id) ON DELETE CASCADE,
    can_read    boolean NOT NULL DEFAULT false,
    can_write   boolean NOT NULL DEFAULT false,
    is_owner    boolean NOT NULL DEFAULT false,
    PRIMARY KEY (bucket_name, key_id)
);
