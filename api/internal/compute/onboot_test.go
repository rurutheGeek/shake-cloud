package compute

import (
	"context"
	"testing"

	"github.com/rurutheGeek/shake-cloud/api/internal/db"
)

// Proxmox starts onboot VMs after the host reboots, and monitoring alerts on
// an onboot VM that is down; both have to follow what the owner asked for.
func TestNewVMsStartWithTheHost(t *testing.T) {
	s, _, _ := testService(t)
	instance := db.Instance{ID: "i-0123456789abcdef0", MACAddress: "BC:24:11:00:00:01"}
	if got := s.vmParams(instance, 5000, db.Resources{}, "img", "", "local-lvm").Get("onboot"); got != "1" {
		t.Fatalf("image launch onboot = %q, want 1", got)
	}
	if got := s.installVmParams(instance, 5000, db.Resources{}, "iso", "", "local-lvm").Get("onboot"); got != "1" {
		t.Fatalf("ISO install onboot = %q, want 1", got)
	}
}

func TestOnbootIsWrittenOnceAndRemembered(t *testing.T) {
	s, pve, _ := testService(t)
	pve.vms[5000] = &fakeVM{status: "stopped", config: map[string]any{}}
	if s.onbootKnown("i-1", false) {
		t.Fatal("nothing written yet")
	}
	if err := s.setOnboot(context.Background(), "i-1", 5000, false); err != nil {
		t.Fatal(err)
	}
	if pve.vms[5000].config["onboot"] != "0" {
		t.Fatalf("config onboot = %v, want 0", pve.vms[5000].config["onboot"])
	}
	if !s.onbootKnown("i-1", false) || s.onbootKnown("i-1", true) {
		t.Fatal("the written value is not remembered")
	}
}
