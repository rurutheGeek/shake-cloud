package netbox

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"
)

// VM is a virtual machine in NetBox's ledger, as the Ansible inventory reads it.
type VM struct {
	ID          int
	Name        string
	Status      string
	Description string
	VCPUs       int
	MemoryMB    int
	Tags        []string
	// PrimaryIP4 is the address ID, or 0 when the VM has no primary address.
	// The inventory only lists VMs that have one.
	PrimaryIP4 int
}

// VMSpec is what a ledger entry should say.
type VMSpec struct {
	Name        string
	Status      string
	Description string
	VCPUs       int
	MemoryMB    int
	Tags        []string
}

// vmJSON is NetBox's wire shape. vcpus is a decimal, which NetBox writes as a
// number or a string depending on its settings.
type vmJSON struct {
	ID     int    `json:"id"`
	Name   string `json:"name"`
	Status struct {
		Value string `json:"value"`
	} `json:"status"`
	Description string          `json:"description"`
	VCPUs       json.RawMessage `json:"vcpus"`
	Memory      *int            `json:"memory"`
	Tags        []struct {
		Slug string `json:"slug"`
	} `json:"tags"`
	PrimaryIP4 *struct {
		ID int `json:"id"`
	} `json:"primary_ip4"`
}

func (v vmJSON) vm() VM {
	out := VM{ID: v.ID, Name: v.Name, Status: v.Status.Value, Description: v.Description}
	if number, err := strconv.ParseFloat(strings.Trim(string(v.VCPUs), `"`), 64); err == nil {
		out.VCPUs = int(number)
	}
	if v.Memory != nil {
		out.MemoryMB = *v.Memory
	}
	for _, tag := range v.Tags {
		out.Tags = append(out.Tags, tag.Slug)
	}
	if v.PrimaryIP4 != nil {
		out.PrimaryIP4 = v.PrimaryIP4.ID
	}
	return out
}

func (s VMSpec) body() map[string]any {
	tags := make([]map[string]string, 0, len(s.Tags))
	for _, slug := range s.Tags {
		tags = append(tags, map[string]string{"slug": slug})
	}
	return map[string]any{
		"name": s.Name, "status": s.Status, "description": s.Description,
		"vcpus": s.VCPUs, "memory": s.MemoryMB, "tags": tags,
	}
}

// ClusterID finds the cluster VMs are registered under, by name.
func (c *Client) ClusterID(ctx context.Context, name string) (int, error) {
	var clusters page[struct {
		ID int `json:"id"`
	}]
	if err := c.do(ctx, http.MethodGet, "/virtualization/clusters/?name="+url.QueryEscape(name), nil, &clusters); err != nil {
		return 0, err
	}
	if len(clusters.Results) != 1 {
		return 0, fmt.Errorf("netbox: expected one cluster named %s, found %d", name, len(clusters.Results))
	}
	return clusters.Results[0].ID, nil
}

// VMsByTag lists every VM carrying the tag. limit=0 asks NetBox for all of
// them in one page, up to its MAX_PAGE_SIZE (1000 by default).
func (c *Client) VMsByTag(ctx context.Context, tag string) ([]VM, error) {
	var vms page[vmJSON]
	if err := c.do(ctx, http.MethodGet, "/virtualization/virtual-machines/?limit=0&tag="+url.QueryEscape(tag), nil, &vms); err != nil {
		return nil, err
	}
	out := make([]VM, 0, len(vms.Results))
	for _, vm := range vms.Results {
		out = append(out, vm.vm())
	}
	return out, nil
}

func (c *Client) CreateVM(ctx context.Context, clusterID int, spec VMSpec) (VM, error) {
	body := spec.body()
	body["cluster"] = clusterID
	var created vmJSON
	err := c.do(ctx, http.MethodPost, "/virtualization/virtual-machines/", body, &created)
	return created.vm(), err
}

func (c *Client) UpdateVM(ctx context.Context, id int, spec VMSpec) error {
	return c.do(ctx, http.MethodPatch, fmt.Sprintf("/virtualization/virtual-machines/%d/", id), spec.body(), nil)
}

// DeleteVM removes a ledger entry and its interfaces. A VM that is already
// gone is not an error.
func (c *Client) DeleteVM(ctx context.Context, id int) error {
	err := c.do(ctx, http.MethodDelete, fmt.Sprintf("/virtualization/virtual-machines/%d/", id), nil, nil)
	if e, ok := err.(*Error); ok && e.Status == http.StatusNotFound {
		return nil
	}
	return err
}

// EnsureVMInterface returns the VM's interface of that name, creating it when
// it does not exist yet.
func (c *Client) EnsureVMInterface(ctx context.Context, vmID int, name string) (int, error) {
	var found page[struct {
		ID int `json:"id"`
	}]
	query := fmt.Sprintf("/virtualization/interfaces/?virtual_machine_id=%d&name=%s", vmID, url.QueryEscape(name))
	if err := c.do(ctx, http.MethodGet, query, nil, &found); err != nil {
		return 0, err
	}
	if len(found.Results) > 0 {
		return found.Results[0].ID, nil
	}
	var created struct {
		ID int `json:"id"`
	}
	body := map[string]any{"virtual_machine": vmID, "name": name, "enabled": true}
	err := c.do(ctx, http.MethodPost, "/virtualization/interfaces/", body, &created)
	return created.ID, err
}

// AssignIP attaches an allocated address to a VM interface. NetBox refuses to
// make an address a VM's primary one until it is assigned to that VM.
func (c *Client) AssignIP(ctx context.Context, ipID, interfaceID int) error {
	body := map[string]any{"assigned_object_type": "virtualization.vminterface", "assigned_object_id": interfaceID}
	return c.do(ctx, http.MethodPatch, fmt.Sprintf("/ipam/ip-addresses/%d/", ipID), body, nil)
}

func (c *Client) SetPrimaryIP(ctx context.Context, vmID, ipID int) error {
	body := map[string]any{"primary_ip4": ipID}
	return c.do(ctx, http.MethodPatch, fmt.Sprintf("/virtualization/virtual-machines/%d/", vmID), body, nil)
}
