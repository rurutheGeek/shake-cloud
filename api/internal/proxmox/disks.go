package proxmox

import (
	"context"
	"encoding/json"
	"net/http"
	"net/url"
	"strconv"
	"strings"
)

// ConfigureVM changes a VM's configuration and returns the task's UPID
// without waiting for it, unlike UpdateVMConfig. Proxmox answers null for a
// change that needed no task (e.g. one that only touches pending state), which
// decodes here as "".
func (c *Client) ConfigureVM(ctx context.Context, vmid int, params url.Values) (string, error) {
	var upid *string
	err := c.form(ctx, http.MethodPost, c.nodePath("/qemu/%d/config", vmid), params, &upid)
	if err != nil || upid == nil {
		return "", err
	}
	return *upid, nil
}

// UnlinkDisks detaches the given config keys (e.g. "scsi0") into unusedN
// entries, or destroys them on storage when force is true. Measured
// synchronous: it never returns a task.
func (c *Client) UnlinkDisks(ctx context.Context, vmid int, keys []string, force bool) error {
	params := url.Values{"idlist": {strings.Join(keys, ",")}}
	if force {
		params.Set("force", "1")
	}
	return c.form(ctx, http.MethodPut, c.nodePath("/qemu/%d/unlink", vmid), params, nil)
}

// MoveDisk reassigns disk (an owned volume or an unusedN slot) to another
// VM's targetDisk slot and returns the task's UPID. The target VM may be
// running.
func (c *Client) MoveDisk(ctx context.Context, vmid int, disk string, targetVMID int, targetDisk string) (string, error) {
	params := url.Values{
		"disk":        {disk},
		"target-vmid": {strconv.Itoa(targetVMID)},
		"target-disk": {targetDisk},
	}
	var upid string
	err := c.form(ctx, http.MethodPost, c.nodePath("/qemu/%d/move_disk", vmid), params, &upid)
	return upid, err
}

// PendingChange is one entry of a VM's pending configuration changes.
type PendingChange struct {
	Key     string `json:"key"`
	Value   any    `json:"value"`
	Pending any    `json:"pending"`
	Delete  int    `json:"delete"`
}

// VMPending returns the entries of /qemu/{vmid}/pending that describe an
// actual change: Proxmox lists every current config key here too, most of
// them with no "pending" field and delete 0, which callers have no use for.
func (c *Client) VMPending(ctx context.Context, vmid int) ([]PendingChange, error) {
	var raw []map[string]json.RawMessage
	if err := c.form(ctx, http.MethodGet, c.nodePath("/qemu/%d/pending", vmid), nil, &raw); err != nil {
		return nil, err
	}
	var changes []PendingChange
	for _, entry := range raw {
		var change PendingChange
		if key, ok := entry["key"]; ok {
			_ = json.Unmarshal(key, &change.Key)
		}
		if value, ok := entry["value"]; ok {
			_ = json.Unmarshal(value, &change.Value)
		}
		pending, hasPending := entry["pending"]
		if hasPending {
			_ = json.Unmarshal(pending, &change.Pending)
		}
		if del, ok := entry["delete"]; ok {
			_ = json.Unmarshal(del, &change.Delete)
		}
		if hasPending || change.Delete != 0 {
			changes = append(changes, change)
		}
	}
	return changes, nil
}
