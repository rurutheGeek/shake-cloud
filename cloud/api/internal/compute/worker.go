package compute

import (
	"context"
	"errors"
	"fmt"
	"math"
	"net/netip"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/netbox"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/proxmox"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/seed"
)

// RunWorker carries out pending actions until ctx ends.
func (s *Service) RunWorker(ctx context.Context) {
	for ctx.Err() == nil {
		if !s.WorkOnce(ctx) {
			select {
			case <-ctx.Done():
			case <-s.wake:
			case <-time.After(5 * time.Second):
			}
		}
	}
}

// WorkOnce carries out one piece of work, reporting whether there was any:
// an instance action first, then a volume action, then a firewall to write.
// One at a time, so two steps never edit the same VM's config at once.
func (s *Service) WorkOnce(ctx context.Context) bool {
	return s.workInstanceOnce(ctx) || s.workVolumeOnce(ctx) || s.workFirewallOnce(ctx)
}

func (s *Service) workInstanceOnce(ctx context.Context) bool {
	instance, err := db.ClaimWork(ctx, s.Pool, 15*time.Minute)
	if errors.Is(err, db.ErrNotFound) {
		return false
	}
	if err != nil {
		if ctx.Err() == nil {
			s.Log.Error("claiming work failed", "err", err)
		}
		return false
	}
	s.process(ctx, instance)
	return true
}

func (s *Service) process(ctx context.Context, instance db.Instance) {
	log := s.Log.With("instance_id", instance.ID, "action", instance.PendingAction, "attempt", instance.Attempts+1)
	stepCtx, cancel := context.WithTimeout(ctx, 14*time.Minute)
	defer cancel()

	state, err := s.carryOut(stepCtx, instance)
	if err == nil {
		// A terminate keeps the reason it was started with, e.g. why a launch was abandoned.
		reason := ""
		if instance.PendingAction == db.ActionTerminate {
			reason = instance.StateReason
		}
		applied, err := db.FinishAction(ctx, s.Pool, instance.ID, instance.PendingAction, state, reason)
		if err != nil {
			log.Error("recording a finished action failed", "err", err)
		} else if !applied {
			// The user asked for something else meanwhile; do that next.
			s.Wake()
		} else {
			log.Info("instance action finished", "state", state)
		}
		return
	}
	if ctx.Err() != nil {
		_ = db.ReleaseLease(context.Background(), s.Pool, instance.ID)
		return
	}

	attempts := instance.Attempts + 1
	message := truncate(err.Error(), 500)
	log.Warn("instance action failed", "err", err)
	if attempts < s.MaxAttempts || instance.PendingAction == db.ActionTerminate {
		if err := db.RetryLater(ctx, s.Pool, instance.ID, instance.PendingAction, message, s.now().Add(s.backoff(attempts))); err != nil {
			log.Error("scheduling a retry failed", "err", err)
		}
		return
	}
	reason := "Server.InternalError: " + message
	switch instance.PendingAction {
	case db.ActionLaunch:
		// Remove whatever the launch managed to create.
		err = db.AbandonLaunch(ctx, s.Pool, instance.ID, reason)
		s.Wake()
	case db.ActionStart:
		err = db.GiveUpAction(ctx, s.Pool, instance.ID, db.ActionStart, db.StateStopped, reason)
	default:
		err = db.GiveUpAction(ctx, s.Pool, instance.ID, instance.PendingAction, db.StateRunning, reason)
	}
	if err != nil {
		log.Error("giving up on an action failed", "err", err)
	}
}

func (s *Service) backoff(attempts int) time.Duration {
	delay := time.Duration(float64(s.RetryDelay) * math.Pow(2, float64(attempts-1)))
	return min(delay, 5*time.Minute)
}

func (s *Service) carryOut(ctx context.Context, instance db.Instance) (string, error) {
	switch instance.PendingAction {
	case db.ActionLaunch:
		return db.StateRunning, s.launch(ctx, instance)
	case db.ActionStart:
		return db.StateRunning, s.power(ctx, instance, "start", nil)
	case db.ActionStop:
		// ACPI shutdown first, so the guest can flush its disks; forced after the timeout.
		return db.StateStopped, s.power(ctx, instance, "shutdown", url.Values{"forceStop": {"1"}, "timeout": {"120"}})
	case db.ActionReboot:
		return db.StateRunning, s.power(ctx, instance, "reboot", url.Values{"timeout": {"120"}})
	case db.ActionTerminate:
		return db.StateTerminated, s.terminate(ctx, instance)
	}
	return "", fmt.Errorf("unknown action %q", instance.PendingAction)
}

func resourcesOf(i db.Instance) db.Resources {
	return db.Resources{VMID: i.VMID, VMCreated: i.VMCreated, IPAddress: i.IPAddress, NetBoxIPID: i.NetBoxIPID, SeedVolume: i.SeedVolume}
}

