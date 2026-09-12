package db

import (
	"context"
	"errors"
	"net/netip"
	"time"

	"github.com/jackc/pgx/v5"
)

// Rule directions, in EC2's words.
const (
	DirectionIngress = "ingress"
	DirectionEgress  = "egress"
)

// ErrDuplicate means a unique name or an identical rule already exists.
var ErrDuplicate = errors.New("already exists")

type SecurityGroup struct {
	ID            string
	AccountID     string
	OwnerUsername string
	Name          string
	Description   string
	// IsDefault marks the group every account has, which instances get when
	// they are launched without naming one.
	IsDefault bool
	CreatedAt time.Time
	UpdatedAt time.Time
}

type SecurityGroupRule struct {
	ID        string
	GroupID   string
	Direction string
	Protocol  string
	// FromPort and ToPort are set for tcp and udp only.
	FromPort    *int
	ToPort      *int
	CIDR        netip.Prefix
	Description string
	CreatedAt   time.Time
}

// GroupRef names a group attached to an instance.
type GroupRef struct {
	GroupID   string
	GroupName string
}

const groupColumns = `g.group_id, g.account_id,
	coalesce((SELECT a.username FROM accounts a WHERE a.id = g.account_id), ''),
	g.group_name, g.description, g.is_default, g.created_at, g.updated_at`

func scanGroup(row pgx.Row) (SecurityGroup, error) {
	var g SecurityGroup
	err := row.Scan(&g.ID, &g.AccountID, &g.OwnerUsername, &g.Name, &g.Description, &g.IsDefault, &g.CreatedAt, &g.UpdatedAt)
	return g, noRows(err)
}

func InsertSecurityGroup(ctx context.Context, q Querier, g SecurityGroup) (SecurityGroup, error) {
	created, err := scanGroup(q.QueryRow(ctx, `INSERT INTO security_groups AS g (group_id, account_id, group_name, description)
		VALUES ($1, $2, $3, $4) RETURNING `+groupColumns, g.ID, g.AccountID, g.Name, g.Description))
	if isUniqueViolation(err, "security_groups_account_id_group_name_key") {
		return SecurityGroup{}, ErrDuplicate
	}
	return created, err
}

// EnsureDefaultSecurityGroup returns the account's default group, creating it
// with rules when it does not exist yet. created reports whether it did.
func EnsureDefaultSecurityGroup(ctx context.Context, q Querier, g SecurityGroup, rules []SecurityGroupRule) (SecurityGroup, bool, error) {
	inserted, err := scanGroup(q.QueryRow(ctx, `INSERT INTO security_groups AS g (group_id, account_id, group_name, description, is_default)
		VALUES ($1, $2, $3, $4, true) ON CONFLICT DO NOTHING RETURNING `+groupColumns, g.ID, g.AccountID, g.Name, g.Description))
	if errors.Is(err, ErrNotFound) {
		existing, err := scanGroup(q.QueryRow(ctx, `SELECT `+groupColumns+` FROM security_groups g
			WHERE g.account_id = $1 AND g.is_default`, g.AccountID))
		return existing, false, err
	}
	if err != nil {
		return SecurityGroup{}, false, err
	}
	for i := range rules {
		rules[i].GroupID = inserted.ID
	}
	return inserted, true, InsertSecurityGroupRules(ctx, q, rules)
}

func GetSecurityGroup(ctx context.Context, q Querier, id string) (SecurityGroup, error) {
	return scanGroup(q.QueryRow(ctx, `SELECT `+groupColumns+` FROM security_groups g WHERE g.group_id = $1`, id))
}

// LockSecurityGroup holds the group's row, so rule changes to one group are
// serialised and a group cannot be deleted while something attaches it.
func LockSecurityGroup(ctx context.Context, q Querier, id string) (SecurityGroup, error) {
	return scanGroup(q.QueryRow(ctx, `SELECT `+groupColumns+` FROM security_groups g WHERE g.group_id = $1 FOR UPDATE`, id))
}

// ListSecurityGroups returns one account's groups, or every account's when
// accountID is empty; default groups first.
func ListSecurityGroups(ctx context.Context, q Querier, accountID string) ([]SecurityGroup, error) {
	rows, err := q.Query(ctx, `SELECT `+groupColumns+` FROM security_groups g
		WHERE ($1::text = '' OR g.account_id = $1)
		ORDER BY g.account_id, g.is_default DESC, g.created_at, g.group_id`, accountID)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (SecurityGroup, error) { return scanGroup(row) })
}

