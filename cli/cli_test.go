package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
)

func captureOutput(t *testing.T, fn func() error) (string, error) {
	t.Helper()
	reader, writer, err := os.Pipe()
	if err != nil {
		t.Fatal(err)
	}
	previous := os.Stdout
	os.Stdout = writer
	runErr := fn()
	writer.Close()
	os.Stdout = previous
	data, err := io.ReadAll(reader)
	if err != nil {
		t.Fatal(err)
	}
	return string(data), runErr
}

func TestInstanceLsPrintsTheApiAnswer(t *testing.T) {
	var gotAuth string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		if r.URL.Path != "/v1/instances" {
			t.Errorf("path = %s", r.URL.Path)
		}
		io.WriteString(w, `{"instances":[{"instance_id":"i-0123456789abcdef0","account_id":"1",
			"owner_username":"alice","image_id":"img-x","instance_type":"small","state":"running",
			"private_ip_address":"192.168.10.100","mac_address":"m","vcpus":2,"memory_mib":2048,
			"root_disk_gib":20,"ballooning":true,"tags":{"Name":"web"},
			"launch_time":"2026-09-11T00:00:00Z","security_groups":[{"group_id":"sg-1","group_name":"default"}],
			"firewall_state":"in-sync"}]}`)
	}))
	defer server.Close()
	t.Setenv("SHAKECLOUD_ENDPOINT", server.URL)
	t.Setenv("SHAKECLOUD_ACCESS_KEY", "sca_test.secret")

	out, err := captureOutput(t, func() error { return run([]string{"--json", "instance", "ls"}) })
	if err != nil {
		t.Fatal(err)
	}
	if gotAuth != "Bearer sca_test.secret" {
		t.Fatalf("Authorization = %q", gotAuth)
	}
	if !strings.Contains(out, "i-0123456789abcdef0") {
		t.Fatalf("output = %s", out)
	}

	out, err = captureOutput(t, func() error { return run([]string{"instance", "ls"}) })
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out, "web") || !strings.Contains(out, "192.168.10.100") {
		t.Fatalf("table output = %s", out)
	}
}

func TestIdentityNeedsAnAccessKey(t *testing.T) {
	t.Setenv("SHAKECLOUD_ENDPOINT", "http://127.0.0.1:1")
	t.Setenv("SHAKECLOUD_ACCESS_KEY", "")
	if _, err := captureOutput(t, func() error { return run([]string{"identity"}) }); err == nil {
		t.Fatal("identity without an access key should fail")
	}
}

func TestVolumeCreateRequiresASize(t *testing.T) {
	t.Setenv("SHAKECLOUD_ACCESS_KEY", "sca_test.secret")
	if _, err := captureOutput(t, func() error { return run([]string{"volume", "create"}) }); err == nil {
		t.Fatal("volume create without --size should fail")
	}
}

func TestUnknownCommandIsAnError(t *testing.T) {
	if _, err := captureOutput(t, func() error { return run([]string{"frobnicate"}) }); err == nil {
		t.Fatal("an unknown command should fail")
	}
}
