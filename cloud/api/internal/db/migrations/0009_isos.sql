-- ISO installation media (Phase 8).
--
-- An ISO is not an image: it is never the root disk. It is attached as a
-- CD-ROM so the guest installs itself from it, and afterwards it is only media
-- a running instance may still read. It lives in the same store as images but
-- under :iso/, and deleting a row removes the file the same way.
CREATE TABLE isos (
    iso_id     text PRIMARY KEY CHECK (iso_id ~ '^iso-[0-9a-f]{17}$'),
    account_id text NOT NULL REFERENCES accounts (id),
    name       text NOT NULL CHECK (name <> ''),
    volume     text NOT NULL UNIQUE,
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    -- '' is a Linux installer, 'windows' selects the Windows 11 hardware.
    os         text NOT NULL DEFAULT '' CHECK (os IN ('', 'linux', 'windows')),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX isos_account ON isos (account_id, created_at DESC);

-- An instance installed from ISO has no source image: image_id stays empty and
-- install_iso_id / driver_iso_id are the media attached at launch. guest_os
-- decides the virtual hardware and survives the ISOs' deletion.
ALTER TABLE instances
    ADD COLUMN guest_os       text NOT NULL DEFAULT '',
    ADD COLUMN install_iso_id text,
    ADD COLUMN driver_iso_id  text;
