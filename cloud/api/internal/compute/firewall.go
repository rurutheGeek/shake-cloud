package compute

import (
	"context"
	"errors"
	"fmt"
	"net/url"
	"slices"
	"strconv"
	"strings"
	"time"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/proxmox"
)

// Security groups are rendered into each instance's own VM firewall, because
// Proxmox's cluster-wide groups need Sys.Modify on /. What a VM should have is
// a function of its groups' rules alone, so writing it is idempotent and the
// whole rule list is replaced rather than patched.

// ipfilterSet is the set Proxmox's ipfilter option reads for net0.
const ipfilterSet = "ipfilter-net0"

// filteredOptions are what every instance with groups gets. Both policies
// drop: a group's rules are all that is allowed, in and out, as in EC2.
// macfilter and ipfilter stop the guest sending as another MAC or IP address;
// ipfilter drops all IPv4 unless the instance's address is in ipfilterSet.
var filteredOptions = map[string]string{
	"enable": "1", "policy_in": "DROP", "policy_out": "DROP",
	"macfilter": "1", "ipfilter": "1", "dhcp": "0", "ndp": "1", "radv": "0",
}

// renderFirewall turns group rules into VM firewall rules, in order.
func renderFirewall(rules []db.SecurityGroupRule) []proxmox.FirewallRule {
	out := []proxmox.FirewallRule{}
	seen := map[proxmox.FirewallRule]bool{}
	for _, r := range rules {
		rule := proxmox.FirewallRule{Action: "ACCEPT", Enable: 1}
		if r.Direction == db.DirectionIngress {
			rule.Type, rule.Source = "in", r.CIDR.String()
		} else {
			rule.Type, rule.Dest = "out", r.CIDR.String()
		}
		switch r.Protocol {
		case "tcp", "udp":
			rule.Proto = r.Protocol
			if *r.FromPort != 0 || *r.ToPort != 65535 {
				rule.Dport = strconv.Itoa(*r.FromPort)
				if *r.ToPort != *r.FromPort {
					rule.Dport += ":" + strconv.Itoa(*r.ToPort)
				}
			}
		case "icmp":
			rule.Proto = "icmp"
		case "icmpv6":
			rule.Proto = "ipv6-icmp"
		}
		// Two groups may allow the same traffic; one rule is enough.
		if seen[rule] {
			continue
		}
		seen[rule] = true
		rule.Comment = "shakecloud " + r.GroupID + " " + r.ID
		out = append(out, rule)
	}
	return out
}

func sameRules(current, desired []proxmox.FirewallRule) bool {
	if len(current) != len(desired) {
		return false
	}
	for i := range desired {
		have := current[i]
		have.Pos = 0
		if have != desired[i] {
			return false
		}
	}
	return true
}

// writeFirewall brings an instance's VM firewall up to its groups and records
// the generation written. The generation is read before the rules, so a change
// made meanwhile leaves the two apart and is written next.
func (s *Service) writeFirewall(ctx context.Context, instanceID string) error {
	instance, err := db.GetInstance(ctx, s.Pool, instanceID)
	if err != nil {
		return err
	}
	if err := s.applyFirewall(ctx, instance); err != nil {
		return err
	}
	return db.RecordFirewallApplied(ctx, s.Pool, instance.ID, instance.FirewallGeneration)
}

func (s *Service) applyFirewall(ctx context.Context, instance db.Instance) error {
	if instance.VMID == nil {
		return errors.New("the instance has no VM")
	}
	vmid := *instance.VMID
	owned, err := s.owns(ctx, vmid, instance)
	if err != nil {
		return err
	}
	if !owned {
		return fmt.Errorf("VM %d does not belong to %s", vmid, instance.ID)
	}
	groups, err := db.InstanceGroups(ctx, s.Pool, []string{instance.ID})
	if err != nil {
		return err
	}
	ids := []string{}
	for _, group := range groups[instance.ID] {
		ids = append(ids, group.GroupID)
	}
	current, err := s.PVE.FirewallRules(ctx, vmid)
	if err != nil {
		return err
	}
	if len(ids) == 0 {
		// Unfiltered, as every instance was before security groups. Turned off
		// before the rules go, so there is no moment with a policy and no rules.
		if err := s.PVE.SetFirewallOptions(ctx, vmid, url.Values{"enable": {"0"}}); err != nil {
			return err
		}
		return s.replaceRules(ctx, vmid, current, nil)
	}
	rules, err := db.RulesOfGroups(ctx, s.Pool, ids)
	if err != nil {
		return err
	}
	// Rules and the address first, so that turning the firewall on never
	// starts from an empty rule list.
	if err := s.replaceRules(ctx, vmid, current, renderFirewall(rules)); err != nil {
		return err
	}
	if err := s.pinAddress(ctx, vmid, instance.IPAddress); err != nil {
		return err
	}
	return s.setFilteredOptions(ctx, vmid)
}

