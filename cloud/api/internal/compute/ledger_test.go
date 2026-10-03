package compute

import (
	"context"
	"errors"
	"log/slog"
	"slices"
	"testing"
	"time"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/netbox"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/site"
)

const trustedAccount = "934162309796"

type fakeLedger struct {
	next     int
	vms      map[int]netbox.VM
	clusters map[int]int
	assigned map[int]int // address ID -> interface ID
	writes   int
	fail     error
}

func newFakeLedger() *fakeLedger {
	return &fakeLedger{next: 100, vms: map[int]netbox.VM{}, clusters: map[int]int{}, assigned: map[int]int{}}
}

func (f *fakeLedger) ClusterID(ctx context.Context, name string) (int, error) {
	if name != "k11" {
		return 0, errors.New("no such cluster")
	}
	return 7, nil
}

func (f *fakeLedger) VMsByTag(ctx context.Context, tag string) ([]netbox.VM, error) {
	if f.fail != nil {
		return nil, f.fail
	}
	var out []netbox.VM
	for _, vm := range f.vms {
		if slices.Contains(vm.Tags, tag) {
			out = append(out, vm)
		}
	}
	return out, nil
}

func (f *fakeLedger) apply(vm netbox.VM, spec netbox.VMSpec) netbox.VM {
	vm.Name, vm.Status, vm.Description = spec.Name, spec.Status, spec.Description
	vm.VCPUs, vm.MemoryMB, vm.Tags = spec.VCPUs, spec.MemoryMB, slices.Clone(spec.Tags)
	return vm
}

func (f *fakeLedger) CreateVM(ctx context.Context, clusterID int, spec netbox.VMSpec) (netbox.VM, error) {
	if slices.Contains(spec.Tags, "no-such-tag") {
		return netbox.VM{}, &netbox.Error{Method: "POST", Path: "/virtualization/virtual-machines/", Status: 400, Detail: "tag does not exist"}
	}
	f.next++
	f.writes++
	vm := f.apply(netbox.VM{ID: f.next}, spec)
	f.vms[vm.ID], f.clusters[vm.ID] = vm, clusterID
	return vm, nil
}

func (f *fakeLedger) UpdateVM(ctx context.Context, id int, spec netbox.VMSpec) error {
	f.writes++
	f.vms[id] = f.apply(f.vms[id], spec)
	return nil
}

func (f *fakeLedger) DeleteVM(ctx context.Context, id int) error {
	f.writes++
	delete(f.vms, id)
	return nil
}

func (f *fakeLedger) EnsureVMInterface(ctx context.Context, vmID int, name string) (int, error) {
	return vmID * 10, nil
}

func (f *fakeLedger) AssignIP(ctx context.Context, ipID, interfaceID int) error {
	f.writes++
	f.assigned[ipID] = interfaceID
	return nil
}

func (f *fakeLedger) SetPrimaryIP(ctx context.Context, vmID, ipID int) error {
	if f.assigned[ipID] != vmID*10 {
		return errors.New("the address is not assigned to this VM")
	}
	f.writes++
	vm := f.vms[vmID]
	vm.PrimaryIP4 = ipID
	f.vms[vmID] = vm
	return nil
}

func (f *fakeLedger) byName(name string) (netbox.VM, bool) {
	for _, vm := range f.vms {
		if vm.Name == name {
			return vm, true
		}
	}
	return netbox.VM{}, false
}

func ledgerService(ledger Ledger) *Service {
	return &Service{
		Ledger: ledger, Log: slog.New(slog.DiscardHandler),
		Site: site.Site{Ledger: site.Ledger{
			Cluster:       "k11",
			GroupAccounts: []string{trustedAccount},
			TagsByName:    map[string][]string{"media-01": {"media-stack"}},
		}},
	}
}

func ledgerInstance(id, account, name, state string, ipID int) db.Instance {
	instance := db.Instance{
		ID: id, AccountID: account, OwnerUsername: "owner", Name: name, State: state,
		CPUCores: 2, MemoryMiB: 2048, IPAddress: "192.168.10.101/24",
	}
	if ipID != 0 {
		instance.NetBoxIPID = &ipID
	}
	return instance
}

const (
	mediaID = "i-a06df9a2dfd1ce6db"
	otherID = "i-0123456789abcdef0"
)

func TestTheLedgerRegistersARunningInstanceWithItsAddress(t *testing.T) {
	ledger := newFakeLedger()
	s := ledgerService(ledger)
	instances := []db.Instance{ledgerInstance(mediaID, trustedAccount, "media-01", db.StateRunning, 41)}
	if err := s.syncLedger(context.Background(), instances); err != nil {
		t.Fatal(err)
	}
	vm, ok := ledger.byName(mediaID)
	if !ok || vm.Status != "active" || vm.PrimaryIP4 != 41 || vm.Description != "media-01 / owner" ||
		vm.VCPUs != 2 || vm.MemoryMB != 2048 || ledger.clusters[vm.ID] != 7 {
		t.Fatalf("entry = %+v, found %v", vm, ok)
	}
	if !slices.Equal(vm.Tags, []string{NetBoxTag, "media-stack"}) {
		t.Fatalf("tags = %v", vm.Tags)
	}

	// A second pass over the same picture writes nothing.
	before := ledger.writes
	if err := s.syncLedger(context.Background(), instances); err != nil || ledger.writes != before {
		t.Fatalf("second pass: err %v, writes %d -> %d", err, before, ledger.writes)
	}
}

