package server

import (
	"errors"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/compute"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/wsrelay"
)

// A browser console is three steps, because two constraints pull apart:
//
//  1. CreateConsoleSession checks who may open one and hands back a URL. It
//     does not ask Proxmox for anything yet.
//  2. The page at that URL asks Proxmox for a VNC ticket and a one-time
//     password. Proxmox's VNC proxy only waits a few seconds for its
//     websocket, so this happens as late as possible — when the page loads,
//     just before noVNC connects.
//  3. The page's websocket is relayed through the API, because a browser
//     cannot attach the Authorization header vncwebsocket requires.
//
// Console sessions live in memory: they last minutes, a restart invalidating
// them costs a click, and nothing about them needs to survive.

// consoleLifetime is how long a console URL can be opened (and reopened, to
// reconnect) after it is handed out.
const consoleLifetime = 5 * time.Minute

type consoleSession struct {
	accountID    string
	instanceID   string
	instanceName string
	expires      time.Time
	// ticket is set by the page and taken by the websocket, so each page load
	// is good for exactly one connection.
	ticket *compute.ConsoleTicket
}

// consoleStore keys sessions by the token's hash, as the session table does, so
// the process's memory never holds a usable URL.
type consoleStore struct {
	mu       sync.Mutex
	sessions map[string]*consoleSession
}

func newConsoleStore() *consoleStore {
	return &consoleStore{sessions: map[string]*consoleSession{}}
}

func consoleKey(token string) string { return string(hashToken(token)) }

func (c *consoleStore) put(token string, session consoleSession, now time.Time) {
	c.mu.Lock()
	defer c.mu.Unlock()
	for key, existing := range c.sessions {
		if !now.Before(existing.expires) {
			delete(c.sessions, key)
		}
	}
	c.sessions[consoleKey(token)] = &session
}

// lookup returns the live session for token if it belongs to accountID. The
// caller must hold c.mu. An expired session is removed on the way.
func (c *consoleStore) lookup(token, accountID string, now time.Time) *consoleSession {
	key := consoleKey(token)
	session, ok := c.sessions[key]
	if !ok {
		return nil
	}
	if !now.Before(session.expires) {
		delete(c.sessions, key)
		return nil
	}
	if session.accountID != accountID {
		return nil
	}
	return session
}

func (c *consoleStore) get(token, accountID string, now time.Time) (consoleSession, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	session := c.lookup(token, accountID, now)
	if session == nil {
		return consoleSession{}, false
	}
	return *session, true
}

func (c *consoleStore) setTicket(token, accountID string, ticket compute.ConsoleTicket, now time.Time) bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	session := c.lookup(token, accountID, now)
	if session == nil {
		return false
	}
	session.ticket = &ticket
	return true
}

// takeTicket hands out the waiting ticket once. A second websocket on the same
// page load finds nothing, so a URL seen by someone else cannot be joined.
func (c *consoleStore) takeTicket(token, accountID string, now time.Time) (compute.ConsoleTicket, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	session := c.lookup(token, accountID, now)
	if session == nil || session.ticket == nil {
		return compute.ConsoleTicket{}, false
	}
	ticket := *session.ticket
	session.ticket = nil
	return ticket, true
}

func (s *Server) createConsoleSession(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	id := r.PathValue("instance_id")
	if !s.mayAct(w, r, c, id) {
		return
	}
	instance, err := service.ConsoleAvailable(r.Context(), id)
	if err != nil {
		if refusal := (*compute.Error)(nil); errors.As(err, &refusal) {
			event := c.event(refusal.Code, nil)
			event.ResourceID = id
			s.recordDenied(r.Context(), event)
		}
		s.computeError(w, r, err)
		return
	}
	expires := s.now().Add(consoleLifetime)
	event := c.event("", map[string]any{"owner_account_id": instance.AccountID, "expires_at": expires.UTC()})
	event.ResourceID = instance.ID
	// Recorded before the URL exists: a console nobody can account for is not
	// handed out.
	if err := db.RecordAudit(r.Context(), s.pool, event); err != nil {
		s.internalError(w, r, err)
		return
	}
	token := randomToken()
	s.consoles.put(token, consoleSession{
		accountID: c.principal.account.ID, instanceID: instance.ID, instanceName: instance.Name, expires: expires,
	}, s.now())
	writeJSON(w, http.StatusCreated, map[string]any{
		"console": map[string]any{"url": "/console/" + token, "expires_at": expires.UTC()},
	})
}

// consoleSecurityPolicy differs from the portal's only in allowing data: and
// blob: images, which noVNC uses to draw the remote cursor.
const consoleSecurityPolicy = "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; " +
	"img-src 'self' data: blob:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"

type consolePageData struct {
	InstanceID    string
	InstanceName  string
	Password      string
	WebSocketPath string
}

