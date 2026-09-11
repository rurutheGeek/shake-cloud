package compute

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/netip"
	"slices"
	"strconv"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

// Adoption registers a VM that already exists, after an administrator has moved
// it into the cloud pool. It cannot be launched or re-created, so the ledger
// keeps no source image, user-data or seed image for it; the adopted flag is
// what lets the rest of the code treat it as one of ours.

type AdoptRequest struct {
	// VMID is the existing Proxmox VM to take over. It must already be in the
	// cloud pool, because that is the only part of Proxmox this token can see.
	VMID int `json:"vmid"`
	// AccountID is the owner the administrator chooses for it.
	AccountID string `json:"account_id"`
	// Name is the display name; omitted means the VM's own name.
	Name string `json:"name"`
	// PrivateIPAddress is optional. Security groups filter by address, so an
	// instance with no address cannot be filtered; give it if the VM has a
	// known static address.
	PrivateIPAddress string `json:"private_ip_address"`
	// RootDiskGiB is optional; omitted means it is measured from storage.
	RootDiskGiB      int               `json:"root_disk_gib"`
	Tags             map[string]string `json:"tags"`
	SecurityGroupIDs []string          `json:"security_group_ids,omitempty"`
}

// Adopt takes an existing cloud-pool VM into the ledger under ownerID.
func (s *Service) Adopt(ctx context.Context, r AdoptRequest, audit func(pgx.Tx, db.Instance) error) (db.Instance, error) {
	bad := func(format string, args ...any) error {
		return refuse(http.StatusBadRequest, "InvalidParameterValue", format, args...)
	}
	switch {
	case r.VMID <= 0:
		return db.Instance{}, bad("vmid is required")
	case r.VMID == s.Site.VolumeHolderVMID || slices.Contains(s.Site.ProbeVMIDs, r.VMID):
		return db.Instance{}, bad("vmid %d is reserved by the cloud", r.VMID)
	case r.AccountID == "":
		return db.Instance{}, bad("account_id is required; an administrator chooses the owner")
	}
	if err := validateTags(r.Tags); err != nil {
		return db.Instance{}, err
	}
	if r.PrivateIPAddress != "" {
		_, prefixErr := netip.ParsePrefix(r.PrivateIPAddress)
		_, addrErr := netip.ParseAddr(r.PrivateIPAddress)
		if prefixErr != nil && addrErr != nil {
			return db.Instance{}, bad("private_ip_address %q is not an address or a CIDR", r.PrivateIPAddress)
		}
	}
	owner, err := db.GetAccount(ctx, s.Pool, r.AccountID)
	if errors.Is(err, db.ErrNotFound) {
		return db.Instance{}, bad("account %s does not exist", r.AccountID)
	}
	if err != nil {
		return db.Instance{}, err
	}

	// ListVMs only shows the pool; a VM outside it is not ours to register.
	vms, err := s.PVE.ListVMs(ctx)
	if err != nil {
		return db.Instance{}, s.unavailable(err)
	}
	if findVM(vms, r.VMID) == nil {
		return db.Instance{}, refuse(http.StatusNotFound, "InvalidInstanceID.NotFound",
			"VM %d is not in pool %s; move it there first, then adopt it", r.VMID, s.Site.Pool)
	}
	if existing, err := db.LiveInstanceByVMID(ctx, s.Pool, r.VMID); err == nil {
		return db.Instance{}, refuse(http.StatusConflict, "InvalidParameterValue",
			"VM %d is already instance %s", r.VMID, existing.ID)
	} else if !errors.Is(err, db.ErrNotFound) {
		return db.Instance{}, err
	}

	config, err := s.PVE.VMConfig(ctx, r.VMID)
	if err != nil {
		return db.Instance{}, s.unavailable(err)
	}
	status, err := s.PVE.VMStatus(ctx, r.VMID)
	if err != nil {
		return db.Instance{}, s.unavailable(err)
	}
	state, ok := map[string]string{"running": db.StateRunning, "stopped": db.StateStopped}[status]
	if !ok {
		return db.Instance{}, refuse(http.StatusConflict, "IncorrectInstanceState",
			"VM %d is %q; a running or stopped VM can be adopted", r.VMID, status)
	}
	mac := macFromNet0(config)
	if mac == "" {
		return db.Instance{}, bad("VM %d has no net0 MAC address to record", r.VMID)
	}
	name := r.Name
	if name == "" {
		name = configString(config, "name")
	}
	if name == "" {
		name = r.Tags["Name"]
	}
	cores := configIntOr(config, "cores", 1)
	memoryMiB := configIntOr(config, "memory", minMemoryMiB)
	balloon := configIntOr(config, "balloon", 0)
	ballooning := balloon > 0
	memoryMinMiB := 0
	if ballooning {
		memoryMinMiB = balloon
	}
	rootDisk := r.RootDiskGiB
	if rootDisk <= 0 {
		volid := firstDiskVolid(config)
		if volid == "" {
			return db.Instance{}, bad("VM %d has no disk to measure; pass root_disk_gib", r.VMID)
		}
		size, found, err := s.diskSizeGiB(ctx, volid)
		if err != nil {
			return db.Instance{}, s.unavailable(err)
		}
		if !found {
			return db.Instance{}, bad("could not read the size of %s; pass root_disk_gib", volid)
		}
		rootDisk = size
	}
	limits, _, err := s.EffectiveLimits(ctx, s.Pool)
	if err != nil {
		return db.Instance{}, err
	}

	var instance db.Instance
	err = pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		if err := db.LockCapacity(ctx, tx); err != nil {
			return err
		}
		if other, err := db.LiveInstanceByVMID(ctx, tx, r.VMID); err == nil {
			return refuse(http.StatusConflict, "InvalidParameterValue", "VM %d is already instance %s", r.VMID, other.ID)
		} else if !errors.Is(err, db.ErrNotFound) {
			return err
		}
		if err := s.checkQuota(ctx, tx, owner.ID, Spec{CPUCores: cores, MemoryMiB: memoryMiB}, rootDisk, limits, nil); err != nil {
			return err
		}
		groupIDs, err := s.resolveGroups(ctx, tx, owner.ID, r.SecurityGroupIDs)
		if err != nil {
			return err
		}
		instance, err = db.InsertAdoptedInstance(ctx, tx, db.Instance{
			ID: newInstanceID(), AccountID: owner.ID, Name: name,
			CPUCores: cores, MemoryMiB: memoryMiB, MemoryMinMiB: memoryMinMiB, Ballooning: ballooning,
			RootDiskGiB: rootDisk, Tags: r.Tags, State: state, VMID: &r.VMID,
			MACAddress: mac, IPAddress: r.PrivateIPAddress,
		})
		if err != nil {
			return err
		}
		if err := db.SetInstanceGroups(ctx, tx, instance.ID, groupIDs); err != nil {
			return err
		}
		if instance, err = db.GetInstance(ctx, tx, instance.ID); err != nil {
			return err
		}
		if audit != nil {
			return audit(tx, instance)
		}
		return nil
	})
	if err != nil {
		return db.Instance{}, err
	}
	s.Wake()
	return instance, nil
}

