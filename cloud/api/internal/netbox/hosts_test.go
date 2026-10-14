package netbox

import (
	"encoding/json"
	"testing"
)

func TestHostsFromNamesVMsByDNSAndKeepsOneAddressEach(t *testing.T) {
	var addresses []hostAddress
	raw := `[
	  {"address":"192.168.10.105/24","dns_name":"apps-01","assigned_object_type":"virtualization.vminterface","assigned_object":{"virtual_machine":{"name":"i-45384ba60468699f2"}}},
	  {"address":"192.168.10.10/24","dns_name":"","assigned_object_type":"dcim.interface","assigned_object":{"device":{"name":"apextox"}}},
	  {"address":"192.168.10.20/24","dns_name":"","assigned_object_type":"dcim.interface","assigned_object":{"device":{"name":"apextox"}}},
	  {"address":"192.168.10.50/24","dns_name":"loose","assigned_object":null}
	]`
	if err := json.Unmarshal([]byte(raw), &addresses); err != nil {
		t.Fatal(err)
	}
	hosts := hostsFrom(addresses, map[string]string{"apextox": "active", "i-45384ba60468699f2": "offline"})
	if len(hosts) != 2 {
		t.Fatalf("hosts = %+v", hosts)
	}
	if hosts[0].Name != "apextox" || hosts[0].Address.String() != "192.168.10.10" || hosts[0].Kind != "device" || hosts[0].Label != "apextox" {
		t.Errorf("first = %+v", hosts[0])
	}
	if hosts[1].Label != "apps-01" || hosts[1].Kind != "vm" || hosts[1].Status != "offline" {
		t.Errorf("second = %+v", hosts[1])
	}
}
