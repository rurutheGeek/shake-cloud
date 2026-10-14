// Package site is the deployment's fixed facts and limits.
//
// The cloud_api Ansible role renders it from platform/terraform/*.yaml (site,
// pools, network, images, flavors, cloud) into one JSON file, so the API reads
// the same declarations Terraform does instead of a copy that can drift.
package site

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/netip"
	"os"
	"regexp"
)

type Site struct {
	Node       string `json:"node"`
	Pool       string `json:"pool"`
	VMIDFrom   int    `json:"vmid_from"`
	VMIDTo     int    `json:"vmid_to"`
	ProbeVMIDs []int  `json:"probe_vmids"`
	// VolumeHolderVMID is the never-started VM that owns detached volumes:
	// Proxmox keeps every disk under some VM, and only move_disk changes which.
	VolumeHolderVMID int              `json:"volume_holder_vmid"`
	Storage          Storage          `json:"storage"`
	Network          Network          `json:"network"`
	Images           map[string]Image `json:"images"`
	// SharedISOs are admin-placed ISO files the API attaches to instances as
	// CD-ROMs. They are not copied into the cloud's own store.
	SharedISOs    map[string]ISO          `json:"shared_isos"`
	InstanceTypes map[string]InstanceType `json:"instance_types"`
	Limits        Limits                  `json:"limits"`
	Ledger        Ledger                  `json:"ledger"`
}

// Ledger says how instances are registered in NetBox as virtual machines,
// which is where the Ansible inventory finds them. An empty Cluster turns
// registration off.
type Ledger struct {
	// Cluster is the NetBox cluster the VMs are filed under.
	Cluster string `json:"cluster"`
	// GroupAccounts are the account IDs whose instances may be given the tags
	// in TagsByName. Everyone else's instances are registered without them.
	GroupAccounts []string `json:"group_accounts"`
	// TagsByName maps an instance's Name tag to NetBox tag slugs. The tags
	// become Ansible groups, so this is a checked-in declaration rather than
	// something an instance can claim for itself.
	TagsByName map[string][]string `json:"tags_by_name"`
}

// ISO is a shared installation image. Volume is the Proxmox volume ID in the
// admin image store, used as-is.
type ISO struct {
	Name   string `json:"name"`
	Volume string `json:"volume"`
	OS     string `json:"os,omitempty"`
}

// Disk tiers are the names callers choose between; the pools behind them stay
// a deployment detail. TierSSD is the default and the pool of every disk made
// before tiers existed.
const (
	TierSSD = "ssd"
	TierHDD = "hdd"
)

// DiskTiers are the names the API accepts, in the order they are offered.
var DiskTiers = []string{TierSSD, TierHDD}

type Storage struct {
	// VMDisks holds instance root disks (thin provisioned).
	VMDisks string `json:"vm_disks"`
	// VMDisksHDD is the pool of the "hdd" tier, on the bulk disk. Empty when
	// this deployment has only one disk pool, and the tier is refused.
	VMDisksHDD string `json:"vm_disks_hdd,omitempty"`
	// Images holds shared images and per-instance seed ISOs.
	Images string `json:"images"`
	// AdminImages is the administrator's store. The API only lists its ISOs,
	// so an ISO dropped there from Proxmox is usable without a declaration.
	AdminImages string `json:"admin_images"`
}

// DiskTierStorage returns the pool a tier's disks live on, and whether this
// deployment has that tier. tier is "" or "ssd" for the default pool.
func (s Storage) DiskTierStorage(tier string) (string, bool) {
	switch tier {
	case "", TierSSD:
		return s.VMDisks, s.VMDisks != ""
	case TierHDD:
		return s.VMDisksHDD, s.VMDisksHDD != ""
	}
	return "", false
}

// TierOfStorage names the tier a pool belongs to. It is how an adopted VM's
// or an existing volume's tier is derived: the HDD pool is hdd, and anything
// else (including pools this deployment does not know) is the default tier.
func (s Storage) TierOfStorage(pool string) string {
	if pool != "" && pool == s.VMDisksHDD {
		return TierHDD
	}
	return TierSSD
}

