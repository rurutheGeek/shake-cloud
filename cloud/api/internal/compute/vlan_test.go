package compute

import (
	"strings"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

func TestInstancesAreTaggedWithTheCloudVLANOnlyWhenOneIsSet(t *testing.T) {
	s, _, _ := testService(t)
	instance := db.Instance{ID: "i-0123456789abcdef0", MACAddress: "BC:24:11:00:00:01"}

	// The management LAN is untagged until the VLAN cut.
	if net0 := s.vmParams(instance, 5000, db.Resources{}, "img").Get("net0"); strings.Contains(net0, "tag=") {
		t.Fatalf("untagged net0 = %q", net0)
	}

	s.Site.Network.VLANID = 20
	net0 := s.vmParams(instance, 5000, db.Resources{}, "img").Get("net0")
	if !strings.Contains(net0, "tag=20") {
		t.Fatalf("tagged net0 = %q, want tag=20", net0)
	}
}
