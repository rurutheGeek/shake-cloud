package provider

import (
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

func intPtr(value int) *int { return &value }

func rule(id, protocol, cidr, description string, from, to *int) client.SecurityGroupRule {
	return client.SecurityGroupRule{
		RuleID: id, Protocol: protocol, CIDR: cidr, Description: description,
		FromPort: from, ToPort: to,
	}
}

func request(protocol, cidr, description string, from, to *int) client.SecurityGroupRuleRequest {
	return client.SecurityGroupRuleRequest{
		Protocol: protocol, CIDR: cidr, Description: description, FromPort: from, ToPort: to,
	}
}

func TestFindNewRulePicksTheMatchingRuleWhenSiblingsAppearFirst(t *testing.T) {
	// What concurrent creates look like: every Create reads the same empty
	// before snapshot, and the API returns the whole group.
	after := []client.SecurityGroupRule{
		rule("sgr-http", "tcp", "192.168.10.0/24", "HTTP", intPtr(80), intPtr(80)),
		rule("sgr-https", "tcp", "192.168.10.0/24", "HTTPS", intPtr(443), intPtr(443)),
		rule("sgr-ssh", "tcp", "192.168.10.0/24", "SSH", intPtr(22), intPtr(22)),
	}
	found, ok := findNewRule(nil, after, request("tcp", "192.168.10.0/24", "SSH", intPtr(22), intPtr(22)))
	if !ok || found.RuleID != "sgr-ssh" {
		t.Fatalf("findNewRule = %q, %v; want sgr-ssh", found.RuleID, ok)
	}
}

func TestFindNewRuleDoesNotReturnAnIdenticalRuleThatWasAlreadyThere(t *testing.T) {
	before := []client.SecurityGroupRule{
		rule("sgr-old", "tcp", "192.168.10.0/24", "SSH", intPtr(22), intPtr(22)),
	}
	after := append(append([]client.SecurityGroupRule{}, before...),
		rule("sgr-new", "tcp", "192.168.10.0/24", "SSH", intPtr(22), intPtr(22)))
	found, ok := findNewRule(before, after, request("tcp", "192.168.10.0/24", "SSH", intPtr(22), intPtr(22)))
	if !ok || found.RuleID != "sgr-new" {
		t.Fatalf("findNewRule = %q, %v; want the new duplicate", found.RuleID, ok)
	}
}

func TestFindNewRuleReportsFailureWhenNothingMatches(t *testing.T) {
	after := []client.SecurityGroupRule{
		rule("sgr-https", "tcp", "192.168.10.0/24", "HTTPS", intPtr(443), intPtr(443)),
	}
	if found, ok := findNewRule(nil, after, request("tcp", "192.168.10.0/24", "SSH", intPtr(22), intPtr(22))); ok {
		t.Fatalf("findNewRule = %q, want no match", found.RuleID)
	}
}

func TestFindNewRuleMatchesRulesWithoutPorts(t *testing.T) {
	after := []client.SecurityGroupRule{
		rule("sgr-all", "all", "0.0.0.0/0", "", nil, nil),
	}
	found, ok := findNewRule(nil, after, request("all", "0.0.0.0/0", "", nil, nil))
	if !ok || found.RuleID != "sgr-all" {
		t.Fatalf("findNewRule = %q, %v; want sgr-all", found.RuleID, ok)
	}
	if _, ok := findNewRule(nil, after, request("all", "0.0.0.0/0", "", intPtr(0), nil)); ok {
		t.Fatal("a request with a port matched a rule without ports")
	}
}
