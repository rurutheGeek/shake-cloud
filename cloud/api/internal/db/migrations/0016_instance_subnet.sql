-- Subnets. An instance sits in one of the segments the home network is cut
-- into (site.json's network.subnets). Only the name is recorded; what the
-- segment is — its range, gateway and VLAN — is a deployment fact.
-- '' means the default subnet, which is where every instance made before this
-- migration lives.

ALTER TABLE instances ADD COLUMN subnet text NOT NULL DEFAULT '';