func TestAGroupIsNeverTakenFromAnAccountTheSiteDoesNotTrust(t *testing.T) {
	ledger := newFakeLedger()
	s := ledgerService(ledger)
	// Someone else names their VM after the media host. It is registered, so
	// the ledger is complete, but it must not land in the media group.
	err := s.syncLedger(context.Background(), []db.Instance{
		ledgerInstance(otherID, "111111111111", "media-01", db.StateRunning, 42),
	})
	if err != nil {
		t.Fatal(err)
	}
	vm, _ := ledger.byName(otherID)
	if !slices.Equal(vm.Tags, []string{NetBoxTag}) {
		t.Fatalf("tags = %v", vm.Tags)
	}
}

func TestAStoppedInstanceGoesOfflineAndComesBack(t *testing.T) {
	ledger := newFakeLedger()
	s := ledgerService(ledger)
	for _, step := range []struct{ state, want string }{
		{db.StateRunning, "active"}, {db.StateStopping, "offline"}, {db.StateStopped, "offline"}, {db.StateRunning, "active"},
	} {
		err := s.syncLedger(context.Background(), []db.Instance{ledgerInstance(mediaID, trustedAccount, "media-01", step.state, 41)})
		if err != nil {
			t.Fatal(err)
		}
		if vm, _ := ledger.byName(mediaID); vm.Status != step.want || vm.PrimaryIP4 != 41 {
			t.Fatalf("%s: entry = %+v", step.state, vm)
		}
	}
}

func TestAnInstanceWithoutAnAddressIsNotRegisteredYet(t *testing.T) {
	ledger := newFakeLedger()
	s := ledgerService(ledger)
	err := s.syncLedger(context.Background(), []db.Instance{ledgerInstance(mediaID, trustedAccount, "media-01", db.StatePending, 0)})
	if err != nil || len(ledger.vms) != 0 {
		t.Fatalf("err %v, entries %v", err, ledger.vms)
	}
}

func TestOnlyTheCloudsOwnEntriesAreRemoved(t *testing.T) {
	ledger := newFakeLedger()
	s := ledgerService(ledger)
	// A terminated instance's entry, an instance that is merely busy and has
	// lost nothing, and two the sync must never touch: a Terraform VM without
	// the tag, and a tagged VM whose name is not an instance ID.
	ledger.vms[1] = netbox.VM{ID: 1, Name: otherID, Status: "active", Tags: []string{NetBoxTag}}
	ledger.vms[2] = netbox.VM{ID: 2, Name: "identity", Status: "active", Tags: []string{"identity"}}
	ledger.vms[3] = netbox.VM{ID: 3, Name: "hand-made", Status: "active", Tags: []string{NetBoxTag}}
	err := s.syncLedger(context.Background(), []db.Instance{
		ledgerInstance(mediaID, trustedAccount, "media-01", db.StateShuttingDown, 41),
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := ledger.byName(otherID); ok {
		t.Error("the terminated instance's entry was kept")
	}
	if vm, ok := ledger.byName(mediaID); !ok || vm.Status != "offline" {
		t.Errorf("the busy instance's entry = %+v, found %v", vm, ok)
	}
	if len(ledger.vms[2].Tags) != 1 || ledger.vms[2].Name != "identity" || ledger.vms[3].Name != "hand-made" {
		t.Errorf("foreign entries were changed: %+v %+v", ledger.vms[2], ledger.vms[3])
	}
}

func TestANetBoxOutageChangesNothing(t *testing.T) {
	ledger := newFakeLedger()
	ledger.fail = errors.New("netbox is down")
	s := ledgerService(ledger)
	err := s.syncLedger(context.Background(), []db.Instance{ledgerInstance(mediaID, trustedAccount, "media-01", db.StateRunning, 41)})
	if err == nil || ledger.writes != 0 {
		t.Fatalf("err %v, writes %d", err, ledger.writes)
	}
}

func TestOneRefusedEntryDoesNotHoldBackTheOthers(t *testing.T) {
	ledger := newFakeLedger()
	s := ledgerService(ledger)
	s.Site.Ledger.TagsByName["net-01"] = []string{"no-such-tag"}
	err := s.syncLedger(context.Background(), []db.Instance{
		ledgerInstance(otherID, trustedAccount, "net-01", db.StateRunning, 43),
		ledgerInstance(mediaID, trustedAccount, "media-01", db.StateRunning, 41),
	})
	if err == nil {
		t.Fatal("the refused entry was not reported")
	}
	if vm, ok := ledger.byName(mediaID); !ok || vm.PrimaryIP4 != 41 {
		t.Fatalf("the other instance was not registered: %+v, found %v", vm, ok)
	}
}

func TestAWakeUpSyncsWithoutWaitingForTheTimer(t *testing.T) {
	ledger := newFakeLedger()
	s := ledgerService(ledger)
	s.ledgerWake = make(chan struct{}, 1)
	// Asking twice before the sync runs must not block the caller.
	s.wakeLedger()
	s.wakeLedger()
	select {
	case <-s.ledgerWake:
	case <-time.After(time.Second):
		t.Fatal("no wake-up was queued")
	}
	select {
	case <-s.ledgerWake:
		t.Fatal("a second wake-up was queued; one is enough")
	default:
	}
	// A service built without the channel (no ledger) ignores the request.
	(&Service{}).wakeLedger()
}
