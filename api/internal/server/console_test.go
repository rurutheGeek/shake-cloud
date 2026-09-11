package server

import (
	"bytes"
	"context"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/compute"
)

func TestConsoleStoreBindsURLsToAnAccountAndSpendsEachTicketOnce(t *testing.T) {
	store := newConsoleStore()
	now := time.Now()
	store.put("token", consoleSession{accountID: "000000000001", instanceID: "i-1", expires: now.Add(time.Minute)}, now)

	if _, ok := store.get("token", "000000000002", now); ok {
		t.Fatal("another account can use the URL")
	}
	if _, ok := store.get("token", "000000000001", now); !ok {
		t.Fatal("the owner cannot use the URL")
	}
	// A websocket before the page asked Proxmox for a ticket gets nothing.
	if _, ok := store.takeTicket("token", "000000000001", now); ok {
		t.Fatal("a ticket was handed out before one was issued")
	}
	ticket := compute.ConsoleTicket{InstanceID: "i-1", VMID: 5000}
	if !store.setTicket("token", "000000000001", ticket, now) {
		t.Fatal("setTicket failed")
	}
	if got, ok := store.takeTicket("token", "000000000001", now); !ok || got.VMID != 5000 {
		t.Fatalf("takeTicket = %+v, %v", got, ok)
	}
	if _, ok := store.takeTicket("token", "000000000001", now); ok {
		t.Fatal("one page load opened two websockets")
	}
	// Reloading the page issues a new ticket, which is how a console reconnects.
	store.setTicket("token", "000000000001", ticket, now)
	if _, ok := store.takeTicket("token", "000000000001", now); !ok {
		t.Fatal("a reload did not reconnect")
	}

	later := now.Add(2 * time.Minute)
	if _, ok := store.get("token", "000000000001", later); ok {
		t.Fatal("an expired URL still works")
	}
	if len(store.sessions) != 0 {
		t.Fatal("the expired session was kept")
	}
	// Memory holds hashes, not usable URLs.
	store.put("secret-token", consoleSession{accountID: "a", expires: later.Add(time.Minute)}, later)
	for key := range store.sessions {
		if strings.Contains(key, "secret-token") {
			t.Fatal("the store is keyed by the raw token")
		}
	}
}

func TestLogsNeverCarryAConsoleToken(t *testing.T) {
	for path, want := range map[string]string{
		"/console/abc123":    "/console/{token}",
		"/console/abc123/ws": "/console/{token}/ws",
		"/v1/instances":      "/v1/instances",
	} {
		if got := loggedPath(path); got != want {
			t.Errorf("loggedPath(%q) = %q, want %q", path, got, want)
		}
	}
}

// The template is written separately from the handler, so check that every
// field the handler passes is one the template uses, and that nothing inline
// would be blocked by the page's content security policy.
func TestTheConsoleTemplateMatchesItsHandler(t *testing.T) {
	var out bytes.Buffer
	err := templates.ExecuteTemplate(&out, "console.html", consolePageData{
		InstanceID: "i-0123456789abcdef0", InstanceName: `<b>web</b>`, Password: `p&"w`, WebSocketPath: "/console/tok/ws",
	})
	if err != nil {
		t.Fatal(err)
	}
	page := out.String()
	for _, want := range []string{`/console/tok/ws`, `i-0123456789abcdef0`, `/static/console.js`} {
		if !strings.Contains(page, want) {
			t.Errorf("the page does not contain %q", want)
		}
	}
	if strings.Contains(page, "<b>web</b>") || strings.Contains(page, `p&"w`) {
		t.Error("template data is not escaped")
	}
	if strings.Count(page, "<script") != strings.Count(page, `src="/static/`) {
		t.Error("the page has an inline script, which its policy blocks")
	}
	if strings.Contains(page, "style=") {
		t.Error("the page has an inline style attribute, which its policy blocks")
	}
}

