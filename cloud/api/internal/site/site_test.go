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
		Storage: Storage{VMDisks: "local-lvm", Images: "cloud-images"},
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
