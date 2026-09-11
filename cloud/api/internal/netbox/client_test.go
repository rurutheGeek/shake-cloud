package netbox

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func server(t *testing.T, token string, handler http.HandlerFunc) *Client {
	t.Helper()
	s := httptest.NewServer(handler)
	t.Cleanup(s.Close)
	return New(s.URL, token)
}

func TestTokenSchemeFollowsTheTokenFormat(t *testing.T) {
	for token, want := range map[string]string{"nbt_key.secret": "Bearer nbt_key.secret", "0123456789abcdef": "Token 0123456789abcdef"} {
		c := server(t, token, func(w http.ResponseWriter, r *http.Request) {
			if got := r.Header.Get("Authorization"); got != want {
				t.Errorf("Authorization = %q, want %q", got, want)
			}
			_, _ = w.Write([]byte(`{"results":[{"id":2}]}`))
		})
		if _, err := c.IPRangeID(context.Background(), "192.168.10.100/24"); err != nil {
			t.Fatal(err)
		}
	}
}

func TestAllocateIPUsesTheRangeAndTagsTheAddress(t *testing.T) {
	c := server(t, "nbt_x.y", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/api/ipam/ip-ranges/2/available-ips/" {
			t.Errorf("%s %s", r.Method, r.URL.Path)
		}
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		if body["description"] != "i-0123456789abcdef0" || body["status"] != "active" {
			t.Errorf("body = %v", body)
		}
		if tags := body["tags"].([]any); len(tags) != 1 || tags[0].(map[string]any)["slug"] != "managed-by-cloud-api" {
			t.Errorf("tags = %v", body["tags"])
		}
		w.WriteHeader(http.StatusCreated)
		_, _ = w.Write([]byte(`{"id":41,"address":"192.168.10.100/24","description":"i-0123456789abcdef0"}`))
	})
	address, err := c.AllocateIP(context.Background(), 2, Allocation{
		Description: "i-0123456789abcdef0", DNSName: "web", Tags: []string{"managed-by-cloud-api"},
	})
	if err != nil || address.ID != 41 || address.Address != "192.168.10.100/24" {
		t.Fatalf("AllocateIP = %+v, %v", address, err)
	}
}

func TestAnExhaustedRangeIsAnError(t *testing.T) {
	c := server(t, "nbt_x.y", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusConflict)
		_, _ = w.Write([]byte(`{"detail":"Insufficient space is available to accommodate the requested number of IPs"}`))
	})
	_, err := c.AllocateIP(context.Background(), 2, Allocation{Description: "i-1"})
	if e, ok := err.(*Error); !ok || e.Status != http.StatusConflict || e.Detail == "" {
		t.Fatalf("err = %v", err)
	}
}

func TestDeletingAnAddressThatIsGoneSucceeds(t *testing.T) {
	c := server(t, "nbt_x.y", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/ipam/ip-addresses/41/" {
			t.Errorf("path = %s", r.URL.Path)
		}
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"detail":"No IPAddress matches the given query."}`))
	})
	if err := c.DeleteIPAddress(context.Background(), 41); err != nil {
		t.Fatal(err)
	}
}

func TestLookupByDescriptionEscapesTheQuery(t *testing.T) {
	c := server(t, "nbt_x.y", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("description") != "i-1 & x" {
			t.Errorf("query = %s", r.URL.RawQuery)
		}
		_, _ = w.Write([]byte(`{"results":[{"id":7,"address":"192.168.10.101/24","description":"i-1 & x"}]}`))
	})
	found, err := c.IPAddressesByDescription(context.Background(), "i-1 & x")
	if err != nil || len(found) != 1 || found[0].ID != 7 {
		t.Fatalf("found = %+v, %v", found, err)
	}
}
