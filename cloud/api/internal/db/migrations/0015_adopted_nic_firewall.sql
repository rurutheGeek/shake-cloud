-- An adopted VM's NIC is now put behind the VM firewall when its groups are
-- written. Instances adopted before this are marked for a rewrite.

UPDATE instances SET firewall_generation = firewall_generation + 1
WHERE adopted AND state <> 'terminated'
  AND instance_id IN (SELECT instance_id FROM instance_security_groups);
