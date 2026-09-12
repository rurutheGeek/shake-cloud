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
	VolumeHolderVMID int                     `json:"volume_holder_vmid"`
	Storage          Storage                 `json:"storage"`
	Network          Network                 `json:"network"`
	Images           map[string]Image        `json:"images"`
	InstanceTypes    map[string]InstanceType `json:"instance_types"`
	Limits           Limits                  `json:"limits"`
}

type Storage struct {
	// VMDisks holds instance root disks (thin provisioned).
	VMDisks string `json:"vm_disks"`
	// Images holds shared images and per-instance seed ISOs.
	Images string `json:"images"`
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
	check(s.Storage.VMDisks != "" && s.Storage.Images != "", "site: storage names are empty")
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
	check(len(s.Images) > 0, "site: no images")
	for id, image := range s.Images {
		check(imageID.MatchString(id), "site: image ID %q does not look like img-<name>", id)
		check(image.Volume != "", "site: image %s has no volume", id)
		check(image.OS == "" || image.OS == "linux" || image.OS == "windows",
			"site: image %s has unknown os %q (use linux or windows)", id, image.OS)
	}
	check(len(s.InstanceTypes) > 0, "site: no instance types")
	for name, t := range s.InstanceTypes {
		check(t.CPUCores > 0 && t.MemoryMiB >= t.MemoryMinMiB && t.MemoryMinMiB > 0, "site: instance type %s is inconsistent", name)
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