type Network struct {
	Bridge  string `json:"bridge"`
	Gateway string `json:"gateway"`
	// DNSServers are handed to instances through network-config.
	DNSServers []string `json:"dns_servers"`
	// IPRangeStart identifies the NetBox IP range instances draw from, e.g. 192.168.10.100/24.
	IPRangeStart string `json:"ip_range_start"`
	// VLANID tags the NICs of instances the API creates. 0 means untagged,
	// which is how the management LAN works before the VLAN cut.
	VLANID int `json:"vlan_id"`
	// BridgeVLANAware records whether the bridge passes VLAN tags (site.yaml).
	// A tagged cloud network on a bridge that cannot carry the tag would make
	// every instance unreachable, so Load refuses it.
	BridgeVLANAware bool `json:"bridge_vlan_aware"`
	// Subnets are the segments the home network is cut into (network.yaml's
	// segments). The first one marked Default is where an instance lands when
	// a launch names none. A site.json from before subnets existed has none;
	// Subnet and SubnetList then describe the flat network above as one.
	Subnets []Subnet `json:"subnets,omitempty"`
}

// DefaultSubnet is the name of the subnet a deployment without a subnet list
// has: the one flat network.
const DefaultSubnet = "server"

// Subnet is one segment: an address range behind its own gateway. The router
// and the bridge define it; the API only reads the declaration and never
// creates or removes a segment.
type Subnet struct {
	Name    string `json:"name"`
	Prefix  string `json:"prefix"`
	Gateway string `json:"gateway"`
	// VLANID is the segment's number on the router. BridgeTag is what a NIC on
	// the hypervisor's bridge must carry to be in it: 0 when the bridge's
	// untagged side already is this segment.
	VLANID    int `json:"vlan_id"`
	BridgeTag int `json:"bridge_tag"`
	// IPRangeStart identifies the NetBox range instances draw from. Empty
	// means the API does not place instances here (the segment is for devices
	// the cloud does not create), and it is listed for reference only.
	IPRangeStart string `json:"ip_range_start,omitempty"`
	Default      bool   `json:"default,omitempty"`
	Description  string `json:"description,omitempty"`
}

// SubnetID is the identifier the API shows for a subnet. Subnets come from the
// declaration, so the name is already stable and unique.
func SubnetID(name string) string { return "subnet-" + name }

// SubnetList returns the declared subnets, or the flat network as a single
// default subnet when the deployment declares none.
func (n Network) SubnetList() []Subnet {
	if len(n.Subnets) > 0 {
		return n.Subnets
	}
	prefix := ""
	if p, err := netip.ParsePrefix(n.IPRangeStart); err == nil {
		prefix = p.Masked().String()
	}
	return []Subnet{{Name: DefaultSubnet, Prefix: prefix, Gateway: n.Gateway, BridgeTag: n.VLANID,
		VLANID: n.VLANID, IPRangeStart: n.IPRangeStart, Default: true}}
}

// Subnet resolves a name; the empty name is the default subnet.
func (n Network) Subnet(name string) (Subnet, bool) {
	for _, subnet := range n.SubnetList() {
		if (name == "" && subnet.Default) || (name != "" && subnet.Name == name) {
			return subnet, true
		}
	}
	return Subnet{}, false
}

// Launchable reports whether the API may place an instance in the subnet, and
// why not. A tagged subnet needs a bridge that passes tags; without it every
// instance there would be unreachable.
func (n Network) Launchable(subnet Subnet) (bool, string) {
	if subnet.IPRangeStart == "" {
		return false, "the cloud does not place instances in this subnet"
	}
	if subnet.BridgeTag != 0 && !n.BridgeVLANAware {
		return false, fmt.Sprintf("bridge %s is not VLAN-aware yet", n.Bridge)
	}
	return true, ""
}

// Image is a shared image. Volume is the Proxmox volume ID in Storage.Images.
// OS is "windows" for a Windows guest and empty for a Linux one; it decides the
// virtual hardware the API creates and how first-boot configuration is handed
// to the guest.
type Image struct {
	Name   string `json:"name"`
	Volume string `json:"volume"`
	OS     string `json:"os,omitempty"`
}

type InstanceType struct {
	CPUCores     int `json:"cpu_cores"`
	MemoryMiB    int `json:"memory_mib"`
	MemoryMinMiB int `json:"memory_min_mib"`
}

