-- Instances stop being drawn from a fixed catalogue of sizes.
--
-- cpu, memory and disk are whatever the caller asked for; a named instance_type
-- is only a shorthand that filled those numbers in, so it is now optional and
-- '' means "these numbers were given explicitly".
ALTER TABLE instances ALTER COLUMN instance_type SET DEFAULT '';

-- Whether the balloon driver is enabled. Proxmox disables it by setting the
-- balloon target to 0, which is also why no floor may be stored when it is off:
-- a floor that nothing enforces would be a lie in the ledger.
ALTER TABLE instances ADD COLUMN ballooning boolean NOT NULL DEFAULT true;
ALTER TABLE instances ADD CONSTRAINT instances_balloon_floor
    CHECK ((ballooning AND memory_min_mib > 0 AND memory_min_mib <= memory_mib)
        OR (NOT ballooning AND memory_min_mib = 0));

-- Sizes that could never boot are refused by the database too, not only by the
-- API, so a hand-written row cannot produce a VM Proxmox will not start.
ALTER TABLE instances ADD CONSTRAINT instances_size
    CHECK (cpu_cores >= 1 AND memory_mib >= 512 AND root_disk_gib >= 1);
