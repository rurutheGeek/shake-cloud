package compute

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"net/http"
	"net/netip"
	"regexp"
	"slices"
	"strings"
	"unicode/utf8"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

// Security groups: named rule sets an account attaches to its instances.
// firewall.go renders them into each instance's VM firewall.

const (
	maxGroupsPerInstance = 5
	maxRulesPerDirection = 60
	maxGroupsPerAccount  = 20
	defaultGroupName     = "default"
)

var groupName = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9 ._:@-]{0,63}$`)

// RuleRequest is one rule as a caller sends it.
type RuleRequest struct {
	Protocol    string `json:"protocol"`
	FromPort    *int   `json:"from_port"`
	ToPort      *int   `json:"to_port"`
	CIDR        string `json:"cidr"`
	Description string `json:"description"`
}

func newGroupID() string { return "sg-" + randomHex17() }
func newRuleID() string  { return "sgr-" + randomHex17() }

func randomHex17() string {
	b := make([]byte, 9)
	rand.Read(b)
	return hex.EncodeToString(b)[:17]
}

func groupNotFound(id string) error {
	return refuse(http.StatusNotFound, "InvalidGroup.NotFound", "security group %s does not exist", id)
}

// allTraffic allows everything in one direction, for IPv4 and IPv6.
func allTraffic(direction string) []db.SecurityGroupRule {
	rules := []db.SecurityGroupRule{}
	for _, cidr := range []string{"0.0.0.0/0", "::/0"} {
		rules = append(rules, db.SecurityGroupRule{
			ID: newRuleID(), Direction: direction, Protocol: "all", CIDR: netip.MustParsePrefix(cidr),
		})
	}
	return rules
}

// EnsureDefaultSecurityGroup returns the account's default group, creating it
// the first time. It allows all traffic, so an instance launched without
// choosing a group is reachable as instances were before groups existed; an
// account that wants less makes a group of its own.
func (s *Service) EnsureDefaultSecurityGroup(ctx context.Context, q db.Querier, accountID string) (db.SecurityGroup, error) {
	group, _, err := db.EnsureDefaultSecurityGroup(ctx, q,
		db.SecurityGroup{ID: newGroupID(), AccountID: accountID, Name: defaultGroupName, Description: "default group: allows all traffic"},
		append(allTraffic(db.DirectionIngress), allTraffic(db.DirectionEgress)...))
	return group, err
}

func (s *Service) CreateSecurityGroup(ctx context.Context, accountID, name, description string, audit func(pgx.Tx, db.SecurityGroup) error) (db.SecurityGroup, error) {
	switch {
	case !groupName.MatchString(name):
		return db.SecurityGroup{}, refuse(http.StatusBadRequest, "InvalidParameterValue",
			"group_name must be 1-64 characters of letters, digits, space or . _ : @ -")
	case strings.EqualFold(name, defaultGroupName):
		return db.SecurityGroup{}, refuse(http.StatusBadRequest, "InvalidParameterValue", "the name default is reserved")
	case !utf8.ValidString(description) || utf8.RuneCountInString(description) > 255:
		return db.SecurityGroup{}, refuse(http.StatusBadRequest, "InvalidParameterValue", "description must be at most 255 characters")
	}
	var group db.SecurityGroup
	err := pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		if err := db.LockCapacity(ctx, tx); err != nil {
			return err
		}
		if _, err := s.EnsureDefaultSecurityGroup(ctx, tx, accountID); err != nil {
			return err
		}
		count, err := db.CountSecurityGroups(ctx, tx, accountID)
		if err != nil {
			return err
		}
		if count >= maxGroupsPerAccount {
			return refuse(http.StatusConflict, "SecurityGroupLimitExceeded", "an account may have %d security groups", maxGroupsPerAccount)
		}
		group, err = db.InsertSecurityGroup(ctx, tx, db.SecurityGroup{ID: newGroupID(), AccountID: accountID, Name: name, Description: description})
		if errors.Is(err, db.ErrDuplicate) {
			return refuse(http.StatusConflict, "InvalidGroup.Duplicate", "you already have a security group called %s", name)
		}
		if err != nil {
			return err
		}
		// A new group allows all egress and no ingress, as in EC2.
		egress := allTraffic(db.DirectionEgress)
		for i := range egress {
			egress[i].GroupID = group.ID
		}
		if err := db.InsertSecurityGroupRules(ctx, tx, egress); err != nil {
			return err
		}
		if audit != nil {
			return audit(tx, group)
		}
		return nil
	})
	return group, err
}

func (s *Service) DeleteSecurityGroup(ctx context.Context, id string, authorize func(db.SecurityGroup) bool, audit func(pgx.Tx, db.SecurityGroup) error) error {
	return pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		group, err := db.LockSecurityGroup(ctx, tx, id)
		if errors.Is(err, db.ErrNotFound) || (err == nil && !authorize(group)) {
			return groupNotFound(id)
		}
		if err != nil {
			return err
		}
		if group.IsDefault {
			return refuse(http.StatusConflict, "CannotDelete", "the default security group cannot be deleted")
		}
		using, err := db.GroupInstances(ctx, tx, []string{id})
		if err != nil {
			return err
		}
		if len(using[id]) > 0 {
			return refuse(http.StatusConflict, "DependencyViolation", "security group %s is used by %s", id, strings.Join(using[id], ", "))
		}
		if err := db.DeleteSecurityGroup(ctx, tx, id); err != nil {
			return err
		}
		if audit != nil {
			return audit(tx, group)
		}
		return nil
	})
}

// validateRules checks rules and turns them into rows of one group.
func validateRules(groupID, direction string, requests []RuleRequest) ([]db.SecurityGroupRule, error) {
	bad := func(format string, args ...any) error {
		return refuse(http.StatusBadRequest, "InvalidParameterValue", format, args...)
	}
	if len(requests) == 0 {
		return nil, bad("rules must not be empty")
	}
	rules := make([]db.SecurityGroupRule, 0, len(requests))
	for i, r := range requests {
		prefix, err := netip.ParsePrefix(r.CIDR)
		if err != nil {
			return nil, bad("rules[%d].cidr %q is not a CIDR such as 192.168.10.0/24", i, r.CIDR)
		}
		if prefix.Masked() != prefix {
			return nil, bad("rules[%d].cidr %q has host bits set; did you mean %s?", i, r.CIDR, prefix.Masked())
		}
		switch r.Protocol {
		case "tcp", "udp":
			if r.FromPort == nil || r.ToPort == nil {
				return nil, bad("rules[%d]: %s needs from_port and to_port", i, r.Protocol)
			}
			if *r.FromPort < 0 || *r.ToPort > 65535 || *r.FromPort > *r.ToPort {
				return nil, bad("rules[%d]: ports must satisfy 0 <= from_port <= to_port <= 65535", i)
			}
		case "icmp", "icmpv6", "all":
			if r.FromPort != nil || r.ToPort != nil {
				return nil, bad("rules[%d]: %s takes no ports", i, r.Protocol)
			}
		default:
			return nil, bad("rules[%d].protocol must be tcp, udp, icmp, icmpv6 or all", i)
		}
		switch {
		case r.Protocol == "icmp" && !prefix.Addr().Is4():
			return nil, bad("rules[%d]: icmp is IPv4; use icmpv6 for %s", i, r.CIDR)
		case r.Protocol == "icmpv6" && prefix.Addr().Is4():
			return nil, bad("rules[%d]: icmpv6 is IPv6; use icmp for %s", i, r.CIDR)
		case !utf8.ValidString(r.Description) || utf8.RuneCountInString(r.Description) > 255:
			return nil, bad("rules[%d].description must be at most 255 characters", i)
		}
		rules = append(rules, db.SecurityGroupRule{
			ID: newRuleID(), GroupID: groupID, Direction: direction, Protocol: r.Protocol,
			FromPort: r.FromPort, ToPort: r.ToPort, CIDR: prefix, Description: r.Description,
		})
	}
	return rules, nil
}

// AuthorizeRules adds rules to a group in one direction, and marks every
// instance using the group as needing its firewall written.
func (s *Service) AuthorizeRules(ctx context.Context, id, direction string, requests []RuleRequest, authorize func(db.SecurityGroup) bool, audit func(pgx.Tx, db.SecurityGroup, []db.SecurityGroupRule) error) (db.SecurityGroup, error) {
	rules, err := validateRules(id, direction, requests)
	if err != nil {
		return db.SecurityGroup{}, err
	}
	var group db.SecurityGroup
	err = pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		group, err = db.LockSecurityGroup(ctx, tx, id)
		if errors.Is(err, db.ErrNotFound) || (err == nil && !authorize(group)) {
			return groupNotFound(id)
		}
		if err != nil {
			return err
		}
		count, err := db.CountRules(ctx, tx, id, direction)
		if err != nil {
			return err
		}
		if count+len(rules) > maxRulesPerDirection {
			return refuse(http.StatusConflict, "RulesPerSecurityGroupLimitExceeded",
				"a security group may have %d %s rules; it has %d", maxRulesPerDirection, direction, count)
		}
		if err := db.InsertSecurityGroupRules(ctx, tx, rules); errors.Is(err, db.ErrDuplicate) {
			return refuse(http.StatusConflict, "InvalidPermission.Duplicate", "security group %s already has one of these rules", id)
		} else if err != nil {
			return err
		}
		if err := db.BumpFirewallOfGroup(ctx, tx, id); err != nil {
			return err
		}
		if audit != nil {
			return audit(tx, group, rules)
		}
		return nil
	})
	if err == nil {
		s.Wake()
	}
	return group, err
}

func (s *Service) RevokeRule(ctx context.Context, id, ruleID string, authorize func(db.SecurityGroup) bool, audit func(pgx.Tx, db.SecurityGroup) error) (db.SecurityGroup, error) {
	var group db.SecurityGroup
	err := pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		var err error
		group, err = db.LockSecurityGroup(ctx, tx, id)
		if errors.Is(err, db.ErrNotFound) || (err == nil && !authorize(group)) {
			return groupNotFound(id)
		}
		if err != nil {
			return err
		}
		if err := db.DeleteSecurityGroupRule(ctx, tx, id, ruleID); errors.Is(err, db.ErrNotFound) {
			return refuse(http.StatusNotFound, "InvalidPermission.NotFound", "security group %s has no rule %s", id, ruleID)
		} else if err != nil {
			return err
		}
		if err := db.BumpFirewallOfGroup(ctx, tx, id); err != nil {
			return err
		}
		if audit != nil {
			return audit(tx, group)
		}
		return nil
	})
	if err == nil {
		s.Wake()
	}
	return group, err
}

// resolveGroups checks that groupIDs are 1-5 groups of accountID and locks
// them, so none can be deleted before the caller's transaction ends. An empty
// list means the account's default group.
func (s *Service) resolveGroups(ctx context.Context, tx pgx.Tx, accountID string, groupIDs []string) ([]string, error) {
	if len(groupIDs) == 0 {
		group, err := s.EnsureDefaultSecurityGroup(ctx, tx, accountID)
		if err != nil {
			return nil, err
		}
		return []string{group.ID}, nil
	}
	ids := []string{}
	for _, id := range groupIDs {
		if !slices.Contains(ids, id) {
			ids = append(ids, id)
		}
	}
	if len(ids) > maxGroupsPerInstance {
		return nil, refuse(http.StatusConflict, "SecurityGroupsPerInstanceLimitExceeded", "an instance may have %d security groups", maxGroupsPerInstance)
	}
	slices.Sort(ids)
	for _, id := range ids {
		group, err := db.LockSecurityGroup(ctx, tx, id)
		if errors.Is(err, db.ErrNotFound) || (err == nil && group.AccountID != accountID) {
			return nil, refuse(http.StatusBadRequest, "InvalidGroup.NotFound", "security group %s does not exist in the instance's account", id)
		}
		if err != nil {
			return nil, err
		}
	}
	return ids, nil
}

// SetInstanceSecurityGroups replaces the groups of an instance.
func (s *Service) SetInstanceSecurityGroups(ctx context.Context, instanceID string, groupIDs []string, authorize func(db.Instance) bool, audit func(pgx.Tx, db.Instance) error) (db.Instance, error) {
	if len(groupIDs) == 0 {
		return db.Instance{}, refuse(http.StatusBadRequest, "InvalidParameterValue", "security_group_ids must name at least one group")
	}
	var result db.Instance
	err := pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		instance, err := db.LockInstance(ctx, tx, instanceID)
		if errors.Is(err, db.ErrNotFound) || (err == nil && !authorize(instance)) {
			return refuse(http.StatusNotFound, "InvalidInstanceID.NotFound", "instance %s does not exist", instanceID)
		}
		if err != nil {
			return err
		}
		if instance.State == db.StateTerminated || instance.State == db.StateShuttingDown {
			return refuse(http.StatusConflict, "IncorrectInstanceState", "instance %s is %s", instanceID, describeState(instance))
		}
		ids, err := s.resolveGroups(ctx, tx, instance.AccountID, groupIDs)
		if err != nil {
			return err
		}
		if err := db.SetInstanceGroups(ctx, tx, instanceID, ids); err != nil {
			return err
		}
		if result, err = db.GetInstance(ctx, tx, instanceID); err != nil {
			return err
		}
		if audit != nil {
			return audit(tx, result)
		}
		return nil
	})
	if err == nil {
		s.Wake()
	}
	return result, err
}