type Limits struct {
	AccountQuota Quota `json:"account_quota"`
	RootDiskGiB  struct {
		Min     int `json:"min"`
		Max     int `json:"max"`
		Default int `json:"default"`
	} `json:"root_disk_gib"`
	// VolumeSizeGiB bounds one volume.
	VolumeSizeGiB struct {
		Min int `json:"min"`
		Max int `json:"max"`
	} `json:"volume_size_gib"`
	Capacity struct {
		MemoryBudgetMiB      int `json:"memory_budget_mib"`
		NodeMemoryReserveMiB int `json:"node_memory_reserve_mib"`
		VMDiskMaxUsedPercent int `json:"vm_disk_max_used_percent"`
		ImageStoreMinFreeMiB int `json:"image_store_min_free_mib"`
		// MaxImageGiB bounds one uploaded image. 0 is unlimited.
		MaxImageGiB int `json:"max_image_gib"`
	} `json:"capacity"`
}

type Quota struct {
	Instances   int `json:"instances"`
	VCPUs       int `json:"vcpus"`
	MemoryMiB   int `json:"memory_mib"`
	RootDiskGiB int `json:"root_disk_gib"`
	Volumes     int `json:"volumes"`
	VolumeGiB   int `json:"volume_gib"`
}

var imageID = regexp.MustCompile(`^img-[a-z0-9-]+$`)
var ledgerAccountID = regexp.MustCompile(`^[0-9]{12}$`)
var ledgerTag = regexp.MustCompile(`^[a-z0-9][a-z0-9-]*$`)
var sharedISOID = regexp.MustCompile(`^iso-[a-z0-9-]+$`)

// Load reads and checks the rendered file. A half-rendered site is refused at
// startup rather than discovered when the first instance fails.
func Load(path string) (Site, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return Site{}, fmt.Errorf("read site: %w", err)
	}
	var s Site
	if err := json.Unmarshal(raw, &s); err != nil {
		return Site{}, fmt.Errorf("parse site %s: %w", path, err)
	}
	return s, s.Validate()
}

