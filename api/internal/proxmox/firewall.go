package proxmox

import (
	"context"
	"net/http"
	"net/url"
	"sort"
	"strconv"
)

// FirewallRule is one per-VM firewall rule. Enable has no omitempty because
// Proxmox always reports it, and 0 (disabled) is a meaningful value to send.
type FirewallRule struct {
	Pos     int    `json:"pos"`
	Type    string `json:"type"`
	Action  string `json:"action"`
	Proto   string `json:"proto,omitempty"`
	Dport   string `json:"dport,omitempty"`
	Source  string `json:"source,omitempty"`
	Dest    string `json:"dest,omitempty"`
	Enable  int    `json:"enable"`
	Comment string `json:"comment,omitempty"`
}

// FirewallRules returns the VM's rules ordered by position, the order
// Proxmox applies them in. The API itself does not promise an order.
func (c *Client) FirewallRules(ctx context.Context, vmid int) ([]FirewallRule, error) {
	var rules []FirewallRule
	if err := c.form(ctx, http.MethodGet, c.nodePath("/qemu/%d/firewall/rules", vmid), nil, &rules); err != nil {
		return nil, err
	}
	sort.Slice(rules, func(i, j int) bool { return rules[i].Pos < rules[j].Pos })
	return rules, nil
}

// InsertFirewallRule adds one rule. Proxmox does not take a pos on insert,
// and measured on the real host (PVE 9.2.2, 2026-09-11) it always lands the
// new rule at position 0 — the top, not the end — so a caller building an
// ordered list r1..rn must post them in reverse. Only fields the caller set
// are sent; Enable is always sent since 0 is meaningful.
func (c *Client) InsertFirewallRule(ctx context.Context, vmid int, rule FirewallRule) error {
	params := url.Values{}
	if rule.Type != "" {
		params.Set("type", rule.Type)
	}
	if rule.Action != "" {
		params.Set("action", rule.Action)
	}
	if rule.Proto != "" {
		params.Set("proto", rule.Proto)
	}
	if rule.Dport != "" {
		params.Set("dport", rule.Dport)
	}
	if rule.Source != "" {
		params.Set("source", rule.Source)
	}
	if rule.Dest != "" {
		params.Set("dest", rule.Dest)
	}
	if rule.Comment != "" {
		params.Set("comment", rule.Comment)
	}
	params.Set("enable", strconv.Itoa(rule.Enable))
	return c.form(ctx, http.MethodPost, c.nodePath("/qemu/%d/firewall/rules", vmid), params, nil)
}

// DeleteFirewallRule removes the rule at pos.
func (c *Client) DeleteFirewallRule(ctx context.Context, vmid, pos int) error {
	return c.form(ctx, http.MethodDelete, c.nodePath("/qemu/%d/firewall/rules/%d", vmid, pos), nil, nil)
}

// FirewallOptions returns the VM firewall's options (enable, policies, ...)
// as a raw map: the set of keys Proxmox reports has grown across versions.
func (c *Client) FirewallOptions(ctx context.Context, vmid int) (map[string]any, error) {
	var options map[string]any
	err := c.form(ctx, http.MethodGet, c.nodePath("/qemu/%d/firewall/options", vmid), nil, &options)
	return options, err
}

func (c *Client) SetFirewallOptions(ctx context.Context, vmid int, params url.Values) error {
	return c.form(ctx, http.MethodPut, c.nodePath("/qemu/%d/firewall/options", vmid), params, nil)
}

// IPSets returns the names of the VM's IP sets.
func (c *Client) IPSets(ctx context.Context, vmid int) ([]string, error) {
	var sets []struct {
		Name string `json:"name"`
	}
	if err := c.form(ctx, http.MethodGet, c.nodePath("/qemu/%d/firewall/ipset", vmid), nil, &sets); err != nil {
		return nil, err
	}
	names := make([]string, len(sets))
	for i, s := range sets {
		names[i] = s.Name
	}
	return names, nil
}

func (c *Client) CreateIPSet(ctx context.Context, vmid int, name string) error {
	return c.form(ctx, http.MethodPost, c.nodePath("/qemu/%d/firewall/ipset", vmid), url.Values{"name": {name}}, nil)
}

// IPSetEntries returns the CIDRs in the named set, as Proxmox reports them.
func (c *Client) IPSetEntries(ctx context.Context, vmid int, name string) ([]string, error) {
	var entries []struct {
		CIDR string `json:"cidr"`
	}
	path := c.nodePath("/qemu/%d/firewall/ipset/%s", vmid, url.PathEscape(name))
	if err := c.form(ctx, http.MethodGet, path, nil, &entries); err != nil {
		return nil, err
	}
	cidrs := make([]string, len(entries))
	for i, e := range entries {
		cidrs[i] = e.CIDR
	}
	return cidrs, nil
}

func (c *Client) AddIPSetEntry(ctx context.Context, vmid int, name, cidr string) error {
	path := c.nodePath("/qemu/%d/firewall/ipset/%s", vmid, url.PathEscape(name))
	return c.form(ctx, http.MethodPost, path, url.Values{"cidr": {cidr}}, nil)
}

// DeleteIPSetEntry removes cidr from the named set. cidr is path-escaped, so
// a CIDR's "/" survives as %2F rather than being read as a path separator.
func (c *Client) DeleteIPSetEntry(ctx context.Context, vmid int, name, cidr string) error {
	path := c.nodePath("/qemu/%d/firewall/ipset/%s/%s", vmid, url.PathEscape(name), url.PathEscape(cidr))
	return c.form(ctx, http.MethodDelete, path, nil, nil)
}

func (c *Client) DeleteIPSet(ctx context.Context, vmid int, name string) error {
	path := c.nodePath("/qemu/%d/firewall/ipset/%s", vmid, url.PathEscape(name))
	return c.form(ctx, http.MethodDelete, path, nil, nil)
}
