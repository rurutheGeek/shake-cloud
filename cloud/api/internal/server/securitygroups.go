package server

import (
	"context"
	"errors"
	"net/http"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/compute"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

// Security groups. Unlike instances and volumes they are private to their
// account: a group's rules say where a VM is open, which is the owner's
// business. admins see and may change every account's.

type ruleBody struct {
	RuleID      string `json:"rule_id"`
	Protocol    string `json:"protocol"`
	FromPort    *int   `json:"from_port,omitempty"`
	ToPort      *int   `json:"to_port,omitempty"`
	CIDR        string `json:"cidr"`
	Description string `json:"description"`
}

type securityGroupBody struct {
	GroupID       string     `json:"group_id"`
	AccountID     string     `json:"account_id"`
	OwnerUsername string     `json:"owner_username,omitempty"`
	GroupName     string     `json:"group_name"`
	Description   string     `json:"description"`
	IsDefault     bool       `json:"is_default"`
	Ingress       []ruleBody `json:"ingress"`
	Egress        []ruleBody `json:"egress"`
	InstanceIDs   []string   `json:"instance_ids"`
	CreatedAt     time.Time  `json:"created_at"`
}

func (c *call) mayTouchGroup(g db.SecurityGroup) bool {
	return c.principal.account.IsAdmin || g.AccountID == c.principal.account.ID
}

// renderGroups loads the rules and instances of groups, two queries for all.
func (s *Server) renderGroups(ctx context.Context, groups []db.SecurityGroup) ([]securityGroupBody, error) {
	ids := make([]string, 0, len(groups))
	for _, g := range groups {
		ids = append(ids, g.ID)
	}
	rules, err := db.RulesOfGroups(ctx, s.pool, ids)
	if err != nil {
		return nil, err
	}
	instances, err := db.GroupInstances(ctx, s.pool, ids)
	if err != nil {
		return nil, err
	}
	bodies := make([]securityGroupBody, len(groups))
	index := map[string]int{}
	for i, g := range groups {
		index[g.ID] = i
		bodies[i] = securityGroupBody{
			GroupID: g.ID, AccountID: g.AccountID, OwnerUsername: g.OwnerUsername, GroupName: g.Name,
			Description: g.Description, IsDefault: g.IsDefault, Ingress: []ruleBody{}, Egress: []ruleBody{},
			InstanceIDs: instances[g.ID], CreatedAt: g.CreatedAt.UTC(),
		}
		if bodies[i].InstanceIDs == nil {
			bodies[i].InstanceIDs = []string{}
		}
	}
	for _, rule := range rules {
		body := &bodies[index[rule.GroupID]]
		entry := ruleBody{RuleID: rule.ID, Protocol: rule.Protocol, FromPort: rule.FromPort, ToPort: rule.ToPort,
			CIDR: rule.CIDR.String(), Description: rule.Description}
		if rule.Direction == db.DirectionIngress {
			body.Ingress = append(body.Ingress, entry)
		} else {
			body.Egress = append(body.Egress, entry)
		}
	}
	return bodies, nil
}

func (s *Server) writeGroup(w http.ResponseWriter, r *http.Request, status int, group db.SecurityGroup) {
	bodies, err := s.renderGroups(r.Context(), []db.SecurityGroup{group})
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, status, map[string]any{"security_group": bodies[0]})
}

// groupRefused records a refused group request and writes the error.
func (s *Server) groupRefused(w http.ResponseWriter, r *http.Request, c *call, id string, err error) {
	if refusal := (*compute.Error)(nil); errors.As(err, &refusal) {
		event := c.event(refusal.Code, nil)
		event.ResourceID = id
		s.recordDenied(r.Context(), event)
	}
	s.computeError(w, r, err)
}

func groupAudit(r *http.Request, c *call, tx pgx.Tx, g db.SecurityGroup, detail map[string]any) error {
	if detail == nil {
		detail = map[string]any{}
	}
	detail["owner_account_id"] = g.AccountID
	detail["group_name"] = g.Name
	event := c.event("", detail)
	event.ResourceID = g.ID
	return db.RecordAudit(r.Context(), tx, event)
}

func (s *Server) describeSecurityGroups(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	account := c.principal.account
	// Created on first sight, so the group an instance gets by default is
	// visible before the first launch.
	if _, err := service.EnsureDefaultSecurityGroup(r.Context(), s.pool, account.ID); err != nil {
		s.internalError(w, r, err)
		return
	}
	scope := account.ID
	if account.IsAdmin {
		scope = ""
	}
	groups, err := db.ListSecurityGroups(r.Context(), s.pool, scope)
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	bodies, err := s.renderGroups(r.Context(), groups)
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"security_groups": bodies})
}

