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

func TestVMsAreReadWithTheirTagsAndPrimaryAddress(t *testing.T) {
	c := server(t, "nbt_x.y", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/virtualization/virtual-machines/" || r.URL.Query().Get("tag") != "managed-by-cloud-api" || r.URL.Query().Get("limit") != "0" {
			t.Errorf("%s %s", r.Method, r.URL)
		}
		// vcpus is a decimal: NetBox writes it as a number or a string.
		_, _ = w.Write([]byte(`{"results":[
			{"id":5,"name":"i-a06df9a2dfd1ce6db","status":{"value":"active"},"description":"media-01 / owner",
			 "vcpus":4.0,"memory":6144,"tags":[{"slug":"managed-by-cloud-api"},{"slug":"media-stack"}],"primary_ip4":{"id":41}},
			{"id":6,"name":"i-0123456789abcdef0","status":{"value":"offline"},"vcpus":"2.00","memory":null,"tags":[],"primary_ip4":null}]}`))
	})
	vms, err := c.VMsByTag(context.Background(), "managed-by-cloud-api")
	if err != nil || len(vms) != 2 {
		t.Fatalf("VMsByTag = %+v, %v", vms, err)
	}
	if a := vms[0]; a.ID != 5 || a.Status != "active" || a.VCPUs != 4 || a.MemoryMB != 6144 || a.PrimaryIP4 != 41 ||
		len(a.Tags) != 2 || a.Tags[1] != "media-stack" {
		t.Errorf("first = %+v", a)
	}
	if b := vms[1]; b.Status != "offline" || b.VCPUs != 2 || b.MemoryMB != 0 || b.PrimaryIP4 != 0 || len(b.Tags) != 0 {
		t.Errorf("second = %+v", b)
	}
}

func TestAVMIsCreatedInTheClusterWithTagSlugs(t *testing.T) {
	c := server(t, "nbt_x.y", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/api/virtualization/virtual-machines/" {
			t.Errorf("%s %s", r.Method, r.URL.Path)
		}
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		if body["name"] != "i-a06df9a2dfd1ce6db" || body["cluster"] != float64(7) || body["status"] != "active" || body["memory"] != float64(6144) {
			t.Errorf("body = %v", body)
		}
		if tags := body["tags"].([]any); len(tags) != 2 || tags[1].(map[string]any)["slug"] != "media-stack" {
			t.Errorf("tags = %v", body["tags"])
		}
		w.WriteHeader(http.StatusCreated)
		_, _ = w.Write([]byte(`{"id":5,"name":"i-a06df9a2dfd1ce6db","status":{"value":"active"},"tags":[],"primary_ip4":null}`))
	})
	vm, err := c.CreateVM(context.Background(), 7, VMSpec{
		Name: "i-a06df9a2dfd1ce6db", Status: "active", VCPUs: 4, MemoryMB: 6144, Tags: []string{"managed-by-cloud-api", "media-stack"},
	})
	if err != nil || vm.ID != 5 {
		t.Fatalf("CreateVM = %+v, %v", vm, err)
	}
}

func TestAnAddressIsAssignedBeforeItBecomesPrimary(t *testing.T) {
	var calls []string
	c := server(t, "nbt_x.y", func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		calls = append(calls, r.Method+" "+r.URL.RequestURI())
		switch r.URL.Path {
		case "/api/virtualization/interfaces/":
			if r.Method == http.MethodGet {
				_, _ = w.Write([]byte(`{"results":[]}`))
				return
			}
			if body["virtual_machine"] != float64(5) || body["name"] != "primary" {
				t.Errorf("interface body = %v", body)
			}
			w.WriteHeader(http.StatusCreated)
			_, _ = w.Write([]byte(`{"id":9}`))
		case "/api/ipam/ip-addresses/41/":
			if body["assigned_object_type"] != "virtualization.vminterface" || body["assigned_object_id"] != float64(9) {
				t.Errorf("address body = %v", body)
			}
			_, _ = w.Write([]byte(`{}`))
		case "/api/virtualization/virtual-machines/5/":
			if body["primary_ip4"] != float64(41) {
				t.Errorf("VM body = %v", body)
			}
			_, _ = w.Write([]byte(`{}`))
		default:
			t.Errorf("unexpected %s %s", r.Method, r.URL.Path)
		}
	})
	ctx := context.Background()
	interfaceID, err := c.EnsureVMInterface(ctx, 5, "primary")
	if err != nil || interfaceID != 9 {
		t.Fatalf("EnsureVMInterface = %d, %v", interfaceID, err)
	}
	if err := c.AssignIP(ctx, 41, interfaceID); err != nil {
		t.Fatal(err)
	}
	if err := c.SetPrimaryIP(ctx, 5, 41); err != nil {
		t.Fatal(err)
	}
	if len(calls) != 4 {
		t.Fatalf("calls = %v", calls)
	}
}

func TestDeletingAVMThatIsGoneIsNotAnError(t *testing.T) {
	c := server(t, "nbt_x.y", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"detail":"Not found."}`))
	})
	if err := c.DeleteVM(context.Background(), 5); err != nil {
		t.Fatal(err)
	}
}
