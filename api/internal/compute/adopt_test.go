package compute

import (
	"context"
	"testing"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

// addFakeVM puts a VM on the fake node the way an administrator's adopted VM
// would be: already built, with its own name, size and disk.
func addFakeVM(pve *fakePVE, vmid int, status string, config map[string]any) {
	pve.mu.Lock()
	defer pve.mu.Unlock()
	if volid := volidAt(config, "virtio0"); volid != "" {
		if _, exists := pve.disks[volid]; !exists {
			pve.disks[volid] = 8 << 30
		}
	}
	pve.vms[vmid] = &fakeVM{status: status, config: config}
}

func adoptableConfig() map[string]any {
	return map[string]any{
		"name": "game1", "cores": "4", "memory": "4096", "balloon": "1024",
		"net0":    "virtio=BC:24:11:AA:BB:CC,bridge=vmbr0,firewall=1",
		"virtio0": "local-lvm:vm-5100-disk-0,discard=on",
	}
}

func TestAdoptingAnExistingVMRecordsItsRealSpecAndDefaultGroup(t *testing.T) {
	s, pve, _ := testService(t)
	ownerID := newAccount(t, s, "alice")
	addFakeVM(pve, 5100, "running", adoptableConfig())

	audited := false
	instance, err := s.Adopt(context.Background(), AdoptRequest{VMID: 5100, AccountID: ownerID},
		func(tx pgx.Tx, i db.Instance) error { audited = true; return nil })
	if err != nil {
		t.Fatal(err)
	}
	if !instance.Adopted {
		t.Fatal("an adopted instance must be marked adopted")
	}
	if instance.State != db.StateRunning || instance.VMID == nil || *instance.VMID != 5100 {
		t.Fatalf("state %q vmid %v", instance.State, instance.VMID)
	}
	if instance.CPUCores != 4 || instance.MemoryMiB != 4096 || instance.MemoryMinMiB != 1024 || !instance.Ballooning {
		t.Fatalf("size %+v", instance)
	}
	if instance.RootDiskGiB != 8 {
		t.Fatalf("root disk %d, want 8 measured from storage", instance.RootDiskGiB)
	}
	if instance.MACAddress != "BC:24:11:AA:BB:CC" {
		t.Fatalf("mac %q", instance.MACAddress)
	}
	if instance.AccountID != ownerID || instance.Name != "game1" {
		t.Fatalf("owner %q name %q", instance.AccountID, instance.Name)
	}
	if !audited {
		t.Fatal("adoption was not audited")
	}
	groups, err := db.InstanceGroups(context.Background(), s.Pool, []string{instance.ID})
	if err != nil {
		t.Fatal(err)
	}
	if len(groups[instance.ID]) != 1 || groups[instance.ID][0].GroupName != defaultGroupName {
		t.Fatalf("groups %+v", groups[instance.ID])
	}
}

func TestAdoptingStoppedAndOutsideTheRangeWorks(t *testing.T) {
	// The pool boundary, not the 5000-5999 numbering, is what decides what the
	// API may manage, so a VM the administrator moved in from any VMID is fine.
	s, pve, _ := testService(t)
	ownerID := newAccount(t, s, "alice")
	config := adoptableConfig()
	config["virtio0"] = "local-lvm:vm-100-disk-0,discard=on"
	addFakeVM(pve, 100, "stopped", config)

	instance, err := s.Adopt(context.Background(), AdoptRequest{VMID: 100, AccountID: ownerID}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if instance.State != db.StateStopped {
		t.Fatalf("state %q", instance.State)
	}
	if instance.VMID == nil || *instance.VMID != 100 {
		t.Fatalf("vmid %v", instance.VMID)
	}
}

func TestAdoptionRefusesAVMOutsideThePool(t *testing.T) {
	s, _, _ := testService(t)
	ownerID := newAccount(t, s, "alice")
	if _, err := s.Adopt(context.Background(), AdoptRequest{VMID: 5101, AccountID: ownerID}, nil); code(err) != "InvalidInstanceID.NotFound" {
		t.Fatalf("a VM the token cannot see: %v", err)
	}
}

func TestAdoptionRefusesAReservedVMIDAndAnUnknownAccount(t *testing.T) {
	s, pve, _ := testService(t)
	ownerID := newAccount(t, s, "alice")
	addFakeVM(pve, 5100, "running", adoptableConfig())
	if _, err := s.Adopt(context.Background(), AdoptRequest{VMID: 5997, AccountID: ownerID}, nil); code(err) != "InvalidParameterValue" {
		t.Fatalf("reserved vmid: %v", err)
	}
	if _, err := s.Adopt(context.Background(), AdoptRequest{VMID: 5100, AccountID: "000000000000"}, nil); code(err) != "InvalidParameterValue" {
		t.Fatalf("unknown account: %v", err)
	}
}

func TestAdoptingTheSameVMIDTwiceIsRefused(t *testing.T) {
	s, pve, _ := testService(t)
	ownerID := newAccount(t, s, "alice")
	addFakeVM(pve, 5100, "running", adoptableConfig())
	if _, err := s.Adopt(context.Background(), AdoptRequest{VMID: 5100, AccountID: ownerID}, nil); err != nil {
		t.Fatal(err)
	}
	if _, err := s.Adopt(context.Background(), AdoptRequest{VMID: 5100, AccountID: ownerID}, nil); code(err) != "InvalidParameterValue" {
		t.Fatalf("second adoption: %v", err)
	}
}

func TestAdoptionNeedsANetworkCardAndARootDisk(t *testing.T) {
	s, pve, _ := testService(t)
	ownerID := newAccount(t, s, "alice")
	addFakeVM(pve, 5102, "running", map[string]any{"cores": "1", "memory": "1024"})
	if _, err := s.Adopt(context.Background(), AdoptRequest{VMID: 5102, AccountID: ownerID}, nil); code(err) != "InvalidParameterValue" {
		t.Fatalf("no MAC: %v", err)
	}

	noDisk := map[string]any{"cores": "1", "memory": "1024", "net0": "virtio=BC:24:11:AA:BB:CC"}
	addFakeVM(pve, 5103, "running", noDisk)
	if _, err := s.Adopt(context.Background(), AdoptRequest{VMID: 5103, AccountID: ownerID}, nil); code(err) != "InvalidParameterValue" {
		t.Fatalf("unmeasurable disk: %v", err)
	}
	// With the size given outright, an unmeasurable disk is fine.
	if _, err := s.Adopt(context.Background(), AdoptRequest{VMID: 5103, AccountID: ownerID, RootDiskGiB: 12}, nil); err != nil {
		t.Fatalf("root_disk_gib given: %v", err)
	}
}

func TestAdoptionRespectsTheAccountQuota(t *testing.T) {
	s, pve, _ := testService(t)
	ownerID := newAccount(t, s, "alice")
	config := adoptableConfig()
	config["cores"] = "16" // the sample account quota is 8 vCPUs.
	addFakeVM(pve, 5104, "running", config)
	if _, err := s.Adopt(context.Background(), AdoptRequest{VMID: 5104, AccountID: ownerID}, nil); code(err) != "VcpuLimitExceeded" {
		t.Fatalf("over quota: %v", err)
	}
}