func CountSecurityGroups(ctx context.Context, q Querier, accountID string) (int, error) {
	var count int
	err := q.QueryRow(ctx, `SELECT count(*) FROM security_groups WHERE account_id = $1`, accountID).Scan(&count)
	return count, err
}

// DeleteSecurityGroup removes a group and its rules. Terminated instances keep
// their membership rows as a record until then; they go with the group.
func DeleteSecurityGroup(ctx context.Context, q Querier, id string) error {
	if _, err := q.Exec(ctx, `DELETE FROM instance_security_groups
		WHERE group_id = $1 AND instance_id IN (SELECT instance_id FROM instances WHERE state = 'terminated')`, id); err != nil {
		return err
	}
	tag, err := q.Exec(ctx, `DELETE FROM security_groups WHERE group_id = $1`, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

// RulesOfGroups returns the rules of the given groups in a stable order, which
// is also the order they are written to a VM.
func RulesOfGroups(ctx context.Context, q Querier, groupIDs []string) ([]SecurityGroupRule, error) {
	rows, err := q.Query(ctx, `SELECT r.rule_id, r.group_id, r.direction, r.protocol, r.from_port, r.to_port,
			r.cidr, r.description, r.created_at
		FROM security_group_rules r WHERE r.group_id = ANY($1::text[])
		ORDER BY r.group_id, r.direction DESC, r.created_at, r.rule_id`, groupIDs)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (SecurityGroupRule, error) {
		var r SecurityGroupRule
		err := row.Scan(&r.ID, &r.GroupID, &r.Direction, &r.Protocol, &r.FromPort, &r.ToPort, &r.CIDR, &r.Description, &r.CreatedAt)
		return r, err
	})
}

// InsertSecurityGroupRules adds rules; a rule identical to an existing one in
// the same group is ErrDuplicate and nothing is added.
func InsertSecurityGroupRules(ctx context.Context, q Querier, rules []SecurityGroupRule) error {
	for _, r := range rules {
		_, err := q.Exec(ctx, `INSERT INTO security_group_rules
			(rule_id, group_id, direction, protocol, from_port, to_port, cidr, description)
			VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
			r.ID, r.GroupID, r.Direction, r.Protocol, r.FromPort, r.ToPort, r.CIDR, r.Description)
		if isUniqueViolation(err, "security_group_rules_unique") {
			return ErrDuplicate
		}
		if err != nil {
			return err
		}
	}
	_, err := q.Exec(ctx, `UPDATE security_groups SET updated_at = now()
		WHERE group_id IN (SELECT DISTINCT unnest($1::text[]))`, groupIDsOf(rules))
	return err
}

func groupIDsOf(rules []SecurityGroupRule) []string {
	ids := make([]string, 0, len(rules))
	for _, r := range rules {
		ids = append(ids, r.GroupID)
	}
	return ids
}

func DeleteSecurityGroupRule(ctx context.Context, q Querier, groupID, ruleID string) error {
	tag, err := q.Exec(ctx, `DELETE FROM security_group_rules WHERE group_id = $1 AND rule_id = $2`, groupID, ruleID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	_, err = q.Exec(ctx, `UPDATE security_groups SET updated_at = now() WHERE group_id = $1`, groupID)
	return err
}

func CountRules(ctx context.Context, q Querier, groupID, direction string) (int, error) {
	var count int
	err := q.QueryRow(ctx, `SELECT count(*) FROM security_group_rules WHERE group_id = $1 AND direction = $2`,
		groupID, direction).Scan(&count)
	return count, err
}

// InstanceGroups returns the groups attached to each of the given instances.
func InstanceGroups(ctx context.Context, q Querier, instanceIDs []string) (map[string][]GroupRef, error) {
	rows, err := q.Query(ctx, `SELECT m.instance_id, g.group_id, g.group_name
		FROM instance_security_groups m JOIN security_groups g ON g.group_id = m.group_id
		WHERE m.instance_id = ANY($1::text[])
		ORDER BY m.instance_id, g.is_default DESC, g.group_name`, instanceIDs)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	groups := map[string][]GroupRef{}
	for rows.Next() {
		var instanceID string
		var ref GroupRef
		if err := rows.Scan(&instanceID, &ref.GroupID, &ref.GroupName); err != nil {
			return nil, err
		}
		groups[instanceID] = append(groups[instanceID], ref)
	}
	return groups, rows.Err()
}

// GroupInstances returns the live instances each of the given groups is attached to.
func GroupInstances(ctx context.Context, q Querier, groupIDs []string) (map[string][]string, error) {
	rows, err := q.Query(ctx, `SELECT m.group_id, m.instance_id
		FROM instance_security_groups m JOIN instances i ON i.instance_id = m.instance_id
		WHERE m.group_id = ANY($1::text[]) AND i.state <> 'terminated'
		ORDER BY m.group_id, m.instance_id`, groupIDs)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	instances := map[string][]string{}
	for rows.Next() {
		var groupID, instanceID string
		if err := rows.Scan(&groupID, &instanceID); err != nil {
			return nil, err
		}
		instances[groupID] = append(instances[groupID], instanceID)
	}
	return instances, rows.Err()
}

// SetInstanceGroups replaces an instance's groups and marks its firewall as
// needing to be written again.
func SetInstanceGroups(ctx context.Context, q Querier, instanceID string, groupIDs []string) error {
	if _, err := q.Exec(ctx, `DELETE FROM instance_security_groups WHERE instance_id = $1`, instanceID); err != nil {
		return err
	}
	if _, err := q.Exec(ctx, `INSERT INTO instance_security_groups (instance_id, group_id)
		SELECT $1::text, unnest($2::text[])`, instanceID, groupIDs); err != nil {
		return err
	}
	_, err := q.Exec(ctx, `UPDATE instances SET firewall_generation = firewall_generation + 1,
		firewall_next_attempt_at = now(), updated_at = now() WHERE instance_id = $1`, instanceID)
	return err
}

// BumpFirewallOfGroup marks every live instance in a group as needing its
// firewall written again, after the group's rules changed.
func BumpFirewallOfGroup(ctx context.Context, q Querier, groupID string) error {
	_, err := q.Exec(ctx, `UPDATE instances SET firewall_generation = firewall_generation + 1,
		firewall_next_attempt_at = now()
		WHERE state <> 'terminated'
		  AND instance_id IN (SELECT instance_id FROM instance_security_groups WHERE group_id = $1)`, groupID)
	return err
}

// ClaimFirewallWork leases the next instance whose VM firewall is behind its
// groups. Launches write the firewall themselves before the first boot, and
// terminates do not need one, so instances in either are skipped.
func ClaimFirewallWork(ctx context.Context, q Querier, lease time.Duration) (Instance, error) {
	return scanInstance(q.QueryRow(ctx, `UPDATE instances AS i SET firewall_lease_until = now() + make_interval(secs => $1)
		WHERE i.instance_id = (
			SELECT instance_id FROM instances
			WHERE firewall_generation <> firewall_applied
			  AND vm_created AND vmid IS NOT NULL AND state <> 'terminated'
			  AND coalesce(pending_action, '') NOT IN ('launch', 'terminate')
			  AND firewall_next_attempt_at <= now()
			  AND (firewall_lease_until IS NULL OR firewall_lease_until < now())
			ORDER BY firewall_next_attempt_at, instance_id
			LIMIT 1 FOR UPDATE SKIP LOCKED)
		RETURNING `+instanceColumns, lease.Seconds()))
}

// RecordFirewallApplied notes that generation is what the VM now has. A later
// generation recorded by someone else is never moved backwards.
func RecordFirewallApplied(ctx context.Context, q Querier, id string, generation int64) error {
	_, err := q.Exec(ctx, `UPDATE instances SET firewall_applied = greatest(firewall_applied, $2),
		firewall_last_error = '', firewall_lease_until = NULL
		WHERE instance_id = $1`, id, generation)
	return err
}

// FirewallRetryLater records a failed write and when to try again.
func FirewallRetryLater(ctx context.Context, q Querier, id, lastError string, next time.Time) error {
	_, err := q.Exec(ctx, `UPDATE instances SET firewall_last_error = $2, firewall_next_attempt_at = $3,
		firewall_lease_until = NULL WHERE instance_id = $1`, id, lastError, next)
	return err
}
