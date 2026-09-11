package proxmox

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// testToken has a real token's shape without looking like a credential:
// tools/check-publication.py rejects UUID-shaped PVE tokens in tracked files.
const testToken = "cloudapi@pve!cloudapi=example-token"

func server(t *testing.T, handler http.HandlerFunc) *Client {
	t.Helper()
	s := httptest.NewServer(handler)
	t.Cleanup(s.Close)
	c := New(s.URL, testToken, "apextox", false)
	c.PollInterval = time.Millisecond
	return c
}

func reply(w http.ResponseWriter, data any) {
	_ = json.NewEncoder(w).Encode(map[string]any{"data": data})
}

func TestRequestsCarryTheTokenAndFormEncoding(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "PVEAPIToken="+testToken {
			t.Errorf("Authorization = %q", r.Header.Get("Authorization"))
		}
		if r.URL.Path != "/api2/json/nodes/apextox/qemu" || r.Method != http.MethodPost {
			t.Errorf("%s %s", r.Method, r.URL.Path)
		}
		if err := r.ParseForm(); err != nil || r.PostForm.Get("vmid") != "5000" || r.PostForm.Get("pool") != "cloud" {
			t.Errorf("form = %v (%v)", r.PostForm, err)
		}
		reply(w, "UPID:apextox:1:2:3:qmcreate:5000:cloudapi@pve!cloudapi:")
	})
	upid, err := c.CreateVM(context.Background(), map[string][]string{"vmid": {"5000"}, "pool": {"cloud"}})
	if err != nil || !strings.HasPrefix(upid, "UPID:") {
		t.Fatalf("CreateVM = %q, %v", upid, err)
	}
}

func TestErrorsKeepTheStatusSoCallersCanTellForbiddenApart(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
		_, _ = io.WriteString(w, `{"data":null,"message":"Permission check failed (/vms/5000, VM.Audit)\n"}`)
	})
	_, err := c.VMStatus(context.Background(), 5000)
	if StatusOf(err) != http.StatusForbidden || !strings.Contains(err.Error(), "VM.Audit") {
		t.Fatalf("err = %v", err)
	}
	if StatusOf(errors.New("other")) != 0 {
		t.Fatal("StatusOf invented a status")
	}
}

func TestParameterErrorsAreReported(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		_, _ = io.WriteString(w, `{"data":null,"errors":{"memory":"value must be at least 16"}}`)
	})
	_, err := c.CreateVM(context.Background(), map[string][]string{"memory": {"1"}})
	if StatusOf(err) != http.StatusBadRequest || !strings.Contains(err.Error(), "memory: value must be at least 16") {
		t.Fatalf("err = %v", err)
	}
}

func TestWaitTaskWaitsForTheTaskToStop(t *testing.T) {
	polls := 0
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		// url.PathEscape leaves ':' alone, which Proxmox accepts in the UPID segment.
		if r.URL.EscapedPath() != "/api2/json/nodes/apextox/tasks/UPID:apextox:1/status" {
			t.Errorf("path = %s", r.URL.EscapedPath())
		}
		polls++
		if polls < 3 {
			reply(w, map[string]string{"status": "running"})
			return
		}
		reply(w, map[string]string{"status": "stopped", "exitstatus": "OK"})
	})
	if err := c.WaitTask(context.Background(), "UPID:apextox:1"); err != nil || polls != 3 {
		t.Fatalf("err = %v after %d polls", err, polls)
	}
}

func TestWaitTaskReportsAFailedTask(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		reply(w, map[string]string{"status": "stopped", "exitstatus": "unable to create VM 5000 - VM 5000 already exists"})
	})
	var taskErr *TaskError
	if err := c.WaitTask(context.Background(), "UPID:x"); !errors.As(err, &taskErr) || !strings.Contains(taskErr.ExitStatus, "already exists") {
		t.Fatalf("err = %v", err)
	}
}

func TestUploadISOSendsAMultipartFile(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api2/json/nodes/apextox/storage/cloud-images/upload" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if err := r.ParseMultipartForm(1 << 20); err != nil {
			t.Fatal(err)
		}
		file, header, err := r.FormFile("filename")
		if err != nil {
			t.Fatal(err)
		}
		content, _ := io.ReadAll(file)
		if r.FormValue("content") != "iso" || header.Filename != "seed.iso" || string(content) != "ISO" {
			t.Errorf("content=%q filename=%q body=%q", r.FormValue("content"), header.Filename, content)
		}
		reply(w, "UPID:upload")
	})
	if _, err := c.UploadISO(context.Background(), "cloud-images", "seed.iso", []byte("ISO")); err != nil {
		t.Fatal(err)
	}
}

func TestDeleteVolumeEscapesTheVolumeID(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.EscapedPath() != "/api2/json/nodes/apextox/storage/cloud-images/content/cloud-images:iso%2Fseed.iso" &&
			r.URL.EscapedPath() != "/api2/json/nodes/apextox/storage/cloud-images/content/cloud-images%3Aiso%2Fseed.iso" {
			t.Errorf("path = %s", r.URL.EscapedPath())
		}
		reply(w, nil)
	})
	if err := c.DeleteVolume(context.Background(), "cloud-images", "cloud-images:iso/seed.iso"); err != nil {
		t.Fatal(err)
	}
}

func TestListVMsAndCapacity(t *testing.T) {
	c := server(t, func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api2/json/cluster/resources":
			reply(w, []map[string]any{{"vmid": 5000, "name": "i-1", "status": "running", "pool": "cloud", "node": "apextox"}})
		case "/api2/json/nodes/apextox/status":
			reply(w, map[string]any{
				"memory":  map[string]int64{"total": 64, "free": 20, "available": 30},
				"cpu":     0.125,
				"cpuinfo": map[string]any{"model": "AMD Ryzen 9 8945HS", "cores": 8, "cpus": 16, "sockets": 1, "mhz": "1100.947"},
				// Proxmox reports these as strings; decoding must not depend on it.
				"loadavg":    []string{"0.14", "0.20", "0.19"},
				"pveversion": "pve-manager/9.2.2",
			})
		case "/api2/json/nodes/apextox/storage/local-lvm/status":
			reply(w, map[string]int64{"total": 100, "used": 10, "avail": 90})
		default:
			t.Errorf("unexpected %s", r.URL.Path)
		}
	})
	ctx := context.Background()
	vms, err := c.ListVMs(ctx)
	if err != nil || len(vms) != 1 || vms[0].VMID != 5000 || vms[0].Pool != "cloud" {
		t.Fatalf("ListVMs = %+v, %v", vms, err)
	}
	status, err := c.NodeStatus(ctx)
	if err != nil || status.Memory.Available != 30 || status.CPUInfo.Cores != 8 || status.CPUInfo.CPUs != 16 ||
		status.Usage != 0.125 || status.PVEVersion != "pve-manager/9.2.2" {
		t.Fatalf("NodeStatus = %+v, %v", status, err)
	}
	storage, err := c.StorageStatus(ctx, "local-lvm")
	if err != nil || storage.Avail != 90 {
		t.Fatalf("StorageStatus = %+v, %v", storage, err)
	}
}
