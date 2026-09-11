package server

import (
	"net/http/httptest"
	"net/netip"
	"testing"
)

func TestClientIPBelievesForwardedForOnlyFromTheProxy(t *testing.T) {
	proxies := []netip.Prefix{netip.MustParsePrefix("172.16.0.0/12"), netip.MustParsePrefix("127.0.0.1/32")}
	for _, tc := range []struct {
		name, peer, forwarded, want string
		trusted                     []netip.Prefix
	}{
		{"no proxy configured ignores the header", "192.0.2.10:5000", "203.0.113.9", "192.0.2.10", nil},
		{"a direct caller cannot claim another address", "192.0.2.10:5000", "203.0.113.9", "192.0.2.10", proxies},
		{"the proxy's view of the client is used", "172.18.0.1:5000", "203.0.113.9", "203.0.113.9", proxies},
		{"hops a client prepended are skipped", "172.18.0.1:5000", "198.51.100.7, 203.0.113.9", "203.0.113.9", proxies},
		{"chained proxies are walked past", "127.0.0.1:5000", "203.0.113.9, 172.18.0.5", "203.0.113.9", proxies},
		{"the proxy itself when it sends no header", "172.18.0.1:5000", "", "172.18.0.1", proxies},
		{"garbage stops the walk", "172.18.0.1:5000", "not-an-ip", "172.18.0.1", proxies},
	} {
		t.Run(tc.name, func(t *testing.T) {
			r := httptest.NewRequest("GET", "/", nil)
			r.RemoteAddr = tc.peer
			if tc.forwarded != "" {
				r.Header.Set("X-Forwarded-For", tc.forwarded)
			}
			if got := clientIP(r, tc.trusted); got != tc.want {
				t.Fatalf("clientIP = %q, want %q", got, tc.want)
			}
		})
	}
}
