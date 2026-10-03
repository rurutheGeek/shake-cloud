-- The address filter now also lets a guest send from global IPv6 (2000::/3).
-- Filters written before this hold only the IPv4 address, so every instance
-- with groups is marked for a rewrite; the firewall worker does the rest.

UPDATE instances SET firewall_generation = firewall_generation + 1
WHERE state <> 'terminated'
  AND instance_id IN (SELECT instance_id FROM instance_security_groups);