func TestConsoleSessionsAreForTheOwnerOfARunningInstance(t *testing.T) {
	s := testServer(t, nil)
	withInstances(t, s)
	alice, aliceCookie := session(t, s, "alice", false)
	_, bobCookie := session(t, s, "bob", false)
	_, adminCookie := session(t, s, "root", true)
	instance := record(t, s, alice.ID, "web")
	path := "/v1/instances/" + instance.ID + "/console"
	cookies := func(c *http.Cookie) []*http.Cookie { return []*http.Cookie{c} }

	expectStatus(t, do(t, s, req{method: "POST", path: path, cookies: cookies(bobCookie)}), http.StatusForbidden)
	// Still launching.
	expectStatus(t, do(t, s, req{method: "POST", path: path, cookies: cookies(aliceCookie)}), http.StatusConflict)

	if _, err := s.pool.Exec(context.Background(), `UPDATE instances SET state = 'running', pending_action = NULL,
		vm_created = true, vmid = 5000 WHERE instance_id = $1`, instance.ID); err != nil {
		t.Fatal(err)
	}
	created := do(t, s, req{method: "POST", path: path, cookies: cookies(aliceCookie)})
	expectStatus(t, created, http.StatusCreated)
	body := decode[struct {
		Console struct {
			URL       string    `json:"url"`
			ExpiresAt time.Time `json:"expires_at"`
		} `json:"console"`
	}](t, created)
	if !strings.HasPrefix(body.Console.URL, "/console/") || time.Until(body.Console.ExpiresAt) < 4*time.Minute {
		t.Fatalf("console: %+v", body.Console)
	}
	// A cloud-admin may open one too.
	expectStatus(t, do(t, s, req{method: "POST", path: path, cookies: cookies(adminCookie)}), http.StatusCreated)

	handshake := map[string]string{"Connection": "Upgrade", "Upgrade": "websocket", "Sec-WebSocket-Version": "13",
		"Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==", "Origin": "http://portal.test"}
	ws := body.Console.URL + "/ws"

	// Another site cannot open a console through Alice's logged-in browser.
	crossSite := map[string]string{}
	for k, v := range handshake {
		crossSite[k] = v
	}
	crossSite["Origin"] = "https://evil.example"
	expectStatus(t, do(t, s, req{method: "GET", path: ws, cookies: cookies(aliceCookie), headers: crossSite}), http.StatusForbidden)
	// Not a websocket handshake at all.
	expectStatus(t, do(t, s, req{method: "GET", path: ws, cookies: cookies(aliceCookie),
		headers: map[string]string{"Origin": "http://portal.test"}}), http.StatusBadRequest)
	// The page has not issued a ticket yet, so there is nothing to connect to.
	expectStatus(t, do(t, s, req{method: "GET", path: ws, cookies: cookies(aliceCookie), headers: handshake}), http.StatusNotFound)
	// Bob cannot use Alice's URL, for the page or the websocket.
	expectStatus(t, do(t, s, req{method: "GET", path: ws, cookies: cookies(bobCookie), headers: handshake}), http.StatusNotFound)
	expectStatus(t, do(t, s, req{method: "GET", path: body.Console.URL, cookies: cookies(bobCookie)}), http.StatusNotFound)
	// Nobody logged in: told to log in, not shown a console.
	expectStatus(t, do(t, s, req{method: "GET", path: body.Console.URL}), http.StatusUnauthorized)

	found := events(t, s, req{path: "/v1/audit-events?event_name=CreateConsoleSession", cookies: cookies(adminCookie)})
	var ok, denied int
	for _, e := range found.Events {
		if e.ErrorCode == "" && e.ResourceID == instance.ID {
			ok++
		} else if e.ErrorCode != "" {
			denied++
		}
	}
	if ok != 2 || denied < 1 {
		t.Fatalf("audit: %d granted, %d refused: %+v", ok, denied, found.Events)
	}
}
