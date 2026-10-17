package compute

import (
	"strings"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/site"
)

func TestInstancesAreTaggedWithTheCloudVLANOnlyWhenOneIsSet(t *testing.T) {
	s, _, _ := testService(t)
	instance := db.Instance{ID: "i-0123456789abcdef0", MACAddress: "BC:24:11:00:00:01"}

	// The management LAN is untagged until the VLAN cut.
	if net0 := s.vmParams(instance, 5000, db.Resources{}, "img", "", "local-lvm").Get("net0"); strings.Contains(net0, "tag=") {
		t.Fatalf("untagged net0 = %q", net0)
	}

	s.Site.Network.VLANID = 20
	net0 := s.vmParams(instance, 5000, db.Resources{}, "img", "", "local-lvm").Get("net0")
	if !strings.Contains(net0, "tag=20") {
		t.Fatalf("tagged net0 = %q, want tag=20", net0)
	}
}

func TestAnInstanceIsWiredIntoItsOwnSubnet(t *testing.T) {
	s, _, _ := testService(t)
	s.Site.Network.BridgeVLANAware = true
	s.Site.Network.Subnets = []site.Subnet{
		{Name: "server", Prefix: "192.168.10.0/24", Gateway: "192.168.10.1", VLANID: 10, IPRangeStart: "192.168.10.100/24", Default: true},
		{Name: "dmz", Prefix: "192.168.30.0/24", Gateway: "192.168.30.1", VLANID: 30, BridgeTag: 30, IPRangeStart: "192.168.30.100/24"},
		{Name: "iot", Prefix: "192.168.50.0/24", Gateway: "192.168.50.1", VLANID: 50},
	}
	instance := db.Instance{ID: "i-0123456789abcdef0", MACAddress: "BC:24:11:00:00:01"}

	// The server segment is the bridge's untagged side, VLAN number or not.
	if net0 := s.vmParams(instance, 5000, db.Resources{}, "img", "", "local-lvm").Get("net0"); strings.Contains(net0, "tag=") {
		t.Fatalf("default subnet net0 = %q, want untagged", net0)
	}
	instance.Subnet = "dmz"
	if net0 := s.vmParams(instance, 5000, db.Resources{}, "img", "", "local-lvm").Get("net0"); !strings.Contains(net0, "tag=30") {
		t.Fatalf("dmz net0 = %q, want tag=30", net0)
	}
	if gateway := s.instanceSubnet(instance).Gateway; gateway != "192.168.30.1" {
		t.Fatalf("dmz gateway = %s", gateway)
	}

	// A segment that was renamed away must not strand the instance.
	instance.Subnet = "gone"
	if name := s.instanceSubnet(instance).Name; name != "server" {
		t.Fatalf("unknown subnet resolved to %q, want the default", name)
	}
}

func TestALaunchIsRefusedForASubnetThatCannotTakeInstances(t *testing.T) {
	s, _, _ := testService(t)
	s.Site.Network.Subnets = []site.Subnet{
		{Name: "server", Prefix: "192.168.10.0/24", Gateway: "192.168.10.1", IPRangeStart: "192.168.10.100/24", Default: true},
		{Name: "dmz", Prefix: "192.168.30.0/24", Gateway: "192.168.30.1", VLANID: 30, BridgeTag: 30, IPRangeStart: "192.168.30.100/24"},
		{Name: "iot", Prefix: "192.168.50.0/24", Gateway: "192.168.50.1", VLANID: 50},
	}
	for id, want := range map[string]string{
		"":              "",
		"subnet-server": "",
		// Tagged, and the bridge does not pass tags yet.
		"subnet-dmz": "InvalidSubnet.NotLaunchable",
		// The cloud never places instances among the appliances.
		"subnet-iot":  "InvalidSubnet.NotLaunchable",
		"subnet-nope": "InvalidSubnetID.NotFound",
		"dmz":         "InvalidParameterValue",
	} {
		_, err := s.launchSubnet(id)
		got := ""
		if refusal, ok := err.(*Error); ok {
			got = refusal.Code
		} else if err != nil {
			t.Fatalf("%q: unexpected error %v", id, err)
		}
		if got != want {
			t.Errorf("launchSubnet(%q) = %q, want %q", id, got, want)
		}
	}

	s.Site.Network.BridgeVLANAware = true
	if _, err := s.launchSubnet("subnet-dmz"); err != nil {
		t.Fatalf("dmz on a VLAN-aware bridge: %v", err)
	}
}
