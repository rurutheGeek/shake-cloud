-- SSH key pairs and uploaded images (Phase 3).

-- Only public keys. The API never stores a private key, and the public half is
-- written into an instance's seed image at launch, so deleting a key pair later
-- cannot lock anyone out of a VM that already exists.
CREATE TABLE key_pairs (
    account_id text NOT NULL REFERENCES accounts (id),
    key_name text NOT NULL CHECK (key_name ~ '^[A-Za-z0-9][A-Za-z0-9 ._:@-]{0,63}$'),
    public_key text NOT NULL,
    -- OpenSSH's SHA256:… form, so it can be compared with `ssh-keygen -lf`.
    fingerprint text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, key_name)
);

-- Images a user uploaded. The deployment's shared images are NOT here: they are
-- declared in Terraform and rendered into site.json, and putting them in this
-- table as well would be the same fact in two places. The API merges the two
-- when it answers DescribeImages.
CREATE TABLE images (
    image_id text PRIMARY KEY CHECK (image_id ~ '^img-[0-9a-f]{17}$'),
    account_id text NOT NULL REFERENCES accounts (id),
    name text NOT NULL CHECK (name <> ''),
    -- The Proxmox volume, e.g. cloud-images:import/img-….qcow2. Unique so two
    -- rows can never claim the same file.
    volume text NOT NULL UNIQUE,
    format text NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX images_account ON images (account_id, created_at DESC);

-- What was written into this instance's seed image. Both columns are a record
-- of what happened, not a reference: the key pair may be deleted afterwards,
-- and the instance keeps working because the key went into the image. The key
-- text is resolved when the launch is admitted, so deleting the key pair in the
-- seconds before the worker builds the image cannot leave a VM with no way in.
ALTER TABLE instances ADD COLUMN key_name text;
ALTER TABLE instances ADD COLUMN key_public_key text;

-- The largest single image an upload may store. Administrator-settable like
-- every other limit; NULL means the deployment default applies.
ALTER TABLE limit_overrides ADD COLUMN max_image_gib int CHECK (max_image_gib >= 0);
