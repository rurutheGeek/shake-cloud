// Package proxmox is the part of the Proxmox VE API the cloud uses, called with
// the pool-scoped cloudapi@pve token.
//
// One property shapes every caller: per-VM endpoints answer 403 both for a VM
// outside the token's pools and for a VMID that does not exist. A 403 therefore
// never means "gone". Existence is decided by ListVMs, which returns exactly the
// VMs the token can see.
package proxmox

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/url"
	"sort"
	"strconv"
	"strings"
	"time"
)

type Client struct {
	base  string
	token string
	node  string
	http  *http.Client
	// PollInterval is how often WaitTask asks about a running task.
	PollInterval time.Duration
}

// New returns a client for one node. token is the complete
// "user@realm!name=uuid" form. insecure skips certificate verification, for a
// host still on Proxmox's self-signed certificate.
func New(endpoint, token, node string, insecure bool) *Client {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	if insecure {
		transport.TLSClientConfig = &tls.Config{InsecureSkipVerify: true}
	}
	return &Client{
		base:         strings.TrimRight(endpoint, "/") + "/api2/json",
		token:        token,
		node:         node,
		http:         &http.Client{Transport: transport, Timeout: 5 * time.Minute},
		PollInterval: 2 * time.Second,
	}
}

// Error is a non-2xx answer.
type Error struct {
	Method string
	Path   string
	Status int
	Reason string
}

func (e *Error) Error() string {
	return fmt.Sprintf("proxmox %s %s: %d %s", e.Method, e.Path, e.Status, e.Reason)
}

// StatusOf returns the HTTP status of a Proxmox error, or 0 for anything else.
func StatusOf(err error) int {
	var e *Error
	if errors.As(err, &e) {
		return e.Status
	}
	return 0
}

// TaskError is a task that finished with anything other than OK.
type TaskError struct {
	UPID       string
	ExitStatus string
}

func (e *TaskError) Error() string {
	return fmt.Sprintf("proxmox task %s failed: %s", e.UPID, e.ExitStatus)
}

func (c *Client) nodePath(format string, args ...any) string {
	return "/nodes/" + url.PathEscape(c.node) + fmt.Sprintf(format, args...)
}

func (c *Client) do(ctx context.Context, method, path string, body io.Reader, contentType string, out any) error {
	request, err := http.NewRequestWithContext(ctx, method, c.base+path, body)
	if err != nil {
		return err
	}
	request.Header.Set("Authorization", "PVEAPIToken="+c.token)
	if contentType != "" {
		request.Header.Set("Content-Type", contentType)
	}
	route := strings.SplitN(path, "?", 2)[0]
	response, err := c.http.Do(request)
	if err != nil {
		return fmt.Errorf("proxmox %s %s: %w", method, route, err)
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(response.Body, 16<<20))
	if err != nil {
		return fmt.Errorf("proxmox %s %s: %w", method, route, err)
	}
	var envelope struct {
		Data    json.RawMessage   `json:"data"`
		Message string            `json:"message"`
		Errors  map[string]string `json:"errors"`
	}
	_ = json.Unmarshal(raw, &envelope)

	if response.StatusCode/100 != 2 {
		// Proxmox puts the reason in the status line, e.g.
		// "403 Permission check failed (/vms/5000, VM.Audit)".
		reason := strings.TrimSpace(strings.TrimPrefix(response.Status, strconv.Itoa(response.StatusCode)))
		if message := strings.TrimSpace(envelope.Message); message != "" && !strings.Contains(reason, message) {
			reason = strings.TrimSpace(reason + ": " + message)
		}
		fields := make([]string, 0, len(envelope.Errors))
		for field := range envelope.Errors {
			fields = append(fields, field)
		}
		sort.Strings(fields)
		for _, field := range fields {
			reason += fmt.Sprintf("; %s: %s", field, strings.TrimSpace(envelope.Errors[field]))
		}
		return &Error{Method: method, Path: route, Status: response.StatusCode, Reason: reason}
	}
	if out == nil || len(envelope.Data) == 0 || string(envelope.Data) == "null" {
		return nil
	}
	return json.Unmarshal(envelope.Data, out)
}

func (c *Client) form(ctx context.Context, method, path string, values url.Values, out any) error {
	if values == nil {
		return c.do(ctx, method, path, nil, "", out)
	}
	return c.do(ctx, method, path, strings.NewReader(values.Encode()), "application/x-www-form-urlencoded", out)
}

// Memory is the node's RAM in bytes.
type Memory struct {
	Total     int64 `json:"total"`
	Free      int64 `json:"free"`
	Available int64 `json:"available"`
}

// CPUInfo describes the node's processor. Cores are physical, CPUs are threads.
type CPUInfo struct {
	Model   string `json:"model"`
	Cores   int    `json:"cores"`
	CPUs    int    `json:"cpus"`
	Sockets int    `json:"sockets"`
}

// NodeStatus is what the node reports about itself. Usage is the fraction of
// CPU in use (0 to 1), which is what Proxmox's own summary shows.
type NodeStatus struct {
	Memory        Memory        `json:"memory"`
	RootFS        StorageStatus `json:"rootfs"`
	Usage         float64       `json:"cpu"`
	CPUInfo       CPUInfo       `json:"cpuinfo"`
	KernelVersion string        `json:"kversion"`
	PVEVersion    string        `json:"pveversion"`
	Uptime        int64         `json:"uptime"`
}

// NodeStatus needs Sys.Audit on /nodes/<node> (the CloudApiNodeAudit role).
// Admission control reads the memory from it, so a field added here must not be
// able to fail decoding: Proxmox reports loadavg as strings in some versions
// and numbers in others, and it is deliberately left out.
func (c *Client) NodeStatus(ctx context.Context) (NodeStatus, error) {
	var status NodeStatus
	err := c.form(ctx, http.MethodGet, c.nodePath("/status"), nil, &status)
	return status, err
}

