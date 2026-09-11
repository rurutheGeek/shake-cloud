package proxmox

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestConfigureVMReturnsTheUPID(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/api2/json/nodes/apextox/qemu/5000/config" {
			t.Errorf("%s %s", r.Method, r.URL.Path)
		}
		if err := r.ParseForm(); err != nil || r.PostForm.Get("scsi0") != "local-lvm:1,discard=on" {
			t.Errorf("form = %v (%v)", r.PostForm, err)
		}
		reply(w, "UPID:apextox:1:2:3:qmconfig:5000:cloudapi@pve!cloudapi:")
	})
	upid, err := c.ConfigureVM(context.Background(), 5000, map[string][]string{"scsi0": {"local-lvm:1,discard=on"}})
	if err != nil || !strings.HasPrefix(upid, "UPID:") {
		t.Fatalf("ConfigureVM = %q, %v", upid, err)
	}
}

func TestConfigureVMReturnsEmptyForNull(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		reply(w, nil)
	})
	upid, err := c.ConfigureVM(context.Background(), 5000, nil)
	if err != nil || upid != "" {
		t.Fatalf("ConfigureVM = %q, %v", upid, err)
	}
}

func TestUnlinkDisksSendsNoForceFieldWhenNotForced(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPut || r.URL.Path != "/api2/json/nodes/apextox/qemu/5998/unlink" {
			t.Errorf("%s %s", r.Method, r.URL.Path)
		}
		if err := r.ParseForm(); err != nil {
			t.Fatal(err)
		}
		if r.PostForm.Get("idlist") != "scsi0,virtio1" {
			t.Errorf("idlist = %q", r.PostForm.Get("idlist"))
		}
		if _, ok := r.PostForm["force"]; ok {
			t.Errorf("force field sent unexpectedly: %v", r.PostForm)
		}
		reply(w, nil)
	})
	if err := c.UnlinkDisks(context.Background(), 5998, []string{"scsi0", "virtio1"}, false); err != nil {
		t.Fatal(err)
	}
}

func TestUnlinkDisksSendsForceWhenRequested(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseForm(); err != nil || r.PostForm.Get("force") != "1" {
			t.Errorf("form = %v (%v)", r.PostForm, err)
		}
		reply(w, nil)
	})
	if err := c.UnlinkDisks(context.Background(), 5998, []string{"unused0"}, true); err != nil {
		t.Fatal(err)
	}
}

func TestMoveDiskSendsTheTargetAndReturnsTheUPID(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/api2/json/nodes/apextox/qemu/5998/move_disk" {
			t.Errorf("%s %s", r.Method, r.URL.Path)
		}
		if err := r.ParseForm(); err != nil || r.PostForm.Get("disk") != "unused0" ||
			r.PostForm.Get("target-vmid") != "5000" || r.PostForm.Get("target-disk") != "unused0" {
			t.Errorf("form = %v (%v)", r.PostForm, err)
		}
		reply(w, "UPID:apextox:movedisk")
	})
	upid, err := c.MoveDisk(context.Background(), 5998, "unused0", 5000, "unused0")
	if err != nil || upid != "UPID:apextox:movedisk" {
		t.Fatalf("MoveDisk = %q, %v", upid, err)
	}
}

func TestVMPendingFiltersOutSettledEntries(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api2/json/nodes/apextox/qemu/5000/pending" {
			t.Errorf("path = %s", r.URL.Path)
		}
		reply(w, []map[string]any{
			// Untouched config key: no pending field, delete 0. Must be dropped.
			{"key": "cores", "value": 2, "delete": 0},
			// A pending change: kept.
			{"key": "memory", "value": 2048, "pending": 4096},
			// Queued for deletion: kept even with no pending value.
			{"key": "scsi1", "value": "local-lvm:vm-5000-disk-1", "delete": 1},
		})
	})
	changes, err := c.VMPending(context.Background(), 5000)
	if err != nil {
		t.Fatal(err)
	}
	if len(changes) != 2 {
		t.Fatalf("changes = %+v", changes)
	}
	if changes[0].Key != "memory" || changes[0].Pending != float64(4096) {
		t.Errorf("changes[0] = %+v", changes[0])
	}
	if changes[1].Key != "scsi1" || changes[1].Delete != 1 {
		t.Errorf("changes[1] = %+v", changes[1])
	}
}

func TestVMPendingKeepsTheStatusOn403(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
	}))
	defer s.Close()
	c := New(s.URL, testToken, "apextox", false)
	if _, err := c.VMPending(context.Background(), 5000); StatusOf(err) != http.StatusForbidden {
		t.Fatalf("err = %v", err)
	}
}
