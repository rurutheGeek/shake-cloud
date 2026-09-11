package proxmox

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/wsrelay"
)

func TestVNCProxyAsksForAWebsocketAndASeparatePassword(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/api2/json/nodes/apextox/qemu/5000/vncproxy" {
			t.Errorf("%s %s", r.Method, r.URL.Path)
		}
		if err := r.ParseForm(); err != nil || r.PostForm.Get("websocket") != "1" || r.PostForm.Get("generate-password") != "1" {
			t.Errorf("form = %v (%v)", r.PostForm, err)
		}
		// Proxmox reports the port as a string.
		reply(w, map[string]any{"port": "5901", "ticket": "PVEVNC:abc", "password": "p4ss", "user": "cloudapi@pve!cloudapi"})
	})
	ticket, err := c.VNCProxy(context.Background(), 5000)
	if err != nil || ticket.Port != 5901 || ticket.Ticket != "PVEVNC:abc" || ticket.Password != "p4ss" {
		t.Fatalf("VNCProxy = %+v, %v", ticket, err)
	}
}

// vncNode is just enough of Proxmox's vncwebsocket to exercise the real dial:
// TLS, the token header, the query, the 101 answer, and bytes afterwards.
func vncNode(t *testing.T, answer func(w http.ResponseWriter, r *http.Request)) *Client {
	t.Helper()
	node := httptest.NewTLSServer(http.HandlerFunc(answer))
	t.Cleanup(node.Close)
	return New(node.URL, testToken, "apextox", true)
}

func TestDialVNCUpgradesWithTheTokenAndRelaysBytes(t *testing.T) {
	c := vncNode(t, func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path != "/api2/json/nodes/apextox/qemu/5000/vncwebsocket":
			t.Errorf("path %s", r.URL.Path)
		case r.URL.Query().Get("port") != "5901" || r.URL.Query().Get("vncticket") != "PVEVNC:abc":
			t.Errorf("query %s", r.URL.RawQuery)
		case r.Header.Get("Authorization") != "PVEAPIToken="+testToken:
			t.Errorf("Authorization = %q", r.Header.Get("Authorization"))
		case r.Header.Get("Upgrade") != "websocket" || r.Header.Get("Sec-WebSocket-Protocol") != "binary":
			t.Errorf("handshake headers %v", r.Header)
		case r.Header.Get("Sec-WebSocket-Extensions") != "":
			// Relayed frames must stay uncompressed.
			t.Errorf("an extension was offered: %q", r.Header.Get("Sec-WebSocket-Extensions"))
		}
		conn, rw, err := http.NewResponseController(w).Hijack()
		if err != nil {
			t.Error(err)
			return
		}
		defer conn.Close()
		// The first bytes arrive in the same write as the 101, which is what a
		// real VNC server does, so the handshake reader must not swallow them.
		fmt.Fprintf(rw, "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"+
			"Sec-WebSocket-Accept: %s\r\nSec-WebSocket-Protocol: binary\r\n\r\nRFB 003.008\n",
			wsrelay.AcceptKey(r.Header.Get("Sec-WebSocket-Key")))
		rw.Flush()
		echo := make([]byte, 4)
		if _, err := io.ReadFull(rw, echo); err == nil {
			conn.Write(echo)
		}
	})

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	conn, err := c.DialVNC(ctx, 5000, VNCTicket{Port: 5901, Ticket: "PVEVNC:abc", Password: "p4ss"})
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	banner := make([]byte, 12)
	if _, err := io.ReadFull(conn, banner); err != nil || string(banner) != "RFB 003.008\n" {
		t.Fatalf("banner %q (%v)", banner, err)
	}
	if _, err := conn.Write([]byte("ping")); err != nil {
		t.Fatal(err)
	}
	echo := make([]byte, 4)
	if _, err := io.ReadFull(conn, echo); err != nil || string(echo) != "ping" {
		t.Fatalf("echo %q (%v)", echo, err)
	}
}

func TestDialVNCReportsARefusedUpgrade(t *testing.T) {
	c := vncNode(t, func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "no ticket", http.StatusUnauthorized)
	})
	_, err := c.DialVNC(context.Background(), 5000, VNCTicket{Port: 5901, Ticket: "stale"})
	if StatusOf(err) != http.StatusUnauthorized {
		t.Fatalf("err = %v", err)
	}
}

func TestDialVNCRefusesAnAnswerToSomeoneElsesHandshake(t *testing.T) {
	c := vncNode(t, func(w http.ResponseWriter, r *http.Request) {
		conn, rw, _ := http.NewResponseController(w).Hijack()
		defer conn.Close()
		fmt.Fprintf(rw, "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"+
			"Sec-WebSocket-Accept: %s\r\n\r\n", wsrelay.AcceptKey("dGhlIHNhbXBsZSBub25jZQ=="))
		rw.Flush()
	})
	if _, err := c.DialVNC(context.Background(), 5000, VNCTicket{Port: 5901, Ticket: "PVEVNC:abc"}); err == nil {
		t.Fatal("a 101 answering a different key was accepted")
	}
}
