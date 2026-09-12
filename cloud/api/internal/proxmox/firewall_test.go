package proxmox

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestFirewallRulesSortsByPos(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/api2/json/nodes/apextox/qemu/5000/firewall/rules" {
			t.Errorf("%s %s", r.Method, r.URL.Path)
		}
		reply(w, []map[string]any{
			{"pos": 2, "type": "in", "action": "ACCEPT", "enable": 1},
			{"pos": 0, "type": "in", "action": "ACCEPT", "enable": 1, "dport": "22"},
			{"pos": 1, "type": "out", "action": "ACCEPT", "enable": 0},
		})
	})
	rules, err := c.FirewallRules(context.Background(), 5000)
	if err != nil || len(rules) != 3 {
		t.Fatalf("rules = %+v, %v", rules, err)
	}
	for i, want := range []int{0, 1, 2} {
		if rules[i].Pos != want {
			t.Errorf("rules[%d].Pos = %d, want %d", i, rules[i].Pos, want)
		}
	}
	if rules[0].Dport != "22" {
		t.Errorf("rules[0].Dport = %q", rules[0].Dport)
	}
}

func TestFirewallRulesKeepsTheStatusOn403(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
	}))
	defer s.Close()
	c := New(s.URL, testToken, "apextox", false)
	if _, err := c.FirewallRules(context.Background(), 5000); StatusOf(err) != http.StatusForbidden {
		t.Fatalf("err = %v", err)
	}
}

func TestInsertFirewallRuleOmitsEmptyFieldsAndNeverSendsPos(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/api2/json/nodes/apextox/qemu/5000/firewall/rules" {
			t.Errorf("%s %s", r.Method, r.URL.Path)
		}
		if err := r.ParseForm(); err != nil {
			t.Fatal(err)
		}
		if r.PostForm.Get("type") != "in" || r.PostForm.Get("action") != "ACCEPT" || r.PostForm.Get("dport") != "22" {
			t.Errorf("form = %v", r.PostForm)
		}
		for _, field := range []string{"pos", "proto", "source", "dest", "comment"} {
			if _, ok := r.PostForm[field]; ok {
				t.Errorf("field %q sent unexpectedly: %v", field, r.PostForm)
			}
		}
		if r.PostForm.Get("enable") != "1" {
			t.Errorf("enable = %q", r.PostForm.Get("enable"))
		}
		reply(w, nil)
	})
	rule := FirewallRule{Pos: 7, Type: "in", Action: "ACCEPT", Dport: "22", Enable: 1}
	if err := c.InsertFirewallRule(context.Background(), 5000, rule); err != nil {
		t.Fatal(err)
	}
}

func TestInsertFirewallRuleSendsEnableZero(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseForm(); err != nil || r.PostForm.Get("enable") != "0" {
			t.Errorf("form = %v (%v)", r.PostForm, err)
		}
		reply(w, nil)
	})
	rule := FirewallRule{Type: "out", Action: "ACCEPT", Enable: 0}
	if err := c.InsertFirewallRule(context.Background(), 5000, rule); err != nil {
		t.Fatal(err)
	}
}

func TestDeleteFirewallRule(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete || r.URL.Path != "/api2/json/nodes/apextox/qemu/5000/firewall/rules/3" {
			t.Errorf("%s %s", r.Method, r.URL.Path)
		}
		reply(w, nil)
	})
	if err := c.DeleteFirewallRule(context.Background(), 5000, 3); err != nil {
		t.Fatal(err)
	}
}

func TestFirewallOptionsGetAndSet(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api2/json/nodes/apextox/qemu/5000/firewall/options" {
			t.Errorf("path = %s", r.URL.Path)
		}
		switch r.Method {
		case http.MethodGet:
			reply(w, map[string]any{"enable": 1})
		case http.MethodPut:
			if err := r.ParseForm(); err != nil || r.PostForm.Get("enable") != "1" {
				t.Errorf("form = %v (%v)", r.PostForm, err)
			}
			reply(w, nil)
		default:
			t.Errorf("method = %s", r.Method)
		}
	})
	options, err := c.FirewallOptions(context.Background(), 5000)
	if err != nil || options["enable"] != float64(1) {
		t.Fatalf("options = %+v, %v", options, err)
	}
	if err := c.SetFirewallOptions(context.Background(), 5000, map[string][]string{"enable": {"1"}}); err != nil {
		t.Fatal(err)
	}
}

