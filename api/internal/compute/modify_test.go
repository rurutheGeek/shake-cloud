package compute

import (
	"context"
	"strings"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

func ptr[T any](value T) *T { return &value }

// stopped launches an instance and brings it to rest, which is where a resize
// of cpu or memory is allowed.
func stopped(t *testing.T, s *Service, accountID string, r RunRequest) db.Instance {
	t.Helper()
	instance := run(t, s, accountID, r)
	work(t, s, 5)
	if _, err := request(t, s, instance.ID, db.ActionStop, accountID); err != nil {
		t.Fatal(err)
	}
	work(t, s, 3)
	got := get(t, s, instance.ID)
	if got.State != db.StateStopped {
		t.Fatalf("state %s (%s)", got.State, got.LastError)
	}
	return got
}

func TestASizeCanBeGivenWithoutANamedType(t *testing.T) {
	s, pve, _ := testService(t)
	alice := newAccount(t, s, "alice")

	// No instance_type at all: the numbers are the request. The sizes here stay
	// inside the sample deployment's 8 GiB cloud-wide memory budget, which is
	// shared across accounts.
	instance := run(t, s, alice, RunRequest{ImageID: "img-debian13", VCPUs: ptr(3), MemoryMiB: ptr(4096)})
	if instance.InstanceType != "" || instance.CPUCores != 3 || instance.MemoryMiB != 4096 {
		t.Fatalf("custom instance: %+v", instance)
	}
	// The default floor is a quarter of the ceiling.
	if !instance.Ballooning || instance.MemoryMinMiB != 1024 {
		t.Fatalf("ballooning %v floor %d", instance.Ballooning, instance.MemoryMinMiB)
	}
	work(t, s, 5)
	config := pve.vms[*instance.VMID].config
	if config["cores"] != "3" || config["memory"] != "4096" || config["balloon"] != "1024" {
		t.Fatalf("VM config: %v", config)
	}

	// A named type is only a starting point: overriding one field keeps the rest
	// and stops calling it that type.
	other := newAccount(t, s, "bob")
	mixed := run(t, s, other, RunRequest{ImageID: "img-debian13", InstanceType: "small", MemoryMiB: ptr(3072)})
	if mixed.InstanceType != "" || mixed.CPUCores != 2 || mixed.MemoryMiB != 3072 || mixed.MemoryMinMiB != 768 {
		t.Fatalf("mixed instance: %+v", mixed)
	}
}

func TestBallooningCanBeTurnedOff(t *testing.T) {
	s, pve, _ := testService(t)
	alice := newAccount(t, s, "alice")
	instance := run(t, s, alice, RunRequest{ImageID: "img-debian13", VCPUs: ptr(2), MemoryMiB: ptr(2048), Ballooning: ptr(false)})
	if instance.Ballooning || instance.MemoryMinMiB != 0 {
		t.Fatalf("ballooning %v floor %d", instance.Ballooning, instance.MemoryMinMiB)
	}
	work(t, s, 5)
	// Proxmox disables the balloon driver by targeting zero.
	if got := pve.vms[*instance.VMID].config["balloon"]; got != "0" {
		t.Fatalf("balloon = %v, want 0", got)
	}
}

func TestMoreVCPUsThanTheNodeHasThreadsIsRefused(t *testing.T) {
	s, _, _ := testService(t)
	alice := newAccount(t, s, "alice")
	// The fake node reports 8 cores and 16 threads.
	_, _, err := s.Run(context.Background(), alice, RunRequest{ImageID: "img-debian13", VCPUs: ptr(32), MemoryMiB: ptr(1024)}, nil)
	if code(err) != "InvalidParameterValue" || !strings.Contains(err.Error(), "16 threads") {
		t.Fatalf("err = %v", err)
	}
}

func TestResizingAStoppedInstanceReachesTheVM(t *testing.T) {
	s, pve, _ := testService(t)
	alice := newAccount(t, s, "alice")
	instance := stopped(t, s, alice, small)
	vmid := *instance.VMID

	modified, err := s.Modify(context.Background(), instance.ID,
		ModifyRequest{VCPUs: ptr(4), MemoryMiB: ptr(8192), RootDiskGiB: ptr(40)}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if modified.CPUCores != 4 || modified.MemoryMiB != 8192 || modified.RootDiskGiB != 40 {
		t.Fatalf("modified: %+v", modified)
	}
	// The floor followed the ceiling rather than staying at the old preset's.
	if modified.MemoryMinMiB != 2048 || modified.InstanceType != "" {
		t.Fatalf("floor %d, type %q", modified.MemoryMinMiB, modified.InstanceType)
	}
	config := pve.vms[vmid].config
	if config["cores"] != "4" || config["memory"] != "8192" || config["balloon"] != "2048" ||
		!strings.Contains(config["virtio0"].(string), "size=40G") {
		t.Fatalf("VM config: %v", config)
	}

	// Turning ballooning off drops the floor to zero on both sides.
	off, err := s.Modify(context.Background(), instance.ID, ModifyRequest{Ballooning: ptr(false)}, nil)
	if err != nil || off.Ballooning || off.MemoryMinMiB != 0 || pve.vms[vmid].config["balloon"] != "0" {
		t.Fatalf("ballooning off: %+v (%v), balloon=%v", off, err, pve.vms[vmid].config["balloon"])
	}

	// Asking for what it already has changes nothing and is not an error.
	same, err := s.Modify(context.Background(), instance.ID, ModifyRequest{VCPUs: ptr(4)}, nil)
	if err != nil || same.CPUCores != 4 {
		t.Fatalf("no-op resize: %+v (%v)", same, err)
	}
}

func TestResizeRefusesWhatWouldLoseDataOrDisagreeWithTheGuest(t *testing.T) {
	s, _, _ := testService(t)
	alice := newAccount(t, s, "alice")
	running := run(t, s, alice, small)
	work(t, s, 5)

	// cpu and memory only apply at the next start, so the ledger would lie.
	if _, err := s.Modify(context.Background(), running.ID, ModifyRequest{MemoryMiB: ptr(4096)}, nil); code(err) != "IncorrectInstanceState" {
		t.Fatalf("resize while running: %v", err)
	}
	// A disk may still grow while it runs.
	grown, err := s.Modify(context.Background(), running.ID, ModifyRequest{RootDiskGiB: ptr(50)}, nil)
	if err != nil || grown.RootDiskGiB != 50 {
		t.Fatalf("grow while running: %+v (%v)", grown, err)
	}
	// Shrinking would throw away whatever is past the new end.
	if _, err := s.Modify(context.Background(), running.ID, ModifyRequest{RootDiskGiB: ptr(10)}, nil); code(err) != "InvalidParameterValue" {
		t.Fatalf("shrink: %v", err)
	}
	// Nothing to do at all is a bad request, not a silent success.
	if _, err := s.Modify(context.Background(), running.ID, ModifyRequest{}, nil); code(err) != "InvalidParameterValue" {
		t.Fatalf("empty: %v", err)
	}
	if _, err := s.Modify(context.Background(), "i-0000000000000dead", ModifyRequest{VCPUs: ptr(2)}, nil); code(err) != "InvalidInstanceID.NotFound" {
		t.Fatalf("missing instance: %v", err)
	}
}

func TestResizeIsCheckedAgainstTheQuota(t *testing.T) {
	s, _, _ := testService(t)
	alice := newAccount(t, s, "alice")
	instance := stopped(t, s, alice, small)

	// The account quota is 8 GiB of memory in the sample deployment.
	if _, err := s.Modify(context.Background(), instance.ID, ModifyRequest{MemoryMiB: ptr(16384)}, nil); code(err) != "InstanceLimitExceeded" {
		t.Fatalf("over quota: %v", err)
	}
	// Its own current size does not count against it, so the whole quota is reachable.
	if got, err := s.Modify(context.Background(), instance.ID, ModifyRequest{MemoryMiB: ptr(8192)}, nil); err != nil || got.MemoryMiB != 8192 {
		t.Fatalf("up to the quota: %+v (%v)", got, err)
	}
}