// launch creates the address, the seed ISO and the VM, in that order, and
// starts it. Each step is skipped when an earlier attempt already recorded its
// result, so a crash at any point resumes rather than duplicates.
func (s *Service) launch(ctx context.Context, instance db.Instance) error {
	resources := resourcesOf(instance)
	record := func() error { return db.RecordResources(ctx, s.Pool, instance.ID, resources) }

	if resources.NetBoxIPID == nil {
		address, err := s.address(ctx, instance)
		if err != nil {
			return fmt.Errorf("allocate address: %w", err)
		}
		resources.IPAddress, resources.NetBoxIPID = address.Address, &address.ID
		if err := record(); err != nil {
			return err
		}
	}
	if resources.SeedVolume == "" {
		volume, err := s.uploadSeed(ctx, instance, resources.IPAddress)
		if err != nil {
			return fmt.Errorf("seed ISO: %w", err)
		}
		resources.SeedVolume = volume
		if err := record(); err != nil {
			return err
		}
	}
	if !resources.VMCreated {
		if err := s.createVM(ctx, instance, &resources); err != nil {
			return fmt.Errorf("create VM: %w", err)
		}
		resources.VMCreated = true
		if err := record(); err != nil {
			return err
		}
	}
	vmid := *resources.VMID
	if err := s.growDisk(ctx, instance, vmid); err != nil {
		return fmt.Errorf("resize disk: %w", err)
	}
	// Before the first boot, so the guest is never reachable beyond its groups.
	if err := s.writeFirewall(ctx, instance.ID); err != nil {
		return fmt.Errorf("firewall: %w", err)
	}
	status, err := s.PVE.VMStatus(ctx, vmid)
	if err != nil {
		return err
	}
	if status != "running" {
		if err := s.task(ctx, func() (string, error) { return s.PVE.Power(ctx, vmid, "start", nil) }); err != nil {
			return fmt.Errorf("start: %w", err)
		}
	}
	return nil
}

func (s *Service) task(ctx context.Context, start func() (string, error)) error {
	upid, err := start()
	if err != nil {
		return err
	}
	return s.PVE.WaitTask(ctx, upid)
}

// address reuses one an interrupted attempt already took for this instance.
func (s *Service) address(ctx context.Context, instance db.Instance) (netbox.IPAddress, error) {
	existing, err := s.IPAM.IPAddressesByDescription(ctx, instance.ID)
	if err != nil {
		return netbox.IPAddress{}, err
	}
	if len(existing) > 0 {
		return existing[0], nil
	}
	rangeID, err := s.ipRange(ctx)
	if err != nil {
		return netbox.IPAddress{}, err
	}
	return s.IPAM.AllocateIP(ctx, rangeID, netbox.Allocation{
		Description: instance.ID, DNSName: seed.Hostname(instance.Name, instance.ID), Tags: []string{NetBoxTag},
	})
}

func (s *Service) ipRange(ctx context.Context) (int, error) {
	s.rangeMu.Lock()
	defer s.rangeMu.Unlock()
	if s.rangeID == 0 {
		id, err := s.IPAM.IPRangeID(ctx, s.Site.Network.IPRangeStart)
		if err != nil {
			return 0, err
		}
		s.rangeID = id
	}
	return s.rangeID, nil
}

func seedFileName(instanceID string) string { return "shakecloud-" + instanceID + ".iso" }

func (s *Service) uploadSeed(ctx context.Context, instance db.Instance, ipAddress string) (string, error) {
	address, err := netip.ParsePrefix(ipAddress)
	if err != nil {
		return "", fmt.Errorf("address %q from NetBox: %w", ipAddress, err)
	}
	config := seed.Config{
		InstanceID: instance.ID, Hostname: seed.Hostname(instance.Name, instance.ID), MACAddress: instance.MACAddress,
		Address: address, Gateway: netip.MustParseAddr(s.Site.Network.Gateway), UserData: instance.UserData,
	}
	if instance.KeyPublicKey != "" {
		config.PublicKeys = []string{instance.KeyPublicKey}
	}
	for _, server := range s.Site.Network.DNSServers {
		config.Nameservers = append(config.Nameservers, netip.MustParseAddr(server))
	}
	iso, err := seed.Build(config, s.WorkDir)
	if err != nil {
		return "", err
	}
	storage := s.Site.Storage.Images
	name := seedFileName(instance.ID)
	volume := storage + ":iso/" + name
	// An attempt that died mid-upload may have left a file under the same name.
	if exists, err := s.volumeExists(ctx, storage, volume); err != nil {
		return "", err
	} else if exists {
		if err := s.PVE.DeleteVolume(ctx, storage, volume); err != nil {
			return "", err
		}
	}
	if err := s.task(ctx, func() (string, error) { return s.PVE.UploadISO(ctx, storage, name, iso) }); err != nil {
		return "", err
	}
	return volume, nil
}

