package site

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// sample is a complete site as the cloud_api role renders it.
func sample() Site {
	s := Site{
		Node: "apextox", Pool: "cloud", VMIDFrom: 5000, VMIDTo: 5999, ProbeVMIDs: []int{5998, 5999}, VolumeHolderVMID: 5997,
		Storage: Storage{VMDisks: "local-lvm", Images: "cloud-images", AdminImages: "local"},
		Network: Network{Bridge: "vmbr0", Gateway: "192.168.10.1", DNSServers: []string{"192.168.10.1"}, IPRangeStart: "192.168.10.100/24"},
		Images:  map[string]Image{"img-debian13": {Name: "debian13", Volume: "cloud-images:import/debian-13.qcow2"}},
		InstanceTypes: map[string]InstanceType{
			"small":  {CPUCores: 2, MemoryMiB: 2048, MemoryMinMiB: 512},
			"medium": {CPUCores: 2, MemoryMiB: 4096, MemoryMinMiB: 1024},
		},
	}
	s.Limits.AccountQuota = Quota{Instances: 4, VCPUs: 8, MemoryMiB: 8192, RootDiskGiB: 200, Volumes: 16, VolumeGiB: 1000}
	s.Limits.RootDiskGiB.Min, s.Limits.RootDiskGiB.Default, s.Limits.RootDiskGiB.Max = 10, 20, 100
	s.Limits.VolumeSizeGiB.Min, s.Limits.VolumeSizeGiB.Max = 1, 500
	s.Limits.Capacity.MemoryBudgetMiB = 8192
	s.Limits.Capacity.NodeMemoryReserveMiB = 4096
	s.Limits.Capacity.VMDiskMaxUsedPercent = 80
	s.Limits.Capacity.ImageStoreMinFreeMiB = 2048
	return s
}

func TestAnExampleSiteLoads(t *testing.T) {
	raw, _ := json.Marshal(sample())
	path := filepath.Join(t.TempDir(), "site.json")
	if err := os.WriteFile(path, raw, 0o600); err != nil {
		t.Fatal(err)
	}
	s, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if !s.ReservedVMID(5999) || s.ReservedVMID(5000) {
		t.Fatal("probe VMIDs are not reserved")
	}
	// The allocator must never hand out the VM that holds detached volumes.
	if !s.ReservedVMID(5997) {
		t.Fatal("the volume holder VMID is not reserved")
	}
}

func TestAVolumeHolderOutsideThePoolOrOnAProbeIsRefused(t *testing.T) {
	for _, holder := range []int{4000, 5999} {
		s := sample()
		s.VolumeHolderVMID = holder
		if err := s.Validate(); err == nil || !strings.Contains(err.Error(), "volume holder") {
			t.Fatalf("holder %d: %v", holder, err)
		}
	}
}

func TestDiskTiersMapToTheirPools(t *testing.T) {
	s := sample()
	s.Storage.VMDisksHDD = "bulk-disks"
	for _, tier := range []string{"", TierSSD} {
		if pool, ok := s.Storage.DiskTierStorage(tier); !ok || pool != "local-lvm" {
			t.Fatalf("tier %q -> %q, %v", tier, pool, ok)
		}
	}
	if pool, ok := s.Storage.DiskTierStorage(TierHDD); !ok || pool != "bulk-disks" {
		t.Fatalf("hdd tier -> %q, %v", pool, ok)
	}
	if _, ok := s.Storage.DiskTierStorage("nvme"); ok {
		t.Fatal("an unknown tier was accepted")
	}
	// A disk on a pool this deployment does not know is the default tier: the
	// label matters, not where an adopted VM's disk sat.
	if s.Storage.TierOfStorage("some-old-pool") != TierSSD {
		t.Fatal("an unknown pool was not the default tier")
	}
	if s.Storage.TierOfStorage("bulk-disks") != TierHDD {
		t.Fatal("the HDD pool was not the hdd tier")
	}

	s.Storage.VMDisksHDD = ""
	if _, ok := s.Storage.DiskTierStorage(TierHDD); ok {
		t.Fatal("a deployment without an HDD pool offered the tier")
	}
}

func TestTheHDDPoolCannotCollideWithAnotherStore(t *testing.T) {
	for _, pool := range []string{"local-lvm", "cloud-images", "local"} {
		s := sample()
		s.Storage.VMDisksHDD = pool
		if err := s.Validate(); err == nil || !strings.Contains(err.Error(), "vm_disks_hdd") {
			t.Fatalf("pool %q: %v", pool, err)
		}
	}
}

func TestEveryProblemIsReported(t *testing.T) {
	s := sample()
	s.Network.Gateway = "gateway"
	s.Images = map[string]Image{"debian": {}}
	s.Limits.RootDiskGiB.Default = 200
	err := s.Validate()
	if err == nil {
		t.Fatal("broken site accepted")
	}
	for _, want := range []string{"gateway", "img-<name>", "no volume", "root disk"} {
		if !strings.Contains(err.Error(), want) {
			t.Errorf("error does not mention %q: %v", want, err)
		}
	}
}
