-- Instances (Phase 2).

CREATE TABLE instances (
    instance_id text PRIMARY KEY CHECK (instance_id ~ '^i-[0-9a-f]{17}$'),
    account_id text NOT NULL REFERENCES accounts (id),
    -- A retried RunInstances with the same client_token returns this instance
    -- instead of creating another. request_sha256 detects a reused token with
    -- different parameters.
    client_token text,
    request_sha256 bytea,
    name text NOT NULL DEFAULT '',
    image_id text NOT NULL,
    instance_type text NOT NULL,
    cpu_cores int NOT NULL,
    memory_mib int NOT NULL,
    memory_min_mib int NOT NULL,
    root_disk_gib int NOT NULL,
    user_data text NOT NULL DEFAULT '',
    tags jsonb NOT NULL DEFAULT '{}',
    state text NOT NULL CHECK (state IN ('pending', 'running', 'stopping', 'stopped', 'shutting-down', 'terminated')),
    -- Work the worker still owes this instance. NULL when there is none.
    pending_action text CHECK (pending_action IN ('launch', 'start', 'stop', 'reboot', 'terminate')),
    state_reason text NOT NULL DEFAULT '',
    last_error text NOT NULL DEFAULT '',
    attempts int NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    -- Set while a worker holds the instance, so a crashed worker's claim expires.
    lease_until timestamptz,
    -- Backend resources, recorded as soon as each exists so a terminate after a
    -- crash knows exactly what to remove.
    vmid int,
    vm_created boolean NOT NULL DEFAULT false,
    mac_address text NOT NULL,
    ip_address text,
    netbox_ip_id int,
    seed_volume text,
    launch_time timestamptz NOT NULL DEFAULT now(),
    terminated_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_id, client_token)
);
-- A VMID belongs to at most one instance until that instance is fully terminated.
CREATE UNIQUE INDEX instances_live_vmid ON instances (vmid) WHERE state <> 'terminated' AND vmid IS NOT NULL;
CREATE INDEX instances_account ON instances (account_id, launch_time DESC);
CREATE INDEX instances_work ON instances (next_attempt_at) WHERE pending_action IS NOT NULL;

-- VMIDs found already taken by something the API did not create. Never handed out again.
CREATE TABLE vmid_quarantine (
    vmid int PRIMARY KEY,
    reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
