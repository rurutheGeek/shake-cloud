package compute

import (
	"context"
	"net/netip"
	"slices"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/proxmox"
)

func allowAll(db.SecurityGroup) bool { return true }

func TestRulesRenderIntoProxmoxRules(t *testing.T) {
	rule := func(id, direction, protocol string, from, to *int, cidr string) db.SecurityGroupRule {
		return db.SecurityGroupRule{ID: id, GroupID: "sg-a", Direction: direction, Protocol: protocol,
			FromPort: from, ToPort: to, CIDR: netip.MustParsePrefix(cidr)}
	}
	got := renderFirewall([]db.SecurityGroupRule{
		rule("sgr-1", db.DirectionIngress, "tcp", ptr(22), ptr(22), "192.168.10.0/24"),
		rule("sgr-2", db.DirectionIngress, "udp", ptr(27000), ptr(27100), "0.0.0.0/0"),
		rule("sgr-3", db.DirectionIngress, "tcp", ptr(0), ptr(65535), "10.0.0.0/8"),
		rule("sgr-4", db.DirectionIngress, "icmpv6", nil, nil, "::/0"),
		rule("sgr-5", db.DirectionEgress, "all", nil, nil, "0.0.0.0/0"),
		// The same traffic from a second group is written once.
		{ID: "sgr-6", GroupID: "sg-b", Direction: db.DirectionIngress, Protocol: "tcp", FromPort: ptr(22), ToPort: ptr(22),
			CIDR: netip.MustParsePrefix("192.168.10.0/24")},
	})
	want := []proxmox.FirewallRule{
		{Type: "in", Action: "ACCEPT", Proto: "tcp", Dport: "22", Source: "192.168.10.0/24", Enable: 1, Comment: "shakecloud sg-a sgr-1"},
		{Type: "in", Action: "ACCEPT", Proto: "udp", Dport: "27000:27100", Source: "0.0.0.0/0", Enable: 1, Comment: "shakecloud sg-a sgr-2"},
		{Type: "in", Action: "ACCEPT", Proto: "tcp", Source: "10.0.0.0/8", Enable: 1, Comment: "shakecloud sg-a sgr-3"},
		{Type: "in", Action: "ACCEPT", Proto: "ipv6-icmp", Source: "::/0", Enable: 1, Comment: "shakecloud sg-a sgr-4"},
		{Type: "out", Action: "ACCEPT", Dest: "0.0.0.0/0", Enable: 1, Comment: "shakecloud sg-a sgr-5"},
	}
	if !slices.Equal(got, want) {
		t.Fatalf("rendered\n%+v\nwant\n%+v", got, want)
	}
}

func vmRules(pve *fakePVE, vmid int) []proxmox.FirewallRule {
	pve.mu.Lock()
	defer pve.mu.Unlock()
	return slices.Clone(pve.firewall(vmid).rules)
}

func TestALaunchWritesTheDefaultGroupBeforeTheFirstBoot(t *testing.T) {
	s, pve, _ := testService(t)
	alice := newAccount(t, s, "alice")
	instance := running(t, s, alice)
	vmid := *instance.VMID

	if !pve.startedFiltered[vmid] {
		t.Fatal("the VM was started before its firewall was on")
	}
	if instance.FirewallApplied != instance.FirewallGeneration || instance.FirewallGeneration == 0 {
		t.Fatalf("generation %d applied %d", instance.FirewallGeneration, instance.FirewallApplied)
	}
	rules := vmRules(pve, vmid)
	in, out := 0, 0
	for _, rule := range rules {
		if rule.Proto != "" || rule.Dport != "" {
			t.Fatalf("the default group allows everything, got %+v", rule)
		}
		switch rule.Type {
		case "in":
			in++
		case "out":
			out++
		}
	}
	if in != 2 || out != 2 {
		t.Fatalf("rules: %+v", rules)
	}
	options := pve.firewall(vmid).options
	if options["policy_in"] != "DROP" || options["ipfilter"] != "1" || options["macfilter"] != "1" {
		t.Fatalf("options %v", options)
	}
	if entries := pve.firewall(vmid).ipsets[ipfilterSet]; !slices.Equal(entries, []string{"192.168.10.100"}) {
		t.Fatalf("ipfilter-net0 = %v", entries)
	}
}

