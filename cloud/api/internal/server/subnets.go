package server

import (
	"net/http"
	"strings"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/site"
)

type subnetBody struct {
	SubnetID  string `json:"subnet_id"`
	Name      string `json:"name"`
	CIDRBlock string `json:"cidr_block"`
	Gateway   string `json:"gateway"`
	VLANID    int    `json:"vlan_id"`
	Default   bool   `json:"default"`
	// Launchable is false for a subnet the cloud does not place instances in,
	// or cannot yet; StateReason says which.
	Launchable  bool   `json:"launchable"`
	StateReason string `json:"state_reason,omitempty"`
	Description string `json:"description,omitempty"`
}

func subnetJSON(network site.Network, subnet site.Subnet) subnetBody {
	launchable, reason := network.Launchable(subnet)
	return subnetBody{
		SubnetID: site.SubnetID(subnet.Name), Name: subnet.Name, CIDRBlock: subnet.Prefix,
		Gateway: subnet.Gateway, VLANID: subnet.VLANID, Default: subnet.Default,
		Launchable: launchable, StateReason: reason, Description: subnet.Description,
	}
}

// describeSubnets lists the segments of the home network. They come from the
// deployment's declaration: the router and the bridge define a segment, so the
// API has no call that creates or removes one.
func (s *Server) describeSubnets(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	network := service.Site.Network
	body := make([]subnetBody, 0, len(network.SubnetList()))
	for _, subnet := range network.SubnetList() {
		body = append(body, subnetJSON(network, subnet))
	}
	writeJSON(w, http.StatusOK, map[string]any{"subnets": body})
}

func (s *Server) describeSubnet(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	id := r.PathValue("subnet_id")
	name, ok := strings.CutPrefix(id, "subnet-")
	subnet, found := service.Site.Network.Subnet(name)
	if !ok || name == "" || !found {
		writeError(w, r, http.StatusNotFound, "InvalidSubnetID.NotFound", "subnet "+id+" does not exist")
		return
	}
	writeJSON(w, http.StatusOK, subnetJSON(service.Site.Network, subnet))
}
