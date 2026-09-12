package compute

import (
	"strings"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/seed"
)

func TestWindowsGetsUEFITPMAndTheWindowsOSType(t *testing.T) {
	s, _, _ := testService(t)
	instance := db.Instance{ID: "i-0123456789abcdef0", MACAddress: "BC:24:11:00:00:01"}

	values := s.vmParams(instance, 5000, db.Resources{SeedVolume: "cloud-images:iso/seed.iso"},
		"cloud-images:import/win11pro.qcow2", seed.OSWindows)
	if values.Get("ostype") != "win11" || values.Get("bios") != "ovmf" || values.Get("machine") != "q35" {
		t.Fatalf("windows ostype/bios/machine = %q/%q/%q", values.Get("ostype"), values.Get("bios"), values.Get("machine"))
	}
	if !strings.Contains(values.Get("efidisk0"), "efitype=4m") || !strings.Contains(values.Get("efidisk0"), "pre-enrolled-keys=1") {
		t.Fatalf("efidisk0 = %q", values.Get("efidisk0"))
	}
	if !strings.Contains(values.Get("tpmstate0"), "version=v2.0") {
		t.Fatalf("tpmstate0 = %q", values.Get("tpmstate0"))
	}
	if values.Get("agent") != "enabled=1" {
		t.Fatalf("agent = %q", values.Get("agent"))
	}
	// The disk, NIC and seed layout stays the same as a Linux guest.
	if values.Get("virtio0") == "" || values.Get("net0") == "" || values.Get("boot") != "order=virtio0" ||
		values.Get("ide2") != "cloud-images:iso/seed.iso,media=cdrom" {
		t.Fatalf("common layout changed: %v", values)
	}

	linux := s.vmParams(instance, 5000, db.Resources{}, "img", "")
	if linux.Get("ostype") != "l26" || linux.Get("bios") != "" || linux.Get("tpmstate0") != "" || linux.Get("efidisk0") != "" {
		t.Fatalf("linux vm params = %v", linux)
	}
}