// StorageStatus is a storage's capacity in bytes.
type StorageStatus struct {
	Total int64 `json:"total"`
	Used  int64 `json:"used"`
	Avail int64 `json:"avail"`
}

func (c *Client) StorageStatus(ctx context.Context, storage string) (StorageStatus, error) {
	var status StorageStatus
	err := c.form(ctx, http.MethodGet, c.nodePath("/storage/%s/status", url.PathEscape(storage)), nil, &status)
	return status, err
}

type VM struct {
	VMID   int    `json:"vmid"`
	Name   string `json:"name"`
	Status string `json:"status"`
	Pool   string `json:"pool"`
	Node   string `json:"node"`
}

// ListVMs returns every VM the token can see: for cloudapi@pve, the cloud pool.
func (c *Client) ListVMs(ctx context.Context) ([]VM, error) {
	var vms []VM
	err := c.form(ctx, http.MethodGet, "/cluster/resources?type=vm", nil, &vms)
	return vms, err
}

// CreateVM starts creating a VM and returns the task's UPID.
func (c *Client) CreateVM(ctx context.Context, params url.Values) (string, error) {
	var upid string
	err := c.form(ctx, http.MethodPost, c.nodePath("/qemu"), params, &upid)
	return upid, err
}

// VMConfig returns the VM's current configuration keys, e.g. "virtio0".
func (c *Client) VMConfig(ctx context.Context, vmid int) (map[string]any, error) {
	var config map[string]any
	err := c.form(ctx, http.MethodGet, c.nodePath("/qemu/%d/config", vmid), nil, &config)
	return config, err
}

// VMStatus returns "running" or "stopped".
func (c *Client) VMStatus(ctx context.Context, vmid int) (string, error) {
	var status struct {
		Status string `json:"status"`
	}
	err := c.form(ctx, http.MethodGet, c.nodePath("/qemu/%d/status/current", vmid), nil, &status)
	return status.Status, err
}

// Power runs start, stop, shutdown or reboot and returns the task's UPID.
func (c *Client) Power(ctx context.Context, vmid int, action string, params url.Values) (string, error) {
	if params == nil {
		params = url.Values{}
	}
	var upid string
	err := c.form(ctx, http.MethodPost, c.nodePath("/qemu/%d/status/%s", vmid, url.PathEscape(action)), params, &upid)
	return upid, err
}

// ResizeDisk grows a disk to an absolute size such as "20G" and waits for it.
func (c *Client) ResizeDisk(ctx context.Context, vmid int, disk, size string) error {
	var upid *string
	err := c.form(ctx, http.MethodPut, c.nodePath("/qemu/%d/resize", vmid), url.Values{"disk": {disk}, "size": {size}}, &upid)
	if err != nil || upid == nil || *upid == "" {
		return err
	}
	return c.WaitTask(ctx, *upid)
}

// DeleteVM destroys a VM with its disks and returns the task's UPID.
func (c *Client) DeleteVM(ctx context.Context, vmid int) (string, error) {
	var upid string
	err := c.form(ctx, http.MethodDelete, c.nodePath("/qemu/%d?purge=1&destroy-unreferenced-disks=1", vmid), nil, &upid)
	return upid, err
}

// UploadISO stores content as <storage>:iso/<filename> and returns the task's UPID.
func (c *Client) UploadISO(ctx context.Context, storage, filename string, content []byte) (string, error) {
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	if err := writer.WriteField("content", "iso"); err != nil {
		return "", err
	}
	part, err := writer.CreateFormFile("filename", filename)
	if err != nil {
		return "", err
	}
	if _, err := part.Write(content); err != nil {
		return "", err
	}
	if err := writer.Close(); err != nil {
		return "", err
	}
	var upid string
	err = c.do(ctx, http.MethodPost, c.nodePath("/storage/%s/upload", url.PathEscape(storage)), &body, writer.FormDataContentType(), &upid)
	return upid, err
}

type Volume struct {
	VolID string `json:"volid"`
	Size  int64  `json:"size"`
}

func (c *Client) ListVolumes(ctx context.Context, storage, content string) ([]Volume, error) {
	var volumes []Volume
	path := c.nodePath("/storage/%s/content?content=%s", url.PathEscape(storage), url.QueryEscape(content))
	err := c.form(ctx, http.MethodGet, path, nil, &volumes)
	return volumes, err
}

// DeleteVolume removes an uploaded ISO or image and waits when Proxmox runs it as a task.
func (c *Client) DeleteVolume(ctx context.Context, storage, volid string) error {
	var upid *string
	err := c.form(ctx, http.MethodDelete, c.nodePath("/storage/%s/content/%s", url.PathEscape(storage), url.PathEscape(volid)), nil, &upid)
	if err != nil || upid == nil || *upid == "" {
		return err
	}
	return c.WaitTask(ctx, *upid)
}

// WaitTask polls a task until it stops. HTTP 200 on the request that started
// it only means the task began.
func (c *Client) WaitTask(ctx context.Context, upid string) error {
	for {
		var status struct {
			Status     string `json:"status"`
			ExitStatus string `json:"exitstatus"`
		}
		if err := c.form(ctx, http.MethodGet, c.nodePath("/tasks/%s/status", url.PathEscape(upid)), nil, &status); err != nil {
			return err
		}
		if status.Status == "stopped" {
			if status.ExitStatus == "OK" || strings.HasPrefix(status.ExitStatus, "WARNINGS") {
				return nil
			}
			return &TaskError{UPID: upid, ExitStatus: status.ExitStatus}
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(c.PollInterval):
		}
	}
}
