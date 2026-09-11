package compute

import (
	"context"
	"strings"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

func ownedBy(accountID string) func(db.Volume) bool {
	return func(v db.Volume) bool { return v.AccountID == accountID }
}

func newVolume(t *testing.T, s *Service, accountID string, sizeGiB int) db.Volume {
	t.Helper()
	volume, created, err := s.CreateVolume(context.Background(), accountID, CreateVolumeRequest{SizeGiB: sizeGiB}, nil)
	if err != nil || !created {
		t.Fatalf("CreateVolume = %v, created %v", err, created)
	}
	return volume
}

func getVolume(t *testing.T, s *Service, id string) db.Volume {
	t.Helper()
	volume, err := db.GetVolume(context.Background(), s.Pool, id)
	if err != nil {
		t.Fatal(err)
	}
	return volume
}

func running(t *testing.T, s *Service, accountID string) db.Instance {
	t.Helper()
	instance := run(t, s, accountID, small)
	work(t, s, 10)
	if got := get(t, s, instance.ID); got.State != db.StateRunning {
		t.Fatalf("state %s (%s)", got.State, got.LastError)
	}
	return get(t, s, instance.ID)
}

// holderDisks lists the volume IDs the holder VM holds, under any key.
func holderDisks(pve *fakePVE) []string {
	pve.mu.Lock()
	defer pve.mu.Unlock()
	var volids []string
	if holder := pve.vms[5997]; holder != nil {
		for key := range holder.config {
			if volid := volidAt(holder.config, key); diskKey.MatchString(key) && pve.disks[volid] != 0 {
				volids = append(volids, key+"="+volid)
			}
		}
	}
	return volids
}

func TestAVolumeWaitsOnTheHolderAttachesGrowsAndIsDeleted(t *testing.T) {
	s, pve, _ := testService(t)
	ctx := context.Background()
	alice := newAccount(t, s, "alice")
	instance := running(t, s, alice)

	volume := newVolume(t, s, alice, 10)
	work(t, s, 5)
	volume = getVolume(t, s, volume.ID)
	l := volume.Location
	if volume.State != db.VolumeAvailable || l.VMID == nil || *l.VMID != 5997 || !strings.HasPrefix(l.ConfigKey, "unused") {
		t.Fatalf("created volume: state %s, location %+v (%s)", volume.State, l, volume.LastError)
	}
	if description, _ := pve.vms[5997].config["description"].(string); !strings.Contains(description, holderMarker) || pve.vms[5997].status != "stopped" {
		t.Fatalf("holder VM: %v", pve.vms[5997])
	}
	if pve.disks[l.VolID] != 10<<30 {
		t.Fatalf("disk %s is %d bytes", l.VolID, pve.disks[l.VolID])
	}
	pve.labels[l.VolID] = "alice's data"

	attached, err := s.AttachVolume(ctx, volume.ID, instance.ID, "", ownedBy(alice), nil)
	if err != nil || attached.Device != "virtio1" || attached.AttachmentState != db.AttachmentAttaching || attached.State != db.VolumeAvailable {
		t.Fatalf("AttachVolume = %+v, %v", attached, err)
	}
	work(t, s, 5)
	volume = getVolume(t, s, volume.ID)
	plugged, _ := pve.vms[*instance.VMID].config["virtio1"].(string)
	if volume.State != db.VolumeInUse || volume.AttachmentState != db.AttachmentAttached {
		t.Fatalf("after attach: %s/%s (%s)", volume.State, volume.AttachmentState, volume.LastError)
	}
	if !strings.Contains(plugged, "serial="+VolumeSerial(volume.ID)) || pve.labels[strings.SplitN(plugged, ",", 2)[0]] != "alice's data" {
		t.Fatalf("virtio1 = %q, labels %v", plugged, pve.labels)
	}
	if disks := holderDisks(pve); len(disks) != 0 {
		t.Fatalf("the holder still holds %v", disks)
	}

	if _, err := s.DetachVolume(ctx, volume.ID, ownedBy(alice), nil); err != nil {
		t.Fatal(err)
	}
	work(t, s, 5)
	volume = getVolume(t, s, volume.ID)
	if volume.State != db.VolumeAvailable || volume.InstanceID != "" || *volume.Location.VMID != 5997 {
		t.Fatalf("after detach: %+v", volume)
	}
	if _, stillThere := pve.vms[*instance.VMID].config["virtio1"]; stillThere || pve.labels[volume.Location.VolID] != "alice's data" {
		t.Fatalf("instance config %v, labels %v", pve.vms[*instance.VMID].config, pve.labels)
	}

	if _, err := s.ModifyVolume(ctx, volume.ID, 20, ownedBy(alice), nil); err != nil {
		t.Fatal(err)
	}
	work(t, s, 5)
	volume = getVolume(t, s, volume.ID)
	if volume.PendingAction != "" || pve.disks[volume.Location.VolID] != 20<<30 || !strings.HasPrefix(volume.Location.ConfigKey, "unused") {
		t.Fatalf("after resize: %+v, %d bytes (%s)", volume.Location, pve.disks[volume.Location.VolID], volume.LastError)
	}

	if _, err := s.DeleteVolume(ctx, volume.ID, ownedBy(alice), nil); err != nil {
		t.Fatal(err)
	}
	work(t, s, 5)
	if volume = getVolume(t, s, volume.ID); volume.State != db.VolumeDeleted || len(pve.disks) != 0 {
		t.Fatalf("after delete: %s, disks %v (%s)", volume.State, pve.disks, volume.LastError)
	}
}

func TestTerminatingAnInstanceKeepsItsVolumes(t *testing.T) {
	s, pve, _ := testService(t)
	ctx := context.Background()
	alice := newAccount(t, s, "alice")
	instance := running(t, s, alice)
	volume := newVolume(t, s, alice, 5)
	work(t, s, 5)
	pve.labels[getVolume(t, s, volume.ID).Location.VolID] = "keep me"
	if _, err := s.AttachVolume(ctx, volume.ID, instance.ID, "virtio3", ownedBy(alice), nil); err != nil {
		t.Fatal(err)
	}
	work(t, s, 5)

	if _, err := request(t, s, instance.ID, db.ActionTerminate, alice); err != nil {
		t.Fatal(err)
	}
	work(t, s, 10)
	if got := get(t, s, instance.ID); got.State != db.StateTerminated {
		t.Fatalf("instance %s (%s)", got.State, got.LastError)
	}
	volume = getVolume(t, s, volume.ID)
	if volume.State != db.VolumeAvailable || volume.InstanceID != "" || !strings.Contains(volume.StateReason, "InstanceTerminated") {
		t.Fatalf("volume after terminate: %+v", volume)
	}
	if *volume.Location.VMID != 5997 || pve.labels[volume.Location.VolID] != "keep me" {
		t.Fatalf("the data did not survive: %+v, labels %v", volume.Location, pve.labels)
	}
}

func TestAMoveThatFinishedUnrecordedIsFoundAtItsDestination(t *testing.T) {
	s, pve, _ := testService(t)
	ctx := context.Background()
	alice := newAccount(t, s, "alice")
	instance := running(t, s, alice)
	volume := newVolume(t, s, alice, 5)
	work(t, s, 5)
	volume = getVolume(t, s, volume.ID)
	pve.labels[volume.Location.VolID] = "only copy"

	// What a crash between Proxmox finishing move_disk and the ledger recording
	// it leaves: the destination written down, the disk already renamed there.
	target := *instance.VMID
	l := volume.Location
	l.MoveVMID, l.MoveKey = &target, "unused0"
	if err := db.RecordLocation(ctx, s.Pool, volume.ID, l); err != nil {
		t.Fatal(err)
	}
	if _, err := pve.MoveDisk(ctx, 5997, l.ConfigKey, target, "unused0"); err != nil {
		t.Fatal(err)
	}

	if _, err := s.AttachVolume(ctx, volume.ID, instance.ID, "", ownedBy(alice), nil); err != nil {
		t.Fatal(err)
	}
	work(t, s, 5)
	volume = getVolume(t, s, volume.ID)
	if volume.AttachmentState != db.AttachmentAttached || volume.Location.ConfigKey != "virtio1" {
		t.Fatalf("after recovery: %+v (%s)", volume, volume.LastError)
	}
	if len(pve.disks) != 1 || pve.labels[volume.Location.VolID] != "only copy" {
		t.Fatalf("disks %v, labels %v", pve.disks, pve.labels)
	}
}

func TestADetachTheGuestRefusesKeepsTrying(t *testing.T) {
	s, pve, _ := testService(t)
	ctx := context.Background()
	alice := newAccount(t, s, "alice")
	instance := running(t, s, alice)
	volume := newVolume(t, s, alice, 5)
	work(t, s, 5)
	if _, err := s.AttachVolume(ctx, volume.ID, instance.ID, "", ownedBy(alice), nil); err != nil {
		t.Fatal(err)
	}
	work(t, s, 5)

	pve.refuseUnplug = true
	s.MaxAttempts = 2
	if _, err := s.DetachVolume(ctx, volume.ID, ownedBy(alice), nil); err != nil {
		t.Fatal(err)
	}
	work(t, s, 6)
	volume = getVolume(t, s, volume.ID)
	// More attempts than MaxAttempts, and still a detach: giving up would leave
	// the disk where terminating the instance destroys it.
	if volume.PendingAction != db.VolumeActionDetach || volume.Attempts < 3 || !strings.Contains(volume.LastError, "unmount") {
		t.Fatalf("while refused: %+v", volume)
	}

	pve.mu.Lock()
	pve.refuseUnplug = false
	pve.pending = map[int][]string{}
	pve.mu.Unlock()
	work(t, s, 5)
	if volume = getVolume(t, s, volume.ID); volume.State != db.VolumeAvailable {
		t.Fatalf("after the guest let go: %+v (%s)", volume, volume.LastError)
	}
}

func TestVolumeRequestsThatCannotWorkAreRefused(t *testing.T) {
	s, _, _ := testService(t)
	ctx := context.Background()
	alice, bob := newAccount(t, s, "alice"), newAccount(t, s, "bob")

	if _, _, err := s.CreateVolume(ctx, alice, CreateVolumeRequest{SizeGiB: 51}, nil); code(err) != "InvalidParameterValue" {
		t.Fatalf("too large: %v", err)
	}
	first, created, err := s.CreateVolume(ctx, alice, CreateVolumeRequest{SizeGiB: 40, ClientToken: "one"}, nil)
	if err != nil || !created {
		t.Fatal(err)
	}
	again, created, err := s.CreateVolume(ctx, alice, CreateVolumeRequest{SizeGiB: 40, ClientToken: "one"}, nil)
	if err != nil || created || again.ID != first.ID {
		t.Fatalf("retry: %v created %v", err, created)
	}
	if _, _, err := s.CreateVolume(ctx, alice, CreateVolumeRequest{SizeGiB: 41, ClientToken: "one"}, nil); code(err) != "IdempotentParameterMismatch" {
		t.Fatalf("reused token: %v", err)
	}
	newVolume(t, s, alice, 40)
	// The sample account may hold 100 GiB of volumes.
	if _, _, err := s.CreateVolume(ctx, alice, CreateVolumeRequest{SizeGiB: 30}, nil); code(err) != "VolumeLimitExceeded" {
		t.Fatalf("over the GiB quota: %v", err)
	}
	newVolume(t, s, alice, 10)
	if _, _, err := s.CreateVolume(ctx, alice, CreateVolumeRequest{SizeGiB: 1}, nil); code(err) != "VolumeLimitExceeded" {
		t.Fatalf("over the count quota: %v", err)
	}
	work(t, s, 10)

	instance := running(t, s, alice)
	bobs := running(t, s, bob)
	if _, err := s.AttachVolume(ctx, first.ID, bobs.ID, "", ownedBy(alice), nil); code(err) != "InvalidParameterValue" {
		t.Fatalf("someone else's instance: %v", err)
	}
	if _, err := s.AttachVolume(ctx, first.ID, instance.ID, "virtio0", ownedBy(alice), nil); code(err) != "InvalidParameterValue" {
		t.Fatalf("the root disk's slot: %v", err)
	}
	if _, err := s.DetachVolume(ctx, first.ID, ownedBy(alice), nil); code(err) != "IncorrectState" {
		t.Fatalf("detach while detached: %v", err)
	}
	if _, err := s.ModifyVolume(ctx, first.ID, 20, ownedBy(alice), nil); code(err) != "InvalidParameterValue" {
		t.Fatalf("shrink: %v", err)
	}
	if _, err := s.AttachVolume(ctx, first.ID, instance.ID, "", ownedBy(bob), nil); code(err) != "InvalidVolume.NotFound" {
		t.Fatalf("attach by someone who may not: %v", err)
	}
	if _, err := s.AttachVolume(ctx, first.ID, instance.ID, "", ownedBy(alice), nil); err != nil {
		t.Fatal(err)
	}
	if _, err := s.DeleteVolume(ctx, first.ID, ownedBy(alice), nil); code(err) != "VolumeInUse" {
		t.Fatalf("delete while attaching: %v", err)
	}

	launching := run(t, s, alice, small)
	other := getVolume(t, s, again.ID)
	_ = other
	third, _, _ := s.CreateVolume(ctx, bob, CreateVolumeRequest{SizeGiB: 1}, nil)
	if _, err := s.AttachVolume(ctx, third.ID, launching.ID, "", ownedBy(bob), nil); code(err) != "InvalidParameterValue" && code(err) != "IncorrectState" {
		t.Fatalf("bob's volume on alice's launching instance: %v", err)
	}
}
