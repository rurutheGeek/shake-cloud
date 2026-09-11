// Package proxmox is the part of the Proxmox VE API the cloud uses, called with
// the pool-scoped cloudapi@pve token.
//
// One property shapes every caller: per-VM endpoints answer 403 both for a VM
// outside the token's pools and for a VMID that does not exist. A 403 therefore
// never means "gone". Existence is decided by ListVMs, which returns exactly the
// VMs the token can see.
package proxmox

import (
	"bufio"
	"bytes"
	"context"
	"crypto/rand"
	"crypto/tls"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime/multipart"
	"net"
	"net/http"
	"net/url"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/wsrelay"
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

// do sends one request. contentLength is -1 to let net/http work it out from
// the body type; a real value is needed when the body is a stream, because
// Proxmox answers 501 to a chunked request.
func (c *Client) do(ctx context.Context, method, path string, body io.Reader, contentLength int64, contentType string, out any) error {
	request, err := http.NewRequestWithContext(ctx, method, c.base+path, body)
	if err != nil {
		return err
	}
	if contentLength >= 0 {
		request.ContentLength = contentLength
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
		return c.do(ctx, method, path, nil, -1, "", out)
	}
	return c.do(ctx, method, path, strings.NewReader(values.Encode()), -1, "application/x-www-form-urlencoded", out)
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

// UpdateVMConfig changes a VM's configuration. Proxmox accepts cpu and memory
// changes for a running VM but only applies them at its next start, so the
// caller decides whether the VM has to be stopped first.
func (c *Client) UpdateVMConfig(ctx context.Context, vmid int, params url.Values) error {
	var upid *string
	err := c.form(ctx, http.MethodPut, c.nodePath("/qemu/%d/config", vmid), params, &upid)
	if err != nil || upid == nil || *upid == "" {
		return err
	}
	return c.WaitTask(ctx, *upid)
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
	err = c.do(ctx, http.MethodPost, c.nodePath("/storage/%s/upload", url.PathEscape(storage)), &body, -1, writer.FormDataContentType(), &upid)
	return upid, err
}

// UploadImage stores a disk image as <storage>:import/<filename> and returns
// the task's UPID. size must be the exact number of bytes body will yield.
//
// **Proxmox refuses a chunked request body with 501** (measured 2026-09-11), so
// the length of the whole multipart envelope has to be declared up front. That
// rules out piping a body of unknown length, which is why the caller has to
// know the size; the envelope is assembled by hand here so its length can be
// computed exactly rather than guessed.
//
// The bytes themselves are still streamed, not buffered: only the framing is
// held in memory. Proxmox validates the file with qemu-img and the task fails
// on anything it cannot open, leaving nothing stored, so a corrupt upload needs
// no cleanup.
func (c *Client) UploadImage(ctx context.Context, storage, filename string, body io.Reader, size int64) (string, error) {
	boundary := make([]byte, 16)
	if _, err := rand.Read(boundary); err != nil {
		return "", err
	}
	mark := "shakecloud" + hex.EncodeToString(boundary)

	var prefix bytes.Buffer
	fmt.Fprintf(&prefix, "--%s\r\nContent-Disposition: form-data; name=\"content\"\r\n\r\nimport\r\n", mark)
	fmt.Fprintf(&prefix, "--%s\r\nContent-Disposition: form-data; name=\"filename\"; filename=%q\r\n", mark, filename)
	fmt.Fprint(&prefix, "Content-Type: application/octet-stream\r\n\r\n")
	suffix := fmt.Sprintf("\r\n--%s--\r\n", mark)

	// LimitReader keeps a body that turns out longer than promised from running
	// past the length already declared.
	envelope := io.MultiReader(bytes.NewReader(prefix.Bytes()), io.LimitReader(body, size), strings.NewReader(suffix))
	length := int64(prefix.Len()) + size + int64(len(suffix))

	var upid string
	err := c.do(ctx, http.MethodPost, c.nodePath("/storage/%s/upload", url.PathEscape(storage)),
		envelope, length, "multipart/form-data; boundary="+mark, &upid)
	return upid, err
}

// VNCTicket is what vncproxy hands back for one console connection: the port
// the VM's VNC proxy listens on, the ticket that opens its websocket, and the
// one-time password the VNC session itself asks for.
type VNCTicket struct {
	Port     int
	Ticket   string
	Password string
}

// VNCProxy starts a VNC proxy for a running VM. websocket=1 makes it reachable
// through vncwebsocket; generate-password=1 makes Proxmox issue a password
// separate from the ticket, so the ticket — which opens the websocket — never
// has to reach the browser.
//
// The proxy only waits a few seconds for its websocket, so call this as late
// as possible before connecting.
func (c *Client) VNCProxy(ctx context.Context, vmid int) (VNCTicket, error) {
	var raw struct {
		// Proxmox reports the port as a string; accept a number too.
		Port     json.RawMessage `json:"port"`
		Ticket   string          `json:"ticket"`
		Password string          `json:"password"`
	}
	params := url.Values{"websocket": {"1"}, "generate-password": {"1"}}
	if err := c.form(ctx, http.MethodPost, c.nodePath("/qemu/%d/vncproxy", vmid), params, &raw); err != nil {
		return VNCTicket{}, err
	}
	port, err := strconv.Atoi(strings.Trim(string(raw.Port), `"`))
	if err != nil || port <= 0 {
		return VNCTicket{}, fmt.Errorf("proxmox vncproxy: unusable port %s", raw.Port)
	}
	if raw.Ticket == "" || raw.Password == "" {
		return VNCTicket{}, errors.New("proxmox vncproxy: the answer has no ticket or password")
	}
	return VNCTicket{Port: port, Ticket: raw.Ticket, Password: raw.Password}, nil
}

// DialVNC opens the websocket to a VM's VNC proxy and returns the connection
// once Proxmox has switched protocols. Everything that follows is websocket
// frames, which the caller relays without interpreting.
//
// This exists because a browser cannot put an Authorization header on a
// websocket, and vncwebsocket requires one. The API makes the connection with
// its own pool-scoped token instead (probe console_auth measured that the token
// is accepted here).
func (c *Client) DialVNC(ctx context.Context, vmid int, ticket VNCTicket) (net.Conn, error) {
	endpoint, err := url.Parse(c.base)
	if err != nil {
		return nil, err
	}
	address := endpoint.Host
	if endpoint.Port() == "" {
		address = net.JoinHostPort(endpoint.Hostname(), "443")
	}
	tlsConfig := &tls.Config{}
	if transport, ok := c.http.Transport.(*http.Transport); ok && transport.TLSClientConfig != nil {
		tlsConfig = transport.TLSClientConfig.Clone()
	}
	if tlsConfig.ServerName == "" {
		tlsConfig.ServerName = endpoint.Hostname()
	}
	dialer := &tls.Dialer{NetDialer: &net.Dialer{Timeout: 10 * time.Second}, Config: tlsConfig}
	conn, err := dialer.DialContext(ctx, "tcp", address)
	if err != nil {
		return nil, fmt.Errorf("proxmox vncwebsocket: %w", err)
	}

	nonce := make([]byte, 16)
	if _, err := rand.Read(nonce); err != nil {
		conn.Close()
		return nil, err
	}
	key := base64.StdEncoding.EncodeToString(nonce)
	query := url.Values{"port": {strconv.Itoa(ticket.Port)}, "vncticket": {ticket.Ticket}}
	target := endpoint.Path + c.nodePath("/qemu/%d/vncwebsocket", vmid) + "?" + query.Encode()

	deadline, ok := ctx.Deadline()
	if !ok {
		deadline = time.Now().Add(15 * time.Second)
	}
	_ = conn.SetDeadline(deadline)
	// No Sec-WebSocket-Extensions: frames are relayed verbatim, so nothing may
	// be negotiated here that the browser's side did not also agree to.
	_, err = fmt.Fprintf(conn, "GET %s HTTP/1.1\r\nHost: %s\r\nAuthorization: PVEAPIToken=%s\r\n"+
		"Connection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\n"+
		"Sec-WebSocket-Key: %s\r\nSec-WebSocket-Protocol: binary\r\n\r\n",
		target, endpoint.Host, c.token, key)
	if err != nil {
		conn.Close()
		return nil, fmt.Errorf("proxmox vncwebsocket: %w", err)
	}
	reader := bufio.NewReader(conn)
	request, _ := http.NewRequest(http.MethodGet, endpoint.Scheme+"://"+endpoint.Host+target, nil)
	response, err := http.ReadResponse(reader, request)
	if err != nil {
		conn.Close()
		return nil, fmt.Errorf("proxmox vncwebsocket: %w", err)
	}
	route := strings.SplitN(target, "?", 2)[0]
	if response.StatusCode != http.StatusSwitchingProtocols {
		conn.Close()
		return nil, &Error{Method: http.MethodGet, Path: route, Status: response.StatusCode,
			Reason: strings.TrimSpace(strings.TrimPrefix(response.Status, strconv.Itoa(response.StatusCode)))}
	}
	if response.Header.Get("Sec-WebSocket-Accept") != wsrelay.AcceptKey(key) {
		conn.Close()
		return nil, fmt.Errorf("proxmox vncwebsocket: the handshake answer does not match the key sent")
	}
	_ = conn.SetDeadline(time.Time{})
	return &bufferedConn{Conn: conn, reader: reader}, nil
}

// bufferedConn keeps bytes the handshake reader already pulled off the socket,
// such as a first frame that arrived with the 101 answer.
type bufferedConn struct {
	net.Conn
	reader *bufio.Reader
}

func (b *bufferedConn) Read(p []byte) (int, error) { return b.reader.Read(p) }

type Volume struct {
	VolID  string `json:"volid"`
	Size   int64  `json:"size"`
	Format string `json:"format"`
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
