package server

import (
	"net/netip"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/netbox"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/site"
)

func TestNetworkMapPlacesHostsBySubnet(t *testing.T) {
	network := site.Network{Subnets: []site.Subnet{
		{Name: "server", Prefix: "192.168.10.0/24", Gateway: "192.168.10.1", VLANID: 10, Default: true},
		{Name: "personal", Prefix: "192.168.40.0/24", Gateway: "192.168.40.1", VLANID: 40},
		{Name: "dmz", Prefix: "192.168.30.0/24", Gateway: "192.168.30.1", VLANID: 30},
	}}
	hosts := []netbox.Host{
		{Name: "apextox", Label: "apextox", Address: netip.MustParseAddr("192.168.10.10"), Kind: "device", Status: "active"},
		{Name: "iphone", Label: "iphone", Address: netip.MustParseAddr("192.168.40.110"), Kind: "device"},
		{Name: "elsewhere", Label: "elsewhere", Address: netip.MustParseAddr("10.0.0.1"), Kind: "device"},
	}
	got := networkMap(network, hosts)
	if len(got) != 3 {
		t.Fatalf("subnets = %d", len(got))
	}
	counts := map[string]int{}
	for _, subnet := range got {
		counts[subnet.Name] = len(subnet.Hosts)
	}
	if counts["server"] != 1 || counts["personal"] != 1 || counts["dmz"] != 0 {
		t.Errorf("counts = %v", counts)
	}
	for _, subnet := range got {
		if subnet.Hosts == nil {
			t.Errorf("%s hosts is nil; the JSON must be [] not null", subnet.Name)
		}
	}
}
