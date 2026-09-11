-- Limits an administrator has changed at runtime.
--
-- One row, and every column is nullable: NULL means "no override, use the
-- deployment default from platform/terraform/cloud.yaml". Only what an
-- administrator actually changed lives here, so the same limit is never
-- declared in two places.
--
-- 0 means unlimited for the quota columns and memory_budget_mib, and it turns
-- vm_disk_max_used_percent off entirely (0 cannot mean "refuse above 0% used",
-- which would refuse everything). node_memory_reserve_mib at 0 keeps the check
-- that the memory being asked for is actually free, but keeps nothing back for
-- the host. Those last two are what stop a full host, so 0 there is an
-- administrator deliberately removing the guard.
CREATE TABLE limit_overrides (
    id boolean PRIMARY KEY DEFAULT true CHECK (id),
    account_instances int CHECK (account_instances >= 0),
    account_vcpus int CHECK (account_vcpus >= 0),
    account_memory_mib int CHECK (account_memory_mib >= 0),
    account_root_disk_gib int CHECK (account_root_disk_gib >= 0),
    root_disk_min_gib int CHECK (root_disk_min_gib > 0),
    root_disk_default_gib int CHECK (root_disk_default_gib > 0),
    root_disk_max_gib int CHECK (root_disk_max_gib > 0),
    memory_budget_mib int CHECK (memory_budget_mib >= 0),
    node_memory_reserve_mib int CHECK (node_memory_reserve_mib >= 0),
    vm_disk_max_used_percent int CHECK (vm_disk_max_used_percent BETWEEN 0 AND 100),
    image_store_min_free_mib int CHECK (image_store_min_free_mib >= 0),
    updated_at timestamptz,
    -- The account that last changed them. Kept for the portal; the audit log is
    -- the record that cannot be overwritten.
    updated_by text REFERENCES accounts (id),
    -- Whatever is stored must be internally consistent even if it is written
    -- outside the API. The order against the defaults is checked in Go, which
    -- knows them.
    CHECK (root_disk_min_gib IS NULL OR root_disk_max_gib IS NULL OR root_disk_min_gib <= root_disk_max_gib),
    CHECK (root_disk_min_gib IS NULL OR root_disk_default_gib IS NULL OR root_disk_min_gib <= root_disk_default_gib),
    CHECK (root_disk_default_gib IS NULL OR root_disk_max_gib IS NULL OR root_disk_default_gib <= root_disk_max_gib)
);

-- The row exists from the start, so reading limits never has to create it.
INSERT INTO limit_overrides (id) VALUES (true);
