package netbox

import (
	"context"
	"net/http"
	"net/netip"
	"sort"
)

// Host is one addressed machine in the ledger: a physical device or a VM.
type Host struct {
	// Name is the ledger name (a cloud VM's is its instance ID); Label is what
	// people call it, the address's DNS name when there is one.
	Name    string
	Label   string
	Address netip.Addr
	Kind    string // "device" or "vm"
	Status  string // NetBox status: active, offline, planned, ...
}

type hostAddress struct {
	Address            string `json:"address"`
	DNSName            string `json:"dns_name"`
	AssignedObjectType string `json:"assigned_object_type"`
	AssignedObject     *struct {
		Device *struct {
			Name string `json:"name"`
		} `json:"device"`
		VirtualMachine *struct {
			Name string `json:"name"`
		} `json:"virtual_machine"`
	} `json:"assigned_object"`
}

type statusPage struct {
	Results []struct {
		Name   string `json:"name"`
		Status struct {
			Value string `json:"value"`
		} `json:"status"`
	} `json:"results"`
}

// Hosts lists every machine that holds an address, sorted by address. A
// machine with several addresses is listed once, at its lowest.
func (c *Client) Hosts(ctx context.Context) ([]Host, error) {
	var addresses page[hostAddress]
	if err := c.do(ctx, http.MethodGet, "/ipam/ip-addresses/?limit=1000&family=4", nil, &addresses); err != nil {
		return nil, err
	}
	status := map[string]string{}
	for _, path := range []string{"/dcim/devices/?limit=1000", "/virtualization/virtual-machines/?limit=1000"} {
		var items statusPage
		if err := c.do(ctx, http.MethodGet, path, nil, &items); err != nil {
			return nil, err
		}
		for _, item := range items.Results {
			status[item.Name] = item.Status.Value
		}
	}
	return hostsFrom(addresses.Results, status), nil
}

func hostsFrom(addresses []hostAddress, status map[string]string) []Host {
	hosts := []Host{}
	for _, entry := range addresses {
		prefix, err := netip.ParsePrefix(entry.Address)
		if err != nil || entry.AssignedObject == nil {
			continue
		}
		host := Host{Address: prefix.Addr(), Label: entry.DNSName}
		switch {
		case entry.AssignedObject.VirtualMachine != nil:
			host.Name, host.Kind = entry.AssignedObject.VirtualMachine.Name, "vm"
		case entry.AssignedObject.Device != nil:
			host.Name, host.Kind = entry.AssignedObject.Device.Name, "device"
		default:
			continue
		}
		if host.Label == "" {
			host.Label = host.Name
		}
		host.Status = status[host.Name]
		hosts = append(hosts, host)
	}
	sort.Slice(hosts, func(i, j int) bool { return hosts[i].Address.Less(hosts[j].Address) })
	seen := map[string]bool{}
	unique := hosts[:0]
	for _, host := range hosts {
		if !seen[host.Kind+"/"+host.Name] {
			seen[host.Kind+"/"+host.Name] = true
			unique = append(unique, host)
		}
	}
	return unique
}
