package compute

import (
	"context"
	"log/slog"
	"strings"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/seed"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/site"
)

// tierService needs no database: these tests are about the mapping from a
// caller's tier name to a pool, which is a function of site.json alone.
func tierService(disks, hdd string) *Service {
	s := sampleSite()
	s.Storage = site.Storage{VMDisks: disks, VMDisksHDD: hdd, Images: "cloud-images"}
	return New(nil, nil, nil, s, slog.New(slog.DiscardHandler), "")
}

func TestDiskTiersResolveToTheirPools(t *testing.T) {
	s := tierService("local-lvm", "bulk-disks")

	for _, tier := range []string{"", "ssd"} {
		if pool, err := s.diskTierStorage(tier); err != nil || pool != "local-lvm" {
			t.Fatalf("tier %q -> %q, %v", tier, pool, err)
		}
	}
	if pool, err := s.diskTierStorage("hdd"); err != nil || pool != "bulk-disks" {
		t.Fatalf("hdd tier -> %q, %v", pool, err)
	}
	if _, err := s.diskTierStorage("nvme"); err == nil {
		t.Fatal("an unknown tier was accepted")
	}
}

func TestADeploymentWithoutAnHDDPoolRefusesTheTier(t *testing.T) {
	s := tierService("local-lvm", "")
	_, err := s.diskTierStorage("hdd")
	if err == nil {
		t.Fatal("hdd without a pool was accepted")
	}
	refusal, ok := err.(*Error)
	if !ok || refusal.Code != "InvalidParameterValue" || !strings.Contains(refusal.Message, "no hdd") {
		t.Fatalf("unexpected refusal: %v", err)
	}
}

func TestAnInstancesTierNamesItsPool(t *testing.T) {
	s := tierService("local-lvm", "bulk-disks")

	if pool, err := s.instanceDiskStorage(db.Instance{ID: "i-x", DiskTier: "hdd"}); err != nil || pool != "bulk-disks" {
		t.Fatalf("hdd instance -> %q, %v", pool, err)
	}
	if pool, err := s.instanceDiskStorage(db.Instance{ID: "i-x", DiskTier: "ssd"}); err != nil || pool != "local-lvm" {
		t.Fatalf("ssd instance -> %q, %v", pool, err)
	}
	// A deployment that lost the pool must fail the worker with a message that
	// names the instance, not send the disk to an empty storage name.
	s.Site.Storage.VMDisksHDD = ""
	if _, err := s.instanceDiskStorage(db.Instance{ID: "i-x", DiskTier: "hdd"}); err == nil {
		t.Fatal("an instance on a missing tier was accepted")
	}
}

func TestAnHDDLaunchPutsItsDiskOnTheHDDStorage(t *testing.T) {
	s, pve, _ := testService(t)
	s.Site.Storage.VMDisksHDD = "bulk-disks"
	alice := newAccount(t, s, "alice")

	instance := run(t, s, alice, RunRequest{ImageID: "img-debian13", InstanceType: "small",
		DiskTier: "hdd", Tags: map[string]string{"Name": "bulk"}})
	if instance.DiskTier != "hdd" {
		t.Fatalf("disk tier %q, want hdd", instance.DiskTier)
	}
	work(t, s, 10)
	instance = get(t, s, instance.ID)
	if instance.State != db.StateRunning {
		t.Fatalf("state %s (%s)", instance.State, instance.LastError)
	}
	if params := pve.created[*instance.VMID]; !strings.HasPrefix(params.Get("virtio0"), "bulk-disks:") {
		t.Fatalf("virtio0 = %q", params.Get("virtio0"))
	}
}

func TestAWindowsHDDLaunchKeepsEFIAndTPMOnTheHDD(t *testing.T) {
	s, pve, _ := testService(t)
	s.Site.Storage.VMDisksHDD = "bulk-disks"
	s.Site.Images["img-win11"] = site.Image{Name: "win11", Volume: "cloud-images:import/win11.qcow2", OS: seed.OSWindows}
	alice := newAccount(t, s, "alice")

	instance := run(t, s, alice, RunRequest{ImageID: "img-win11", InstanceType: "small", DiskTier: "hdd"})
	work(t, s, 10)
	instance = get(t, s, instance.ID)
	if instance.State != db.StateRunning {
		t.Fatalf("state %s (%s)", instance.State, instance.LastError)
	}
	params := pve.created[*instance.VMID]
	for _, key := range []string{"virtio0", "efidisk0", "tpmstate0"} {
		if !strings.HasPrefix(params.Get(key), "bulk-disks:") {
			t.Fatalf("%s = %q", key, params.Get(key))
		}
	}
}

