-- Volumes and security groups (Phase 4).

-- A volume is an extra disk. While attached it is a virtioN disk on its
-- instance's VM; while detached it waits as an unusedN entry on the volume
-- holder, a VM in the cloud pool that is never started. Proxmox names every
-- disk after the VM that owns it and only move_disk changes the owner, so a
-- disk that belongs to no VM cannot exist; the holder is that owner.
CREATE TABLE volumes (
    volume_id text PRIMARY KEY CHECK (volume_id ~ '^vol-[0-9a-f]{17}$'),
    account_id text NOT NULL REFERENCES accounts (id),
    client_token text,
    request_sha256 bytea,
    size_gib int NOT NULL CHECK (size_gib > 0),
    tags jsonb NOT NULL DEFAULT '{}',
    state text NOT NULL CHECK (state IN ('creating', 'available', 'in-use', 'deleting', 'deleted', 'error')),
    -- The attachment, set as soon as it is requested and cleared once the disk
    -- is back on the holder.
    instance_id text REFERENCES instances (instance_id),
    device text CHECK (device ~ '^virtio([1-9]|1[0-5])$'),
    attachment_state text CHECK (attachment_state IN ('attaching', 'attached', 'detaching')),
    pending_action text CHECK (pending_action IN ('create', 'attach', 'detach', 'resize', 'delete')),
    state_reason text NOT NULL DEFAULT '',
    last_error text NOT NULL DEFAULT '',
    attempts int NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    lease_until timestamptz,
    -- Where the disk is: the VM whose config holds it, under which key, and the
    -- Proxmox volume ID, which changes every time the owning VM does.
    vmid int,
    config_key text,
    volid text,
    -- Written before each move_disk. After a crash the disk is either still at
    -- (vmid, config_key) or already at (move_vmid, move_key); nothing else.
    move_vmid int,
    move_key text,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_id, client_token),
    CHECK ((instance_id IS NULL) = (device IS NULL) AND (instance_id IS NULL) = (attachment_state IS NULL))
);
CREATE UNIQUE INDEX volumes_device ON volumes (instance_id, device) WHERE instance_id IS NOT NULL;
CREATE UNIQUE INDEX volumes_live_volid ON volumes (volid) WHERE state <> 'deleted' AND volid IS NOT NULL;
CREATE INDEX volumes_account ON volumes (account_id, created_at DESC);
CREATE INDEX volumes_work ON volumes (next_attempt_at) WHERE pending_action IS NOT NULL;

-- Security groups are the API's own objects. Proxmox's cluster-wide groups
-- need Sys.Modify on /, so each instance gets its groups' rules rendered into
-- its own VM firewall instead.
CREATE TABLE security_groups (
    group_id text PRIMARY KEY CHECK (group_id ~ '^sg-[0-9a-f]{17}$'),
    account_id text NOT NULL REFERENCES accounts (id),
    group_name text NOT NULL CHECK (group_name ~ '^[A-Za-z0-9][A-Za-z0-9 ._:@-]{0,63}$'),
    description text NOT NULL DEFAULT '' CHECK (length(description) <= 255),
    is_default boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_id, group_name)
);
CREATE UNIQUE INDEX security_groups_one_default ON security_groups (account_id) WHERE is_default;

CREATE TABLE security_group_rules (
    rule_id text PRIMARY KEY CHECK (rule_id ~ '^sgr-[0-9a-f]{17}$'),
    group_id text NOT NULL REFERENCES security_groups (group_id) ON DELETE CASCADE,
    direction text NOT NULL CHECK (direction IN ('ingress', 'egress')),
    protocol text NOT NULL CHECK (protocol IN ('tcp', 'udp', 'icmp', 'icmpv6', 'all')),
    from_port int CHECK (from_port BETWEEN 0 AND 65535),
    to_port int CHECK (to_port BETWEEN 0 AND 65535),
    cidr cidr NOT NULL,
    description text NOT NULL DEFAULT '' CHECK (length(description) <= 255),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((protocol IN ('tcp', 'udp')) = (from_port IS NOT NULL AND to_port IS NOT NULL)),
    CHECK (from_port IS NULL OR from_port <= to_port),
    -- Proxmox refuses an ICMP rule whose address is of the other family.
    CHECK (protocol <> 'icmp' OR family(cidr) = 4),
    CHECK (protocol <> 'icmpv6' OR family(cidr) = 6)
);
CREATE UNIQUE INDEX security_group_rules_unique ON security_group_rules
    (group_id, direction, protocol, coalesce(from_port, -1), coalesce(to_port, -1), cidr);

CREATE TABLE instance_security_groups (
    instance_id text NOT NULL REFERENCES instances (instance_id),
    group_id text NOT NULL REFERENCES security_groups (group_id),
    PRIMARY KEY (instance_id, group_id)
);
CREATE INDEX instance_security_groups_group ON instance_security_groups (group_id);

-- What the instance's VM firewall should look like is a function of its groups
-- and their rules. generation moves whenever that input changes; applied is the
-- generation last written to Proxmox. Instances from before this migration
-- have no groups, are unfiltered, and start in sync at 0 = 0.
ALTER TABLE instances ADD COLUMN firewall_generation bigint NOT NULL DEFAULT 0;
ALTER TABLE instances ADD COLUMN firewall_applied bigint NOT NULL DEFAULT 0;
ALTER TABLE instances ADD COLUMN firewall_next_attempt_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE instances ADD COLUMN firewall_lease_until timestamptz;
ALTER TABLE instances ADD COLUMN firewall_last_error text NOT NULL DEFAULT '';
CREATE INDEX instances_firewall_work ON instances (firewall_next_attempt_at) WHERE firewall_generation <> firewall_applied;

-- Volume limits, administrator-settable like the rest. NULL means the
-- deployment default applies; 0 is unlimited for the account quotas.
ALTER TABLE limit_overrides ADD COLUMN account_volumes int CHECK (account_volumes >= 0);
ALTER TABLE limit_overrides ADD COLUMN account_volume_gib int CHECK (account_volume_gib >= 0);
ALTER TABLE limit_overrides ADD COLUMN volume_min_gib int CHECK (volume_min_gib >= 1);
ALTER TABLE limit_overrides ADD COLUMN volume_max_gib int CHECK (volume_max_gib >= 1);
