package compute

import (
	"context"
	"strings"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/proxmox"
)

func upload(t *testing.T, s *Service, accountID, name, fileName, content string) db.Image {
	t.Helper()
	image, err := s.ImportImage(context.Background(), accountID, name, fileName, strings.NewReader(content), nil)
	if err != nil {
		t.Fatalf("ImportImage: %v", err)
	}
	return image
}

func TestAnUploadedImageIsStoredAndCanBeLaunchedFrom(t *testing.T) {
	s, pve, _ := testService(t)
	alice := newAccount(t, s, "alice")

	image := upload(t, s, alice, "ubuntu 24.04", "noble.qcow2", "0123456789")
	if !strings.HasPrefix(image.ID, "img-") || image.Name != "ubuntu 24.04" {
		t.Fatalf("image: %+v", image)
	}
	if image.Volume != "cloud-images:import/"+image.ID+".qcow2" {
		t.Fatalf("volume %q does not name the image", image.Volume)
	}
	// The size and format are what the store reported, not what we guessed.
	if image.SizeBytes != 10 || image.Format != "qcow2" {
		t.Fatalf("size %d format %q", image.SizeBytes, image.Format)
	}
	if !pve.volumes[image.Volume] {
		t.Fatal("the file is not in the store")
	}

	// It is listed alongside the deployment's shared images.
	images, err := s.Images(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	var shared, uploaded int
	for _, listed := range images {
		if listed.Public {
			shared++
		} else if listed.ID == image.ID {
			uploaded++
			if listed.OwnerUsername != "alice" {
				t.Errorf("uploader not named: %+v", listed)
			}
		}
	}
	if shared != 1 || uploaded != 1 {
		t.Fatalf("listing has %d shared and %d uploaded", shared, uploaded)
	}

	// A launch from it copies that volume into the instance's disk. The node
	// replaces virtio0 with the disk it created, so the creation parameter is
	// where the import actually shows.
	instance := run(t, s, alice, RunRequest{ImageID: image.ID, VCPUs: ptr(2), MemoryMiB: ptr(2048)})
	work(t, s, 5)
	if got := get(t, s, instance.ID); got.State != db.StateRunning {
		t.Fatalf("instance state %s (%s)", got.State, got.LastError)
	}
	requested := pve.created[*instance.VMID].Get("virtio0")
	if !strings.Contains(requested, "import-from="+image.Volume) {
		t.Fatalf("virtio0 was %q, not made from the uploaded image", requested)
	}
}

func TestUploadsAreRefusedBeforeTheyFillTheStore(t *testing.T) {
	s, pve, _ := testService(t)
	alice := newAccount(t, s, "alice")

	for name, tc := range map[string]struct{ imageName, fileName, code string }{
		"a file that is not a disk image": {"notes", "notes.txt", "InvalidParameterValue"},
		"no name":                         {"  ", "disk.qcow2", "InvalidParameterValue"},
	} {
		_, err := s.ImportImage(context.Background(), alice, tc.imageName, tc.fileName, strings.NewReader("x"), nil)
		if code(err) != tc.code {
			t.Errorf("%s: %v", name, err)
		}
	}

	// Only 1 MiB may be used once the 2 GiB reserve is honoured, so 2 MiB stops
	// mid-stream rather than being discovered after it is written.
	pve.storage["cloud-images"] = proxmox.StorageStatus{Total: 100 << 30, Used: 0, Avail: (2048 + 1) << 20}
	_, err := s.ImportImage(context.Background(), alice, "big", "big.qcow2", strings.NewReader(strings.Repeat("x", 2<<20)), nil)
	if code(err) != "RequestEntityTooLarge" {
		t.Fatalf("oversize upload: %v", err)
	}

	// With the store already inside its reserve, nothing is accepted at all.
	pve.storage["cloud-images"] = proxmox.StorageStatus{Total: 100 << 30, Used: 100 << 30, Avail: 1 << 20}
	if _, err := s.ImportImage(context.Background(), alice, "any", "any.qcow2", strings.NewReader("x"), nil); code(err) != "ImageLimitExceeded" {
		t.Fatalf("store full: %v", err)
	}
}

func TestDeletingAnImageRespectsOwnershipAndLaunchesInFlight(t *testing.T) {
	s, pve, _ := testService(t)
	alice, bob := newAccount(t, s, "alice"), newAccount(t, s, "bob")
	image := upload(t, s, alice, "mine", "mine.qcow2", "0123456789")
	mine := func(i db.Image) bool { return i.AccountID == alice }

	// The deployment's shared images are Terraform's, not the API's.
	if err := s.DeleteImage(context.Background(), "img-debian13", func(db.Image) bool { return true }, nil); code(err) != "ImageLimitExceeded" {
		t.Fatalf("shared image: %v", err)
	}
	// Someone else's upload is refused, and says so.
	if err := s.DeleteImage(context.Background(), image.ID, func(i db.Image) bool { return i.AccountID == bob }, nil); code(err) != "UnauthorizedOperation" {
		t.Fatalf("another account: %v", err)
	}
	// While a launch is still copying from it, it stays.
	instance := run(t, s, alice, RunRequest{ImageID: image.ID, VCPUs: ptr(2), MemoryMiB: ptr(2048)})
	if err := s.DeleteImage(context.Background(), image.ID, mine, nil); code(err) != "IncorrectInstanceState" {
		t.Fatalf("launch in flight: %v", err)
	}
	work(t, s, 5)
	if got := get(t, s, instance.ID); got.State != db.StateRunning {
		t.Fatalf("instance state %s (%s)", got.State, got.LastError)
	}
	// Once the disk has been copied, the image can go and the VM is unaffected.
	if err := s.DeleteImage(context.Background(), image.ID, mine, nil); err != nil {
		t.Fatal(err)
	}
	if pve.volumes[image.Volume] {
		t.Fatal("the file is still in the store")
	}
	if _, err := db.GetImage(context.Background(), s.Pool, image.ID); err == nil {
		t.Fatal("the row is still there")
	}
	if pve.vms[*instance.VMID] == nil {
		t.Fatal("deleting the image removed the VM")
	}
	// A launch naming it now fails admission rather than half-creating a VM.
	if _, _, err := s.Run(context.Background(), alice, RunRequest{ImageID: image.ID, VCPUs: ptr(1), MemoryMiB: ptr(512)}, nil); code(err) != "InvalidImageID.NotFound" {
		t.Fatalf("launch from a deleted image: %v", err)
	}
}