// configString reads a string value from a Proxmox VM config, which reports
// almost everything as text. A missing or null key reads as "".
func configString(config map[string]any, key string) string {
	value, ok := config[key]
	if !ok || value == nil {
		return ""
	}
	switch typed := value.(type) {
	case string:
		return typed
	case float64:
		return strconv.FormatFloat(typed, 'f', -1, 64)
	default:
		return fmt.Sprint(typed)
	}
}

// configInt reads an integer from a Proxmox VM config, which may report it as a
// string, a JSON number or an int. A missing or unparsable value is not found.
func configInt(config map[string]any, key string) (int, bool) {
	value, ok := config[key]
	if !ok || value == nil {
		return 0, false
	}
	switch typed := value.(type) {
	case string:
		n, err := strconv.Atoi(typed)
		return n, err == nil
	case float64:
		return int(typed), true
	case int:
		return typed, true
	default:
		return 0, false
	}
}

func configIntOr(config map[string]any, key string, fallback int) int {
	if n, ok := configInt(config, key); ok {
		return n
	}
	return fallback
}

// macFromNet0 pulls the MAC out of a NIC config such as
// "virtio=BC:24:11:AA:BB:CC,bridge=vmbr0,firewall=1".
func macFromNet0(config map[string]any) string {
	net0 := configString(config, "net0")
	_, rest, found := strings.Cut(net0, "=")
	if !found {
		return ""
	}
	mac, _, _ := strings.Cut(rest, ",")
	return strings.TrimSpace(mac)
}

// firstDiskVolid names the volume holding a VM's first disk, searching the
// usual controllers in order so the boot disk is found before any other.
func firstDiskVolid(config map[string]any) string {
	keys := make([]string, 0, len(config))
	for key := range config {
		if diskKey.MatchString(key) && plugged(key) {
			keys = append(keys, key)
		}
	}
	slices.SortFunc(keys, func(a, b string) int {
		return diskOrder(a) - diskOrder(b)
	})
	for _, key := range keys {
		if volid := volidAt(config, key); volid != "" {
			return volid
		}
	}
	return ""
}

// diskOrder ranks the controllers so the boot disk (virtio, then scsi, sata,
// ide) is considered before extras.
func diskOrder(key string) int {
	for i, prefix := range []string{"virtio", "scsi", "sata", "ide", "unused"} {
		if strings.HasPrefix(key, prefix) {
			return i*100 + diskIndex(key)
		}
	}
	return 1 << 20
}

func diskIndex(key string) int {
	n, _ := strconv.Atoi(strings.TrimLeft(key, "abcdefghijklmnopqrstuvwxyz"))
	return n
}