// consolePage renders the noVNC page, asking Proxmox for a fresh ticket on
// every load so that reloading the page is how a console reconnects.
func (s *Server) consolePage(w http.ResponseWriter, r *http.Request) {
	c := newCall(r, "OpenConsole")
	p, failure := s.authenticate(r, c)
	if failure != nil {
		loginPage(w, failure.status, "コンソールを開くには、ポータルにログインしてください。")
		return
	}
	if s.Compute == nil {
		loginPage(w, http.StatusServiceUnavailable, "このクラウドではインスタンスが設定されていません。")
		return
	}
	token := r.PathValue("token")
	session, ok := s.consoles.get(token, p.account.ID, s.now())
	if !ok {
		loginPage(w, http.StatusNotFound,
			"このコンソールの URL は期限が切れているか、別のアカウントのものです。ポータルから開き直してください。")
		return
	}
	_, ticket, err := s.Compute.OpenConsole(r.Context(), session.instanceID)
	if err != nil {
		var refusal *compute.Error
		if errors.As(err, &refusal) {
			loginPage(w, refusal.Status, "コンソールを開けませんでした: "+refusal.Message)
			return
		}
		s.log.Error("opening a console failed", "err", err, "instance_id", session.instanceID)
		loginPage(w, http.StatusInternalServerError, "コンソールを開けませんでした。")
		return
	}
	if !s.consoles.setTicket(token, p.account.ID, ticket, s.now()) {
		loginPage(w, http.StatusNotFound, "このコンソールの URL は期限が切れました。ポータルから開き直してください。")
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Content-Security-Policy", consoleSecurityPolicy)
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Referrer-Policy", "no-referrer")
	w.WriteHeader(http.StatusOK)
	_ = templates.ExecuteTemplate(w, "console.html", consolePageData{
		InstanceID: session.instanceID, InstanceName: session.instanceName,
		Password: ticket.VNC.Password, WebSocketPath: "/console/" + token + "/ws",
	})
}

// headerHasToken reports whether a comma-separated header such as Connection
// carries token, case-insensitively.
func headerHasToken(header http.Header, name, token string) bool {
	for _, value := range header.Values(name) {
		for _, part := range strings.Split(value, ",") {
			if strings.EqualFold(strings.TrimSpace(part), token) {
				return true
			}
		}
	}
	return false
}

// consoleSocket relays the page's websocket to the VM's VNC proxy.
func (s *Server) consoleSocket(w http.ResponseWriter, r *http.Request) {
	c := newCall(r, "ConnectConsole")
	p, failure := s.authenticate(r, c)
	if failure != nil {
		writeError(w, r, failure.status, failure.code, failure.message)
		return
	}
	c.principal = p
	// CrossOriginProtection only guards unsafe methods, and a websocket opens
	// with GET, carrying the session cookie from any site that tries. A browser
	// always sends Origin here, so a cookie-authenticated upgrade must come
	// from this site. An access key cannot be sent by a page on another site,
	// so a CLI using one needs no Origin.
	if p.credentialType == db.CredentialSession && r.Header.Get("Origin") != s.cfg.PublicURL.String() {
		s.recordDenied(r.Context(), c.event("CrossOriginRequestBlocked", map[string]any{"origin": r.Header.Get("Origin")}))
		writeError(w, r, http.StatusForbidden, "CrossOriginRequestBlocked", "the console must be opened from this site")
		return
	}
	key := r.Header.Get("Sec-WebSocket-Key")
	if !headerHasToken(r.Header, "Connection", "upgrade") || !strings.EqualFold(r.Header.Get("Upgrade"), "websocket") ||
		r.Header.Get("Sec-WebSocket-Version") != "13" || !wsrelay.ValidKey(key) {
		writeError(w, r, http.StatusBadRequest, "MalformedRequest", "this endpoint only accepts a websocket handshake")
		return
	}
	if s.Compute == nil {
		writeError(w, r, http.StatusServiceUnavailable, "ServiceUnavailable", "instances are not configured on this deployment")
		return
	}
	ticket, ok := s.consoles.takeTicket(r.PathValue("token"), p.account.ID, s.now())
	if !ok {
		writeError(w, r, http.StatusNotFound, "NoSuchEntity", "no console is waiting on this URL; load the console page again")
		return
	}

	upstream, err := s.Compute.DialConsole(r.Context(), ticket)
	if err != nil {
		s.log.Error("connecting to the VNC proxy failed", "err", err, "instance_id", ticket.InstanceID, "vmid", ticket.VMID)
		writeError(w, r, http.StatusBadGateway, "ServiceUnavailable", "the node refused the console connection; load the console page again")
		return
	}
	conn, buffered, err := http.NewResponseController(w).Hijack()
	if err != nil {
		upstream.Close()
		s.internalError(w, r, err)
		return
	}
	// The server's read and write timeouts were set on this connection for an
	// ordinary request; a console stays open as long as someone uses it.
	_ = conn.SetDeadline(time.Time{})
	protocol := ""
	if headerHasToken(r.Header, "Sec-WebSocket-Protocol", "binary") {
		protocol = "Sec-WebSocket-Protocol: binary\r\n"
	}
	// No Sec-WebSocket-Extensions in the answer: the frames are relayed as they
	// are, so the browser must not compress anything Proxmox would not expect.
	fmt.Fprintf(buffered, "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"+
		"Sec-WebSocket-Accept: %s\r\n%s\r\n", wsrelay.AcceptKey(key), protocol)
	if err := buffered.Flush(); err != nil {
		conn.Close()
		upstream.Close()
		return
	}

	event := c.event("", map[string]any{"vmid": ticket.VMID})
	event.ResourceID = ticket.InstanceID
	if err := db.RecordAudit(r.Context(), s.pool, event); err != nil {
		s.log.Error("audit write failed", "err", err, "event_name", event.EventName)
	}
	started := time.Now()
	s.log.Info("console connected", "instance_id", ticket.InstanceID, "vmid", ticket.VMID, "account_id", p.account.ID)
	wsrelay.Relay(conn, buffered.Reader, upstream)
	s.log.Info("console closed", "instance_id", ticket.InstanceID, "seconds", int(time.Since(started).Seconds()))
}