func TestAChangedGroupIsRewrittenOnEveryInstanceUsingIt(t *testing.T) {
	s, pve, _ := testService(t)
	ctx := context.Background()
	alice := newAccount(t, s, "alice")

	web, err := s.CreateSecurityGroup(ctx, alice, "web", "", nil)
	if err != nil {
		t.Fatal(err)
	}
	ssh := RuleRequest{Protocol: "tcp", FromPort: ptr(22), ToPort: ptr(22), CIDR: "192.168.10.0/24"}
	if _, err := s.AuthorizeRules(ctx, web.ID, db.DirectionIngress, []RuleRequest{ssh}, allowAll, nil); err != nil {
		t.Fatal(err)
	}
	instance := run(t, s, alice, RunRequest{ImageID: "img-debian13", InstanceType: "small", SecurityGroupIDs: []string{web.ID}})
	work(t, s, 10)
	vmid := *get(t, s, instance.ID).VMID
	// ssh in, plus the all-egress rules a new group starts with.
	if rules := vmRules(pve, vmid); len(rules) != 3 || rules[0].Dport != "22" {
		t.Fatalf("launched with %+v", rules)
	}

	game := RuleRequest{Protocol: "udp", FromPort: ptr(27000), ToPort: ptr(27100), CIDR: "0.0.0.0/0"}
	if _, err := s.AuthorizeRules(ctx, web.ID, db.DirectionIngress, []RuleRequest{game}, allowAll, nil); err != nil {
		t.Fatal(err)
	}
	if got := get(t, s, instance.ID); got.FirewallGeneration == got.FirewallApplied {
		t.Fatal("a rule change did not mark the instance")
	}
	work(t, s, 5)
	rules := vmRules(pve, vmid)
	if len(rules) != 4 {
		t.Fatalf("after adding a rule, the old ones must be gone: %+v", rules)
	}
	if got := get(t, s, instance.ID); got.FirewallGeneration != got.FirewallApplied {
		t.Fatalf("still behind: %d/%d (%s)", got.FirewallApplied, got.FirewallGeneration, got.FirewallLastError)
	}

	groups, err := db.RulesOfGroups(ctx, s.Pool, []string{web.ID})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := s.RevokeRule(ctx, web.ID, groups[0].ID, allowAll, nil); err != nil {
		t.Fatal(err)
	}
	work(t, s, 5)
	if rules := vmRules(pve, vmid); len(rules) != 3 {
		t.Fatalf("after revoking: %+v", rules)
	}

	if err := s.DeleteSecurityGroup(ctx, web.ID, allowAll, nil); code(err) != "DependencyViolation" {
		t.Fatalf("delete a group in use: %v", err)
	}
	def, err := s.EnsureDefaultSecurityGroup(ctx, s.Pool, alice)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := s.SetInstanceSecurityGroups(ctx, instance.ID, []string{def.ID}, func(db.Instance) bool { return true }, nil); err != nil {
		t.Fatal(err)
	}
	work(t, s, 5)
	if rules := vmRules(pve, vmid); len(rules) != 4 || rules[0].Proto != "" {
		t.Fatalf("after switching to default: %+v", rules)
	}
	if err := s.DeleteSecurityGroup(ctx, web.ID, allowAll, nil); err != nil {
		t.Fatalf("delete an unused group: %v", err)
	}
	if err := s.DeleteSecurityGroup(ctx, def.ID, allowAll, nil); code(err) != "CannotDelete" {
		t.Fatalf("delete the default group: %v", err)
	}
}