// replaceRules makes the VM's rules exactly desired.
func (s *Service) replaceRules(ctx context.Context, vmid int, current, desired []proxmox.FirewallRule) error {
	if sameRules(current, desired) {
		return nil
	}
	// Proxmox puts a rule posted without a position at the top (measured), so
	// posting in reverse leaves the new rules in order, above the old ones.
	// Allowing both for a moment is better than a gap where nothing is.
	for i := len(desired) - 1; i >= 0; i-- {
		if err := s.PVE.InsertFirewallRule(ctx, vmid, desired[i]); err != nil {
			return fmt.Errorf("add rule: %w", err)
		}
	}
	for i := len(current) - 1; i >= 0; i-- {
		if err := s.PVE.DeleteFirewallRule(ctx, vmid, len(desired)+current[i].Pos); err != nil {
			return fmt.Errorf("remove old rule: %w", err)
		}
	}
	return nil
}

// pinAddress makes ipfilterSet hold exactly the instance's address.
func (s *Service) pinAddress(ctx context.Context, vmid int, prefix string) error {
	address := strings.SplitN(prefix, "/", 2)[0]
	if address == "" {
		return errors.New("the instance has no address yet")
	}
	sets, err := s.PVE.IPSets(ctx, vmid)
	if err != nil {
		return err
	}
	if !slices.Contains(sets, ipfilterSet) {
		if err := s.PVE.CreateIPSet(ctx, vmid, ipfilterSet); err != nil {
			return err
		}
	}
	entries, err := s.PVE.IPSetEntries(ctx, vmid, ipfilterSet)
	if err != nil {
		return err
	}
	have := false
	for _, entry := range entries {
		if strings.TrimSuffix(entry, "/32") == address {
			have = true
			continue
		}
		if err := s.PVE.DeleteIPSetEntry(ctx, vmid, ipfilterSet, entry); err != nil {
			return err
		}
	}
	if have {
		return nil
	}
	return s.PVE.AddIPSetEntry(ctx, vmid, ipfilterSet, address)
}

// setFilteredOptions writes the filtering options every instance with groups
// gets. It writes them even when the values already match, because Proxmox
// rebuilds a running VM's live ruleset when the options are written: a
// rules-only change -- the usual shape once the first group is applied and
// enable/policies stay put -- can otherwise leave the host enforcing the
// previous, more permissive ruleset. Measured on 2026-09-11: after a
// rules-only write the port that should have been blocked was still reachable,
// and writing the same options again made it block. One extra call per write
// is cheap next to a firewall that silently is not there.
func (s *Service) setFilteredOptions(ctx context.Context, vmid int) error {
	params := url.Values{}
	for key, value := range filteredOptions {
		params.Set(key, value)
	}
	return s.PVE.SetFirewallOptions(ctx, vmid, params)
}

// workFirewallOnce writes one instance's firewall that is behind its groups.
func (s *Service) workFirewallOnce(ctx context.Context) bool {
	instance, err := db.ClaimFirewallWork(ctx, s.Pool, 5*time.Minute)
	if errors.Is(err, db.ErrNotFound) {
		return false
	}
	if err != nil {
		if ctx.Err() == nil {
			s.Log.Error("claiming firewall work failed", "err", err)
		}
		return false
	}
	log := s.Log.With("instance_id", instance.ID, "firewall_generation", instance.FirewallGeneration)
	stepCtx, cancel := context.WithTimeout(ctx, 4*time.Minute)
	defer cancel()
	if err := s.applyFirewall(stepCtx, instance); err != nil {
		if ctx.Err() != nil {
			return true
		}
		log.Warn("writing the firewall failed", "err", err)
		if err := db.FirewallRetryLater(ctx, s.Pool, instance.ID, truncate(err.Error(), 500), s.now().Add(30*time.Second)); err != nil {
			log.Error("scheduling a firewall retry failed", "err", err)
		}
		return true
	}
	if err := db.RecordFirewallApplied(ctx, s.Pool, instance.ID, instance.FirewallGeneration); err != nil {
		log.Error("recording a written firewall failed", "err", err)
		return true
	}
	log.Info("firewall written")
	return true
}