func TestIPSetsAndEntries(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api2/json/nodes/apextox/qemu/5000/firewall/ipset":
			reply(w, []map[string]any{{"name": "ipfilter-net0", "digest": "abc"}})
		case r.Method == http.MethodPost && r.URL.Path == "/api2/json/nodes/apextox/qemu/5000/firewall/ipset":
			if err := r.ParseForm(); err != nil || r.PostForm.Get("name") != "web" {
				t.Errorf("form = %v (%v)", r.PostForm, err)
			}
			reply(w, nil)
		case r.Method == http.MethodGet && r.URL.Path == "/api2/json/nodes/apextox/qemu/5000/firewall/ipset/ipfilter-net0":
			reply(w, []map[string]any{{"cidr": "10.0.0.0/24"}, {"cidr": "192.168.1.1"}})
		case r.Method == http.MethodPost && r.URL.Path == "/api2/json/nodes/apextox/qemu/5000/firewall/ipset/ipfilter-net0":
			if err := r.ParseForm(); err != nil || r.PostForm.Get("cidr") != "10.0.0.0/24" {
				t.Errorf("form = %v (%v)", r.PostForm, err)
			}
			reply(w, nil)
		case r.Method == http.MethodDelete && r.URL.Path == "/api2/json/nodes/apextox/qemu/5000/firewall/ipset/ipfilter-net0":
			reply(w, nil)
		default:
			t.Errorf("%s %s", r.Method, r.URL.Path)
		}
	})
	names, err := c.IPSets(context.Background(), 5000)
	if err != nil || len(names) != 1 || names[0] != "ipfilter-net0" {
		t.Fatalf("IPSets = %v, %v", names, err)
	}
	if err := c.CreateIPSet(context.Background(), 5000, "web"); err != nil {
		t.Fatal(err)
	}
	entries, err := c.IPSetEntries(context.Background(), 5000, "ipfilter-net0")
	if err != nil || len(entries) != 2 || entries[0] != "10.0.0.0/24" || entries[1] != "192.168.1.1" {
		t.Fatalf("IPSetEntries = %v, %v", entries, err)
	}
	if err := c.AddIPSetEntry(context.Background(), 5000, "ipfilter-net0", "10.0.0.0/24"); err != nil {
		t.Fatal(err)
	}
	if err := c.DeleteIPSet(context.Background(), 5000, "ipfilter-net0"); err != nil {
		t.Fatal(err)
	}
}

func TestDeleteIPSetEntryEscapesACIDRWithASlash(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		want := "/api2/json/nodes/apextox/qemu/5000/firewall/ipset/ipfilter-net0/10.0.0.0%2F24"
		if r.URL.EscapedPath() != want {
			t.Errorf("EscapedPath = %s, want %s", r.URL.EscapedPath(), want)
		}
		if r.Method != http.MethodDelete {
			t.Errorf("method = %s", r.Method)
		}
		reply(w, nil)
	})
	if err := c.DeleteIPSetEntry(context.Background(), 5000, "ipfilter-net0", "10.0.0.0/24"); err != nil {
		t.Fatal(err)
	}
}

func TestDeleteIPSetEntryKeepsTheStatusOn403(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
	}))
	defer s.Close()
	c := New(s.URL, testToken, "apextox", false)
	err := c.DeleteIPSetEntry(context.Background(), 5000, "ipfilter-net0", "10.0.0.0/24")
	if StatusOf(err) != http.StatusForbidden {
		t.Fatalf("err = %v", err)
	}
}
