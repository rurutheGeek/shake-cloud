-- Disk tiers. A caller chooses ssd (the default) or hdd; which pool a tier
-- points at is a deployment fact in site.yaml, so only the name is recorded.
-- Every disk made before this migration lives on the default pool.

ALTER TABLE instances ADD COLUMN disk_tier text NOT NULL DEFAULT 'ssd'
    CHECK (disk_tier IN ('ssd', 'hdd'));
ALTER TABLE volumes ADD COLUMN disk_tier text NOT NULL DEFAULT 'ssd'
    CHECK (disk_tier IN ('ssd', 'hdd'));
