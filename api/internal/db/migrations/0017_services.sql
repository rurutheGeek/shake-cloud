-- Container services: always-on Deployments in Kubernetes.

-- One service maps to one Deployment (and its Secret, disk and LoadBalancer)
-- in a namespace. The id doubles as the object names, so it must be a
-- DNS-safe label. Secret values live only in Kubernetes; the ledger keeps
-- their names.
CREATE TABLE services (
    service_id      text PRIMARY KEY CHECK (service_id ~ '^svc-[0-9a-f]{17}$'),
    account_id      text NOT NULL REFERENCES accounts (id),
    name            text NOT NULL CHECK (name ~ '^[a-z][a-z0-9-]{1,29}$'),
    namespace       text NOT NULL,
    image           text NOT NULL CHECK (image <> ''),
    port            integer NOT NULL DEFAULT 0 CHECK (port BETWEEN 0 AND 65535),
    memory_mib      integer NOT NULL CHECK (memory_mib BETWEEN 32 AND 512),
    env             jsonb NOT NULL DEFAULT '{}',
    secret_names    text[] NOT NULL DEFAULT '{}',
    disk_gib        integer NOT NULL DEFAULT 0 CHECK (disk_gib BETWEEN 0 AND 32),
    mount_path      text NOT NULL DEFAULT '',
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_id, name)
);
CREATE INDEX services_account ON services (account_id, created_at DESC);