func (s *Server) describeSecurityGroup(w http.ResponseWriter, r *http.Request, c *call) {
	if s.computeService(w, r) == nil {
		return
	}
	id := r.PathValue("group_id")
	group, err := db.GetSecurityGroup(r.Context(), s.pool, id)
	if errors.Is(err, db.ErrNotFound) || (err == nil && !c.mayTouchGroup(group)) {
		writeError(w, r, http.StatusNotFound, "InvalidGroup.NotFound", "security group "+id+" does not exist")
		return
	}
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	s.writeGroup(w, r, http.StatusOK, group)
}

func (s *Server) createSecurityGroup(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	var request struct {
		GroupName   string `json:"group_name"`
		Description string `json:"description"`
	}
	if !decodeJSON(w, r, &request) {
		return
	}
	group, err := service.CreateSecurityGroup(r.Context(), c.principal.account.ID, request.GroupName, request.Description,
		func(tx pgx.Tx, g db.SecurityGroup) error { return groupAudit(r, c, tx, g, nil) })
	if err != nil {
		s.groupRefused(w, r, c, "", err)
		return
	}
	s.writeGroup(w, r, http.StatusCreated, group)
}

func (s *Server) deleteSecurityGroup(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	id := r.PathValue("group_id")
	err := service.DeleteSecurityGroup(r.Context(), id, c.mayTouchGroup,
		func(tx pgx.Tx, g db.SecurityGroup) error { return groupAudit(r, c, tx, g, nil) })
	if err != nil {
		s.groupRefused(w, r, c, id, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// authorizeRules handles ingress and egress, which differ only in direction.
func authorizeRules(direction string) func(*Server, http.ResponseWriter, *http.Request, *call) {
	return func(s *Server, w http.ResponseWriter, r *http.Request, c *call) {
		service := s.computeService(w, r)
		if service == nil {
			return
		}
		id := r.PathValue("group_id")
		var request struct {
			Rules []compute.RuleRequest `json:"rules"`
		}
		if !decodeJSON(w, r, &request) {
			return
		}
		group, err := service.AuthorizeRules(r.Context(), id, direction, request.Rules, c.mayTouchGroup,
			func(tx pgx.Tx, g db.SecurityGroup, rules []db.SecurityGroupRule) error {
				added := make([]map[string]any, 0, len(rules))
				for _, rule := range rules {
					added = append(added, map[string]any{"rule_id": rule.ID, "protocol": rule.Protocol,
						"from_port": rule.FromPort, "to_port": rule.ToPort, "cidr": rule.CIDR.String()})
				}
				return groupAudit(r, c, tx, g, map[string]any{"rules": added})
			})
		if err != nil {
			s.groupRefused(w, r, c, id, err)
			return
		}
		s.writeGroup(w, r, http.StatusOK, group)
	}
}

func (s *Server) revokeSecurityGroupRule(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	id, ruleID := r.PathValue("group_id"), r.PathValue("rule_id")
	group, err := service.RevokeRule(r.Context(), id, ruleID, c.mayTouchGroup,
		func(tx pgx.Tx, g db.SecurityGroup) error {
			return groupAudit(r, c, tx, g, map[string]any{"rule_id": ruleID})
		})
	if err != nil {
		s.groupRefused(w, r, c, id, err)
		return
	}
	s.writeGroup(w, r, http.StatusOK, group)
}

func (s *Server) modifyInstanceSecurityGroups(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	id := r.PathValue("instance_id")
	if !s.mayAct(w, r, c, id) {
		return
	}
	var request struct {
		SecurityGroupIDs []string `json:"security_group_ids"`
	}
	if !decodeJSON(w, r, &request) {
		return
	}
	instance, err := service.SetInstanceSecurityGroups(r.Context(), id, request.SecurityGroupIDs, c.mayTouch,
		func(tx pgx.Tx, i db.Instance) error {
			event := c.event("", map[string]any{"owner_account_id": i.AccountID, "security_group_ids": request.SecurityGroupIDs})
			event.ResourceID = i.ID
			return db.RecordAudit(r.Context(), tx, event)
		})
	if err != nil {
		s.groupRefused(w, r, c, id, err)
		return
	}
	s.writeInstance(w, r, http.StatusOK, service, instance, true)
}