func (s *Service) volumeExists(ctx context.Context, storage, volume string) (bool, error) {
	volumes, err := s.PVE.ListVolumes(ctx, storage, "iso")
	if err != nil {
		return false, err
	}
	for _, v := range volumes {
		if v.VolID == volume {
			return true, nil
		}
	}
	return false, nil
}

func findVM(vms []proxmox.VM, vmid int) *proxmox.VM {
	for i := range vms {
		if vms[i].VMID == vmid {
			return &vms[i]
		}
	}
	return nil
}

// owns tells a VM this instance manages from anything else on the same VMID.
// Every VM the API creates carries its instance ID in the description; an
// adopted VM predates the API and is owned by virtue of being registered.
func (s *Service) owns(ctx context.Context, vmid int, instance db.Instance) (bool, error) {
	if instance.Adopted {
		return true, nil
	}
	config, err := s.PVE.VMConfig(ctx, vmid)
	if err != nil {
		return false, err
	}
	description, _ := config["description"].(string)
	return strings.Contains(description, instance.ID), nil
}

// vlanTag is the ",tag=<id>" NIC option, or "" while the cloud is untagged.
func vlanTag(id int) string {
	if id <= 0 {
		return ""
	}
	return fmt.Sprintf(",tag=%d", id)
}

func (s *Service) vmParams(instance db.Instance, vmid int, resources db.Resources, imageVolume string) url.Values {
	return url.Values{
		"vmid":        {strconv.Itoa(vmid)},
		"name":        {instance.ID},
		"pool":        {s.Site.Pool},
		"ostype":      {"l26"},
		"cores":       {strconv.Itoa(instance.CPUCores)},
		"cpu":         {"host"},
		"memory":      {strconv.Itoa(instance.MemoryMiB)},
		"balloon":     {strconv.Itoa(instance.MemoryMinMiB)},
		"scsihw":      {"virtio-scsi-single"},
		"virtio0":     {fmt.Sprintf("%s:0,import-from=%s,discard=on", s.Site.Storage.VMDisks, imageVolume)},
		"ide2":        {resources.SeedVolume + ",media=cdrom"},
		"net0":        {fmt.Sprintf("virtio=%s,bridge=%s,firewall=1%s", instance.MACAddress, s.Site.Network.Bridge, vlanTag(s.Site.Network.VLANID))},
		"boot":        {"order=virtio0"},
		"serial0":     {"socket"},
		"tags":        {"shakecloud"},
		"description": {fmt.Sprintf("shake-cloud instance %s (account %s). Managed by cloud/api; do not edit.", instance.ID, instance.AccountID)},
	}
}

func (s *Service) createVM(ctx context.Context, instance db.Instance, resources *db.Resources) error {
	vmid := *resources.VMID
	// Resolved now rather than at admission: an uploaded image lives in the
	// ledger, and this is the moment its file is actually needed.
	image, err := s.ResolveImage(ctx, s.Pool, instance.ImageID)
	if err != nil {
		return err
	}
	vms, err := s.PVE.ListVMs(ctx)
	if err != nil {
		return err
	}
	if findVM(vms, vmid) != nil {
		owned, err := s.owns(ctx, vmid, instance)
		if err != nil || owned {
			// Owned: an earlier attempt created it and crashed before recording that.
			return err
		}
		return s.moveVMID(ctx, instance, resources, vms, "occupied by a VM the API did not create")
	}
	err = s.task(ctx, func() (string, error) {
		return s.PVE.CreateVM(ctx, s.vmParams(instance, vmid, *resources, image.Volume))
	})
	if err != nil && strings.Contains(err.Error(), "already exists") {
		// Taken by a VM outside the cloud pool, which the token cannot list.
		return s.moveVMID(ctx, instance, resources, vms, "Proxmox reports the VMID already exists outside the cloud pool")
	}
	return err
}

// moveVMID quarantines a VMID that turned out to be taken and gives the
// instance another; the retry uses it.
func (s *Service) moveVMID(ctx context.Context, instance db.Instance, resources *db.Resources, visible []proxmox.VM, reason string) error {
	old := *resources.VMID
	err := pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		if err := db.LockCapacity(ctx, tx); err != nil {
			return err
		}
		if err := db.QuarantineVMID(ctx, tx, old, reason); err != nil {
			return err
		}
		vmid, err := db.AllocateVMID(ctx, tx, s.Site.VMIDFrom, s.Site.VMIDTo, s.skipVMIDs(visible))
		if err != nil {
			return err
		}
		resources.VMID = &vmid
		return db.RecordResources(ctx, tx, instance.ID, *resources)
	})
	if err != nil {
		return err
	}
	s.Log.Warn("VMID quarantined", "vmid", old, "instance_id", instance.ID, "new_vmid", *resources.VMID, "reason", reason)
	return fmt.Errorf("VMID %d was taken (%s); moved to %d", old, reason, *resources.VMID)
}