func TestLaunchesAndVolumesRefuseTheHDDTierWithoutAPool(t *testing.T) {
	s, _, _ := testService(t)
	alice := newAccount(t, s, "alice")

	if _, _, err := s.Run(context.Background(), alice, RunRequest{ImageID: "img-debian13", InstanceType: "small", DiskTier: "hdd"}, nil); code(err) != "InvalidParameterValue" {
		t.Fatalf("instance on a missing tier: %v", err)
	}
	if _, _, err := s.CreateVolume(context.Background(), alice, CreateVolumeRequest{SizeGiB: 5, DiskTier: "hdd"}, nil); code(err) != "InvalidParameterValue" {
		t.Fatalf("volume on a missing tier: %v", err)
	}
}

func TestAnHDDVolumeIsCreatedOnTheHDDStorage(t *testing.T) {
	s, pve, _ := testService(t)
	s.Site.Storage.VMDisksHDD = "bulk-disks"
	alice := newAccount(t, s, "alice")

	volume, created, err := s.CreateVolume(context.Background(), alice,
		CreateVolumeRequest{SizeGiB: 10, DiskTier: "hdd"}, nil)
	if err != nil || !created {
		t.Fatalf("CreateVolume = %v, created %v", err, created)
	}
	if volume.DiskTier != "hdd" {
		t.Fatalf("disk tier %q, want hdd", volume.DiskTier)
	}
	work(t, s, 5)
	volume = getVolume(t, s, volume.ID)
	if volume.State != db.VolumeAvailable {
		t.Fatalf("state %s (%s)", volume.State, volume.StateReason)
	}
	if !strings.HasPrefix(volume.Location.VolID, "bulk-disks:") {
		t.Fatalf("disk %q is not on the HDD pool", volume.Location.VolID)
	}
	if pve.disks[volume.Location.VolID] != 10<<30 {
		t.Fatalf("disk %s is %d bytes", volume.Location.VolID, pve.disks[volume.Location.VolID])
	}
}

func TestAdoptingAnHDDDiskRecordsTheHDDTier(t *testing.T) {
	s, pve, _ := testService(t)
	s.Site.Storage.VMDisksHDD = "bulk-disks"
	ownerID := newAccount(t, s, "alice")
	config := adoptableConfig()
	config["virtio0"] = "bulk-disks:vm-5100-disk-0,discard=on"
	addFakeVM(pve, 5100, "running", config)

	instance, err := s.Adopt(context.Background(), AdoptRequest{VMID: 5100, AccountID: ownerID}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if instance.DiskTier != "hdd" {
		t.Fatalf("adopted disk tier %q, want hdd", instance.DiskTier)
	}
}

func TestAnAttachedHDDVolumeIsLeftOutOfVMBackups(t *testing.T) {
	s, pve, _ := testService(t)
	s.Site.Storage.VMDisksHDD = "bulk-disks"
	ctx := context.Background()
	alice := newAccount(t, s, "alice")
	instance := running(t, s, alice)

	hdd, _, err := s.CreateVolume(ctx, alice, CreateVolumeRequest{SizeGiB: 10, DiskTier: "hdd"}, nil)
	if err != nil {
		t.Fatal(err)
	}
	ssd := newVolume(t, s, alice, 10)
	work(t, s, 5)
	for _, id := range []string{hdd.ID, ssd.ID} {
		if _, err := s.AttachVolume(ctx, id, instance.ID, "", ownedBy(alice), nil); err != nil {
			t.Fatal(err)
		}
		work(t, s, 5)
	}
	onHDD, _ := pve.vms[*instance.VMID].config[getVolume(t, s, hdd.ID).Device].(string)
	onSSD, _ := pve.vms[*instance.VMID].config[getVolume(t, s, ssd.ID).Device].(string)
	// The backups live on the same HDD; an SSD volume is still backed up.
	if !strings.Contains(onHDD, "backup=0") || strings.Contains(onSSD, "backup=0") || onSSD == "" {
		t.Fatalf("hdd %q, ssd %q", onHDD, onSSD)
	}
}
