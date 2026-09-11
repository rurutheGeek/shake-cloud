package compute

import (
	"context"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/site"
)

var big = RunRequest{ImageID: "img-debian13", InstanceType: "2xlarge", Tags: map[string]string{"Name": "game"}}

func setLimits(t *testing.T, s *Service, accountID string, o db.LimitOverrides) site.Limits {
	t.Helper()
	limits, _, err := s.SetLimits(context.Background(), o, accountID, nil)
	if err != nil {
		t.Fatalf("SetLimits: %v", err)
	}
	return limits
}

func TestAnAdministratorsOverrideChangesWhatIsAdmitted(t *testing.T) {
	s, pve, _ := testService(t)
	alice := newAccount(t, s, "alice")

	// The declared limits are 8 GiB per account and an 8 GiB cloud budget, so a
	// 16 GiB instance cannot be admitted. The account's own quota is the first
	// one it meets.
	if _, _, err := s.Run(context.Background(), alice, big, nil); code(err) != "InstanceLimitExceeded" {
		t.Fatalf("16 GiB under the declared limits: %v", err)
	}

	unlimited := 0
	setLimits(t, s, alice, db.LimitOverrides{
		MemoryBudgetMiB: &unlimited, AccountMemoryMiB: &unlimited, AccountVCPUs: &unlimited,
	})
	instance := run(t, s, alice, big)
	if instance.MemoryMiB != 16384 || instance.MemoryMinMiB != 4096 {
		t.Fatalf("instance memory %d/%d", instance.MemoryMiB, instance.MemoryMinMiB)
	}
	work(t, s, 5)
	if got := get(t, s, instance.ID); got.State != db.StateRunning {
		t.Fatalf("state %s (%s)", got.State, got.LastError)
	}
	// Ballooning is what makes a 16 GiB ceiling usable, so the floor must reach
	// the VM.
	if balloon := pve.vms[*instance.VMID].config["balloon"]; balloon != "4096" {
		t.Fatalf("balloon = %v, want the flavor's floor", balloon)
	}

	// Unlimited policy does not invent memory: the host still decides.
	pve.memory.Available = 8 << 30
	if _, _, err := s.Run(context.Background(), alice, big, nil); code(err) != "InsufficientInstanceCapacity" {
		t.Fatalf("host short of memory with unlimited quotas: %v", err)
	}
}

func TestClearingOverridesReturnsToTheDeclaredDefaults(t *testing.T) {
	s, _, _ := testService(t)
	alice := newAccount(t, s, "alice")
	declared := sampleSite().Limits

	four := 4
	if limits := setLimits(t, s, alice, db.LimitOverrides{AccountInstances: &four}); limits.AccountQuota.Instances != 4 {
		t.Fatalf("override not applied: %+v", limits.AccountQuota)
	}
	// A field left out of the next call is not remembered.
	twenty := 20
	limits := setLimits(t, s, alice, db.LimitOverrides{AccountVCPUs: &twenty})
	if limits.AccountQuota.Instances != declared.AccountQuota.Instances || limits.AccountQuota.VCPUs != 20 {
		t.Fatalf("PUT did not replace the whole set: %+v", limits.AccountQuota)
	}
	if limits := setLimits(t, s, alice, db.LimitOverrides{}); limits != declared {
		t.Fatalf("cleared limits = %+v, want the declared %+v", limits, declared)
	}

	stored, err := db.GetLimitOverrides(context.Background(), s.Pool)
	if err != nil || stored.AccountInstances != nil || stored.AccountVCPUs != nil {
		t.Fatalf("overrides %+v (%v)", stored, err)
	}
	if stored.UpdatedAt == nil || stored.UpdatedBy != alice {
		t.Fatalf("the change was not attributed: %+v", stored)
	}
}

func TestLimitsThatCouldNotBeSatisfiedAreRefused(t *testing.T) {
	s, _, _ := testService(t)
	alice := newAccount(t, s, "alice")
	zero, hundredOne, hugeMin := 0, 101, 1000
	for name, o := range map[string]db.LimitOverrides{
		"a root disk minimum above the maximum": {RootDiskMinGiB: &hugeMin},
		"a zero root disk size":                 {RootDiskDefaultGiB: &zero},
		"a disk threshold above 100%":           {VMDiskMaxUsedPercent: &hundredOne},
	} {
		if _, _, err := s.SetLimits(context.Background(), o, alice, nil); code(err) != "ValidationError" {
			t.Errorf("%s: %v", name, err)
		}
	}
	// Nothing was stored by the refused calls.
	stored, err := db.GetLimitOverrides(context.Background(), s.Pool)
	if err != nil || stored.RootDiskMinGiB != nil || stored.VMDiskMaxUsedPercent != nil {
		t.Fatalf("a refused change was stored: %+v (%v)", stored, err)
	}
}

func TestCapacityReportsTheHostAndWhatIsAllotted(t *testing.T) {
	s, _, _ := testService(t)
	alice, bob := newAccount(t, s, "alice"), newAccount(t, s, "bob")
	run(t, s, alice, small)
	run(t, s, bob, small)

	capacity, err := s.Capacity(context.Background(), alice, true)
	if err != nil {
		t.Fatal(err)
	}
	if capacity.Node.Name != "apextox" || capacity.Node.CPUCores != 8 || capacity.Node.CPUThreads != 16 ||
		capacity.Node.MemoryTotalMiB != 64<<10 || capacity.Node.MemoryAvailableMiB != 30<<10 {
		t.Fatalf("node: %+v", capacity.Node)
	}
	// Allotted is the sum of ceilings across every account, not what is in use.
	if capacity.Cloud.Instances != 2 || capacity.Cloud.MemoryMiB != 4096 || capacity.Account.Instances != 1 {
		t.Fatalf("cloud %+v, account %+v", capacity.Cloud, capacity.Account)
	}
	if len(capacity.Accounts) != 2 {
		t.Fatalf("per-account rows: %+v", capacity.Accounts)
	}
	purposes := map[string]int{}
	for _, store := range capacity.Storage {
		purposes[store.Purpose] = store.MaxUsedPercent
	}
	if len(capacity.Storage) != 2 || purposes[PurposeInstanceDisks] != 80 {
		t.Fatalf("storage: %+v", capacity.Storage)
	}
	if capacity.Limits.Capacity.MemoryBudgetMiB != 8192 {
		t.Fatalf("limits: %+v", capacity.Limits)
	}

	// A user's own view carries no other account's figures.
	own, err := s.Capacity(context.Background(), bob, false)
	if err != nil || own.Accounts != nil || own.Account.Instances != 1 {
		t.Fatalf("bob's view: %+v (%v)", own, err)
	}
}