var diskSize = regexp.MustCompile(`(?:^|,)size=(\d+(?:\.\d+)?)([KMGT]?)`)

// sizeGiB reads the size out of a disk string such as "local-lvm:vm-5000-disk-0,discard=on,size=3G".
func sizeGiB(disk string) float64 {
	m := diskSize.FindStringSubmatch(disk)
	if m == nil {
		return 0
	}
	value, _ := strconv.ParseFloat(m[1], 64)
	switch m[2] {
	case "K":
		return value / (1 << 20)
	case "M":
		return value / (1 << 10)
	case "T":
		return value * (1 << 10)
	case "G":
		return value
	}
	return value / (1 << 30)
}

func (s *Service) growDisk(ctx context.Context, instance db.Instance, vmid int) error {
	config, err := s.PVE.VMConfig(ctx, vmid)
	if err != nil {
		return err
	}
	disk, _ := config["virtio0"].(string)
	if sizeGiB(disk) >= float64(instance.RootDiskGiB) {
		return nil
	}
	return s.PVE.ResizeDisk(ctx, vmid, "virtio0", fmt.Sprintf("%dG", instance.RootDiskGiB))
}

func (s *Service) power(ctx context.Context, instance db.Instance, action string, params url.Values) error {
	if instance.VMID == nil || !instance.VMCreated {
		return errors.New("the instance has no VM")
	}
	vmid := *instance.VMID
	vms, err := s.PVE.ListVMs(ctx)
	if err != nil {
		return err
	}
	vm := findVM(vms, vmid)
	if vm == nil {
		return fmt.Errorf("VM %d is not in the cloud pool", vmid)
	}
	if owned, err := s.owns(ctx, vmid, instance); err != nil || !owned {
		return errors.Join(err, fmt.Errorf("VM %d does not belong to %s", vmid, instance.ID))
	}
	switch {
	case action == "start" && vm.Status == "running", action == "shutdown" && vm.Status == "stopped":
		return nil
	}
	return s.task(ctx, func() (string, error) { return s.PVE.Power(ctx, vmid, action, params) })
}

// terminate removes the VM, the seed ISO and the address. A VM on the
// instance's VMID that does not carry its ID is never touched.
func (s *Service) terminate(ctx context.Context, instance db.Instance) error {
	if instance.VMID != nil {
		vmid := *instance.VMID
		vms, err := s.PVE.ListVMs(ctx)
		if err != nil {
			return err
		}
		if vm := findVM(vms, vmid); vm != nil {
			owned, err := s.owns(ctx, vmid, instance)
			if err != nil {
				return err
			}
			if owned {
				if vm.Status == "running" {
					if err := s.task(ctx, func() (string, error) { return s.PVE.Power(ctx, vmid, "stop", nil) }); err != nil {
						return fmt.Errorf("stop: %w", err)
					}
				}
				// Deleting the VM destroys every disk it holds, volumes included.
				if err := s.returnVolumes(ctx, instance, vmid); err != nil {
					return fmt.Errorf("return volumes: %w", err)
				}
				if err := s.task(ctx, func() (string, error) { return s.PVE.DeleteVM(ctx, vmid) }); err != nil {
					return fmt.Errorf("delete VM: %w", err)
				}
			} else {
				s.Log.Error("not deleting a VM this instance does not own", "instance_id", instance.ID, "vmid", vmid)
			}
		}
	}
	if instance.SeedVolume != "" {
		storage := s.Site.Storage.Images
		exists, err := s.volumeExists(ctx, storage, instance.SeedVolume)
		if err != nil {
			return err
		}
		if exists {
			if err := s.PVE.DeleteVolume(ctx, storage, instance.SeedVolume); err != nil {
				return fmt.Errorf("delete seed ISO: %w", err)
			}
		}
	}
	// Every address carrying the instance ID, including one taken by an attempt
	// that crashed before recording it.
	addresses, err := s.IPAM.IPAddressesByDescription(ctx, instance.ID)
	if err != nil {
		return err
	}
	released := map[int]bool{}
	for _, address := range addresses {
		if err := s.IPAM.DeleteIPAddress(ctx, address.ID); err != nil {
			return fmt.Errorf("release address: %w", err)
		}
		released[address.ID] = true
	}
	if id := instance.NetBoxIPID; id != nil && !released[*id] {
		if err := s.IPAM.DeleteIPAddress(ctx, *id); err != nil {
			return fmt.Errorf("release address: %w", err)
		}
	}
	return nil
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n]
}
