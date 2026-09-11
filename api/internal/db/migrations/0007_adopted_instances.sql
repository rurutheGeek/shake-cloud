-- Adopting an existing VM into the cloud (Phase 5).

-- An instance the API did not create: an administrator moved a VM that already
-- existed into the cloud pool and registered it here. It has none of the
-- creation records (source image, user-data, seed ISO) a launched instance has,
-- so those columns stay empty and must not be required. The flag is what tells
-- the worker that the VM is the API's to manage even though its description
-- does not carry the instance ID the way a launched VM's does.
ALTER TABLE instances ADD COLUMN adopted boolean NOT NULL DEFAULT false;

-- A vmid is held by at most one live instance either way, adopted or launched,
-- and the existing unique index already enforces that.
