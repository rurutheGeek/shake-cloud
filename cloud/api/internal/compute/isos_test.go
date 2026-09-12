package compute

import (
	"context"
	"strings"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/seed"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/site"
)

func uploadISO(t *testing.T, s *Service, accountID, name, guestOS, fileName, content string) db.ISO {
	t.Helper()
	iso, err := s.ImportISO(context.Background(), accountID, name, guestOS, fileName, strings.NewReader(content), nil)
	if err != nil {
		t.Fatalf("ImportISO: %v", err)
	}
	return iso
}

func TestAnUploadedISOIsStoredAndListed(t *testing.T) {
	s, pve, _ := testService(t)
	alice := newAccount(t, s, "alice")

	iso := uploadISO(t, s, alice, "Win11 25H2", seed.OSWindows, "Win11.iso", "windows-install")
	if !strings.HasPrefix(iso.ID, "iso-") || iso.Name != "Win11 25H2" || iso.OS != seed.OSWindows {
		t.Fatalf("iso: %+v", iso)
	}
	if iso.Volume != "cloud-images:iso/"+iso.ID+".iso" {
		t.Fatalf("volume %q does not name the ISO", iso.Volume)
	}
	if iso.SizeBytes != int64(len("windows-install")) || !pve.volumes[iso.Volume] {
		t.Fatalf("size %d, stored %v", iso.SizeBytes, pve.volumes[iso.Volume])
	}

	isos, err := s.ISOs(context.Background())
	if err != nil || len(isos) != 1 || isos[0].OwnerUsername != "alice" {
		t.Fatalf("ISOs = %+v, %v", isos, err)
	}
}

func TestASharedISOIsUsedWhereItAlreadyIs(t *testing.T) {
	s, _, _ := testService(t)
	s.Site.SharedISOs = map[string]site.ISO{
		"iso-win11": {Name: "Win11", Volume: "local:iso/Win11.iso", OS: seed.OSWindows},
	}
	iso, err := s.ResolveISO(context.Background(), s.Pool, "iso-win11")
	if err != nil || !iso.Public || iso.Volume != "local:iso/Win11.iso" || iso.OS != seed.OSWindows {
		t.Fatalf("shared ISO = %+v, %v", iso, err)
	}
	isos, err := s.ISOs(context.Background())
	if err != nil || len(isos) != 1 || !isos[0].Public {
		t.Fatalf("ISOs = %+v, %v", isos, err)
	}
	// A shared ISO belongs to the administrator's storage, not the API's order.
	if err := s.DeleteISO(context.Background(), "iso-win11", nil, nil); err == nil {
		t.Fatal("a shared ISO was deletable through the API")
	}
}

func TestAnISOWithAnotherExtensionIsRefused(t *testing.T) {
	s, _, _ := testService(t)
	alice := newAccount(t, s, "alice")
	if _, err := s.ImportISO(context.Background(), alice, "not-an-iso", "", "installer.exe", strings.NewReader("x"), nil); err == nil {
		t.Fatal("an .exe was accepted as an ISO")
	}
}

func TestAnInstallVmBootsTheISOWithAnEmptyDisk(t *testing.T) {
	s, _, _ := testService(t)
	instance := db.Instance{ID: "i-0123456789abcdef0", MACAddress: "BC:24:11:00:00:01",
		RootDiskGiB: 64, GuestOS: seed.OSWindows}
	values := s.installVmParams(instance, 5000,
		db.Resources{SeedVolume: "cloud-images:iso/seed.iso"},
		"cloud-images:iso/win11.iso", "cloud-images:iso/virtio-win.iso")

	if strings.Contains(values.Get("virtio0"), "import-from") {
		t.Fatalf("the root disk is not empty: %q", values.Get("virtio0"))
	}
	if !strings.Contains(values.Get("virtio0"), "64") {
		t.Fatalf("root disk size = %q", values.Get("virtio0"))
	}
	if values.Get("ide2") != "cloud-images:iso/win11.iso,media=cdrom" ||
		values.Get("ide3") != "cloud-images:iso/virtio-win.iso,media=cdrom" ||
		values.Get("ide0") != "cloud-images:iso/seed.iso,media=cdrom" {
		t.Fatalf("CD-ROMs = %q / %q / %q", values.Get("ide0"), values.Get("ide2"), values.Get("ide3"))
	}
	if !strings.HasPrefix(values.Get("boot"), "order=ide2") {
		t.Fatalf("boot = %q, want the install ISO first", values.Get("boot"))
	}
	// guest_os=windows still selects the Windows 11 hardware.
	if values.Get("ostype") != "win11" || values.Get("bios") != "ovmf" || values.Get("tpmstate0") == "" {
		t.Fatalf("windows hardware missing: %v", values)
	}
}