func (s Site) Validate() error {
	var errs []error
	check := func(ok bool, format string, args ...any) {
		if !ok {
			errs = append(errs, fmt.Errorf(format, args...))
		}
	}
	check(s.Node != "", "site: node is empty")
	check(s.Pool != "", "site: pool is empty")
	check(s.VMIDFrom >= 100 && s.VMIDTo > s.VMIDFrom, "site: bad VMID range %d-%d", s.VMIDFrom, s.VMIDTo)
	check(s.Storage.VMDisks != "" && s.Storage.Images != "" && s.Storage.AdminImages != "", "site: storage names are empty")
	check(s.Storage.VMDisksHDD == "" || (s.Storage.VMDisksHDD != s.Storage.VMDisks &&
		s.Storage.VMDisksHDD != s.Storage.Images && s.Storage.VMDisksHDD != s.Storage.AdminImages),
		"site: storage.vm_disks_hdd %q collides with another store", s.Storage.VMDisksHDD)
	check(s.Network.Bridge != "", "site: bridge is empty")
	_, err := netip.ParseAddr(s.Network.Gateway)
	check(err == nil, "site: gateway %q is not an address", s.Network.Gateway)
	for _, server := range s.Network.DNSServers {
		_, err := netip.ParseAddr(server)
		check(err == nil, "site: DNS server %q is not an address", server)
	}
	_, err = netip.ParsePrefix(s.Network.IPRangeStart)
	check(err == nil, "site: ip_range_start %q is not a prefix", s.Network.IPRangeStart)
	check(s.Network.VLANID >= 0 && s.Network.VLANID <= 4094, "site: vlan_id %d is not a VLAN id", s.Network.VLANID)
	check(s.Network.VLANID == 0 || s.Network.BridgeVLANAware,
		"site: vlan_id %d is set but bridge %s is not VLAN-aware; make it vlan-aware first (docs/operations/vlan.md)",
		s.Network.VLANID, s.Network.Bridge)
	defaults, seen := 0, map[string]bool{}
	for _, subnet := range s.Network.Subnets {
		check(subnet.Name != "" && !seen[subnet.Name], "site: subnet name %q is empty or repeated", subnet.Name)
		seen[subnet.Name] = true
		prefix, err := netip.ParsePrefix(subnet.Prefix)
		check(err == nil, "site: subnet %s prefix %q is not a prefix", subnet.Name, subnet.Prefix)
		gateway, gwErr := netip.ParseAddr(subnet.Gateway)
		check(gwErr == nil && (err != nil || prefix.Contains(gateway)),
			"site: subnet %s gateway %q is not an address inside %s", subnet.Name, subnet.Gateway, subnet.Prefix)
		check(subnet.BridgeTag >= 0 && subnet.BridgeTag <= 4094, "site: subnet %s bridge_tag %d is not a VLAN id", subnet.Name, subnet.BridgeTag)
		if subnet.IPRangeStart != "" {
			start, rangeErr := netip.ParsePrefix(subnet.IPRangeStart)
			check(rangeErr == nil && (err != nil || prefix.Contains(start.Addr())),
				"site: subnet %s ip_range_start %q is not inside %s", subnet.Name, subnet.IPRangeStart, subnet.Prefix)
		}
		if subnet.Default {
			defaults++
			// The default subnet is where every existing instance lives. If it
			// could not be launched into, the API would be up and useless.
			ok, reason := s.Network.Launchable(subnet)
			check(ok, "site: default subnet %s cannot take instances: %s", subnet.Name, reason)
		}
	}
	check(len(s.Network.Subnets) == 0 || defaults == 1, "site: exactly one subnet must be the default, found %d", defaults)
	check(len(s.Images) > 0, "site: no images")
	for id, image := range s.Images {
		check(imageID.MatchString(id), "site: image ID %q does not look like img-<name>", id)
		check(image.Volume != "", "site: image %s has no volume", id)
		check(image.OS == "" || image.OS == "linux" || image.OS == "windows",
			"site: image %s has unknown os %q (use linux or windows)", id, image.OS)
	}
	for id, iso := range s.SharedISOs {
		check(sharedISOID.MatchString(id), "site: shared ISO ID %q does not look like iso-<name>", id)
		check(iso.Volume != "", "site: shared ISO %s has no volume", id)
		check(iso.OS == "" || iso.OS == "linux" || iso.OS == "windows",
			"site: shared ISO %s has unknown os %q", id, iso.OS)
	}
	check(len(s.InstanceTypes) > 0, "site: no instance types")
	for name, t := range s.InstanceTypes {
		check(t.CPUCores > 0 && t.MemoryMiB >= t.MemoryMinMiB && t.MemoryMinMiB > 0, "site: instance type %s is inconsistent", name)
	}
	check(s.Ledger.Cluster != "" || (len(s.Ledger.GroupAccounts) == 0 && len(s.Ledger.TagsByName) == 0),
		"site: ledger groups are declared but ledger.cluster is empty")
	for _, account := range s.Ledger.GroupAccounts {
		check(ledgerAccountID.MatchString(account), "site: ledger account %q is not a 12-digit account ID", account)
	}
	for name, tags := range s.Ledger.TagsByName {
		check(name != "" && len(tags) > 0, "site: ledger entry %q has no tags", name)
		for _, tag := range tags {
			check(ledgerTag.MatchString(tag), "site: ledger tag %q for %s is not a NetBox tag slug", tag, name)
		}
	}
	q, r, c := s.Limits.AccountQuota, s.Limits.RootDiskGiB, s.Limits.Capacity
	check(q.Instances > 0 && q.VCPUs > 0 && q.MemoryMiB > 0 && q.RootDiskGiB > 0, "site: account quota must be positive")
	check(r.Min > 0 && r.Min <= r.Default && r.Default <= r.Max, "site: root disk limits %d <= %d <= %d do not hold", r.Min, r.Default, r.Max)
	check(c.MemoryBudgetMiB > 0 && c.VMDiskMaxUsedPercent > 0 && c.VMDiskMaxUsedPercent <= 100, "site: capacity limits are unset")
	v := s.Limits.VolumeSizeGiB
	check(q.Volumes > 0 && q.VolumeGiB > 0, "site: volume quota must be positive")
	check(v.Min > 0 && v.Min <= v.Max, "site: volume size limits %d <= %d do not hold", v.Min, v.Max)
	check(s.VolumeHolderVMID >= s.VMIDFrom && s.VolumeHolderVMID <= s.VMIDTo,
		"site: volume holder VMID %d is outside %d-%d", s.VolumeHolderVMID, s.VMIDFrom, s.VMIDTo)
	for _, probe := range s.ProbeVMIDs {
		check(probe != s.VolumeHolderVMID, "site: volume holder VMID %d is also a probe VMID", probe)
	}
	return errors.Join(errs...)
}

// ReservedVMID reports whether the allocator must skip vmid.
func (s Site) ReservedVMID(vmid int) bool {
	if vmid == s.VolumeHolderVMID {
		return true
	}
	for _, probe := range s.ProbeVMIDs {
		if probe == vmid {
			return true
		}
	}
	return false
}