func TestARuleOnlyChangeRewritesTheOptionsSoProxmoxReloads(t *testing.T) {
	// Measured on the real host: a rules-only change does not make Proxmox
	// rebuild a running VM's live ruleset, but writing the options again does.
	// If setFilteredOptions skips the write when the values already match, a
	// security group can look correct in the API and in the config while the
	// host still enforces the previous rules.
	s, pve, _ := testService(t)
	ctx := context.Background()
	alice := newAccount(t, s, "alice")
	group, err := s.CreateSecurityGroup(ctx, alice, "web", "", nil)
	if err != nil {
		t.Fatal(err)
	}
	ssh := RuleRequest{Protocol: "tcp", FromPort: ptr(22), ToPort: ptr(22), CIDR: "192.168.10.0/24"}
	if _, err := s.AuthorizeRules(ctx, group.ID, db.DirectionIngress, []RuleRequest{ssh}, allowAll, nil); err != nil {
		t.Fatal(err)
	}
	instance := run(t, s, alice, RunRequest{ImageID: "img-debian13", InstanceType: "small", SecurityGroupIDs: []string{group.ID}})
	work(t, s, 10)
	vmid := *get(t, s, instance.ID).VMID
	before := pve.firewall(vmid).optionWrites

	game := RuleRequest{Protocol: "udp", FromPort: ptr(27000), ToPort: ptr(27100), CIDR: "0.0.0.0/0"}
	if _, err := s.AuthorizeRules(ctx, group.ID, db.DirectionIngress, []RuleRequest{game}, allowAll, nil); err != nil {
		t.Fatal(err)
	}
	work(t, s, 5)
	if after := pve.firewall(vmid).optionWrites; after <= before {
		t.Fatalf("a rules-only change did not rewrite the firewall options (%d -> %d); Proxmox may not reload", before, after)
	}
}

func TestGroupRequestsThatCannotWorkAreRefused(t *testing.T) {
	s, _, _ := testService(t)
	ctx := context.Background()
	alice, bob := newAccount(t, s, "alice"), newAccount(t, s, "bob")
	group, err := s.CreateSecurityGroup(ctx, alice, "web", "", nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := s.CreateSecurityGroup(ctx, alice, "web", "", nil); code(err) != "InvalidGroup.Duplicate" {
		t.Fatalf("duplicate name: %v", err)
	}
	if _, err := s.CreateSecurityGroup(ctx, alice, "Default", "", nil); code(err) != "InvalidParameterValue" {
		t.Fatalf("reserved name: %v", err)
	}
	for name, rule := range map[string]RuleRequest{
		"host bits":      {Protocol: "tcp", FromPort: ptr(22), ToPort: ptr(22), CIDR: "192.168.10.5/24"},
		"no ports":       {Protocol: "tcp", CIDR: "0.0.0.0/0"},
		"ports on all":   {Protocol: "all", FromPort: ptr(1), ToPort: ptr(2), CIDR: "0.0.0.0/0"},
		"icmp over IPv6": {Protocol: "icmp", CIDR: "::/0"},
		"backwards":      {Protocol: "udp", FromPort: ptr(9), ToPort: ptr(8), CIDR: "0.0.0.0/0"},
		"protocol":       {Protocol: "sctp", CIDR: "0.0.0.0/0"},
	} {
		if _, err := s.AuthorizeRules(ctx, group.ID, db.DirectionIngress, []RuleRequest{rule}, allowAll, nil); code(err) != "InvalidParameterValue" {
			t.Fatalf("%s: %v", name, err)
		}
	}
	ssh := RuleRequest{Protocol: "tcp", FromPort: ptr(22), ToPort: ptr(22), CIDR: "0.0.0.0/0"}
	if _, err := s.AuthorizeRules(ctx, group.ID, db.DirectionIngress, []RuleRequest{ssh}, allowAll, nil); err != nil {
		t.Fatal(err)
	}
	if _, err := s.AuthorizeRules(ctx, group.ID, db.DirectionIngress, []RuleRequest{ssh}, allowAll, nil); code(err) != "InvalidPermission.Duplicate" {
		t.Fatalf("duplicate rule: %v", err)
	}
	if _, _, err := s.Run(ctx, bob, RunRequest{ImageID: "img-debian13", InstanceType: "small", SecurityGroupIDs: []string{group.ID}}, nil); code(err) != "InvalidGroup.NotFound" {
		t.Fatalf("someone else's group: %v", err)
	}
	many := []string{}
	for range 6 {
		many = append(many, newGroupID())
	}
	if _, _, err := s.Run(ctx, alice, RunRequest{ImageID: "img-debian13", InstanceType: "small", SecurityGroupIDs: many}, nil); code(err) != "SecurityGroupsPerInstanceLimitExceeded" {
		t.Fatalf("too many groups: %v", err)
	}
}
