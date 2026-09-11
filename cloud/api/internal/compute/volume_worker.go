package compute

import (
	"context"
	"errors"
	"fmt"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

// The volume worker moves disks between VMs. Proxmox keeps every disk under
// some VM and changes the owner only with move_disk, which also renames the
// disk, so a detached volume waits as an unusedN entry on the holder VM.
//
// Every step first finds where the disk actually is (locate) and records where
// it went as soon as it has moved, so a crash at any point resumes instead of
// losing a disk or making a second one.

// holderMarker identifies the holder in its description, the way an instance's
// VM carries its instance ID.
const holderMarker = "shake-cloud volume holder"

var diskKey = regexp.MustCompile(`^(virtio|scsi|sata|ide|unused)\d+$`)

// giveUp is a failure retrying cannot fix; reason becomes the state reason.
type giveUp struct{ reason string }

func (g giveUp) Error() string { return g.reason }

// errBusy means the instance is in the middle of another action.
var errBusy = errors.New("the instance is busy with another action; trying again")

// errDiskMissing means a recorded disk is on neither its VM nor its move destination.
var errDiskMissing = errors.New("the disk is not where it was recorded")

func (s *Service) workVolumeOnce(ctx context.Context) bool {
	volume, err := db.ClaimVolumeWork(ctx, s.Pool, 15*time.Minute)
	if errors.Is(err, db.ErrNotFound) {
		return false
	}
	if err != nil {
		if ctx.Err() == nil {
			s.Log.Error("claiming volume work failed", "err", err)
		}
		return false
	}
	s.processVolume(ctx, volume)
	return true
}

func (s *Service) processVolume(ctx context.Context, volume db.Volume) {
	log := s.Log.With("volume_id", volume.ID, "action", volume.PendingAction, "attempt", volume.Attempts+1)
	stepCtx, cancel := context.WithTimeout(ctx, 14*time.Minute)
	defer cancel()

	err := s.carryOutVolume(stepCtx, &volume)
	if err == nil {
		applied, err := db.FinishVolumeAction(ctx, s.Pool, volume.ID, volume.PendingAction)
		switch {
		case err != nil:
			log.Error("recording a finished volume action failed", "err", err)
		case !applied:
			s.Wake()
		default:
			log.Info("volume action finished")
		}
		return
	}
	if ctx.Err() != nil {
		_ = db.ReleaseVolumeLease(context.Background(), s.Pool, volume.ID)
		return
	}

	attempts := volume.Attempts + 1
	message := truncate(err.Error(), 500)
	log.Warn("volume action failed", "err", err)
	var permanent giveUp
	retry := !errors.As(err, &permanent) && attempts < s.MaxAttempts
	if volume.PendingAction == db.VolumeActionDetach || volume.PendingAction == db.VolumeActionDelete {
		// Never abandoned: giving up would strand the disk on an instance, where
		// terminating it would destroy the data, or leak the space.
		retry = true
	}
	if retry {
		if err := db.RetryVolumeLater(ctx, s.Pool, volume.ID, volume.PendingAction, message, s.now().Add(s.backoff(attempts))); err != nil {
			log.Error("scheduling a volume retry failed", "err", err)
		}
		return
	}
	reason := "Server.InternalError: " + message
	if errors.As(err, &permanent) {
		reason = permanent.reason
	}
	switch volume.PendingAction {
	case db.VolumeActionCreate:
		err = db.GiveUpCreate(ctx, s.Pool, volume.ID, reason)
	case db.VolumeActionAttach:
		err = db.GiveUpAttach(ctx, s.Pool, volume.ID, reason)
		s.Wake()
	case db.VolumeActionResize:
		actual := volume.SizeGiB
		if size, found, sizeErr := s.diskSizeGiB(ctx, volume.Location.VolID); sizeErr == nil && found {
			actual = size
		}
		err = db.GiveUpResize(ctx, s.Pool, volume.ID, actual, reason)
	}
	if err != nil {
		log.Error("giving up on a volume action failed", "err", err)
	}
}

func (s *Service) carryOutVolume(ctx context.Context, v *db.Volume) error {
	switch v.PendingAction {
	case db.VolumeActionCreate:
		return s.createVolumeDisk(ctx, v)
	case db.VolumeActionAttach:
		return s.attachVolumeDisk(ctx, v)
	case db.VolumeActionDetach:
		return s.detachVolumeDisk(ctx, v)
	case db.VolumeActionResize:
		return s.resizeVolumeDisk(ctx, v)
	case db.VolumeActionDelete:
		return s.deleteVolumeDisk(ctx, v)
	}
	return fmt.Errorf("unknown volume action %q", v.PendingAction)
}

// volidAt returns the volume ID configured under key, or "".
func volidAt(config map[string]any, key string) string {
	value, _ := config[key].(string)
	return strings.SplitN(value, ",", 2)[0]
}

// diskKeyOf returns the key under which config holds volid, or "".
func diskKeyOf(config map[string]any, volid string) string {
	for key := range config {
		if diskKey.MatchString(key) && volidAt(config, key) == volid {
			return key
		}
	}
	return ""
}

// freeKey returns the first of prefix<from>..prefix<to> not in config.
func freeKey(config map[string]any, prefix string, from, to int) string {
	for n := from; n <= to; n++ {
		if _, taken := config[prefix+strconv.Itoa(n)]; !taken {
			return prefix + strconv.Itoa(n)
		}
	}
	return ""
}

// plugged reports whether key attaches a disk to the VM, rather than merely
// listing it as unused.
func plugged(key string) bool {
	return key != "" && !strings.HasPrefix(key, "unused")
}

// configure applies a config change and waits for it, if Proxmox made a task.
func (s *Service) configure(ctx context.Context, vmid int, params url.Values) error {
	upid, err := s.PVE.ConfigureVM(ctx, vmid, params)
	if err != nil || upid == "" {
		return err
	}
	return s.PVE.WaitTask(ctx, upid)
}

func (s *Service) pendingKey(ctx context.Context, vmid int, key string) (bool, error) {
	changes, err := s.PVE.VMPending(ctx, vmid)
	if err != nil {
		return false, err
	}
	for _, change := range changes {
		if change.Key == key {
			return true, nil
		}
	}
	return false, nil
}

// ensureHolder creates the holder VM the first time a volume needs it. A VM on
// the holder's VMID that does not say it is the holder is never used.
func (s *Service) ensureHolder(ctx context.Context) error {
	holder := s.Site.VolumeHolderVMID
	vms, err := s.PVE.ListVMs(ctx)
	if err != nil {
		return err
	}
	if findVM(vms, holder) != nil {
		config, err := s.PVE.VMConfig(ctx, holder)
		if err != nil {
			return err
		}
		if description, _ := config["description"].(string); !strings.Contains(description, holderMarker) {
			return giveUp{fmt.Sprintf("Server.InternalError: VMID %d is taken by a VM that is not the volume holder", holder)}
		}
		return nil
	}
	err = s.task(ctx, func() (string, error) {
		return s.PVE.CreateVM(ctx, url.Values{
			"vmid": {strconv.Itoa(holder)}, "name": {"shakecloud-volumes"}, "pool": {s.Site.Pool},
			// It never runs, so it gets the least Proxmox accepts.
			"memory": {"64"}, "cores": {"1"}, "onboot": {"0"}, "tags": {"shakecloud"},
			"description": {holderMarker + ": detached volumes wait here as unused disks. Never start it. Managed by cloud/api; do not edit."},
		})
	})
	if err != nil && strings.Contains(err.Error(), "already exists") {
		return giveUp{fmt.Sprintf("Server.InternalError: VMID %d is taken outside the cloud pool", holder)}
	}
	return err
}

// volIDClaimed reports whether another live volume records volid.
func (s *Service) volIDClaimed(ctx context.Context, volid, exceptID string) (bool, error) {
	other, err := db.VolumeByVolID(ctx, s.Pool, volid)
	if errors.Is(err, db.ErrNotFound) {
		return false, nil
	}
	return err == nil && other.ID != exceptID, err
}

// locate refreshes where a volume's disk is. A move that finished without being
// recorded is found at its destination, where the disk has a new volume ID.
func (s *Service) locate(ctx context.Context, v *db.Volume) error {
	l := &v.Location
	if l.VMID != nil && l.VolID != "" {
		config, err := s.PVE.VMConfig(ctx, *l.VMID)
		if err != nil {
			return err
		}
		if key := diskKeyOf(config, l.VolID); key != "" {
			if key == l.ConfigKey && l.MoveVMID == nil {
				return nil
			}
			l.ConfigKey, l.MoveVMID, l.MoveKey = key, nil, ""
			return db.RecordLocation(ctx, s.Pool, v.ID, *l)
		}
	}
	if l.MoveVMID != nil && l.MoveKey != "" {
		config, err := s.PVE.VMConfig(ctx, *l.MoveVMID)
		if err != nil {
			return err
		}
		if volid := volidAt(config, l.MoveKey); volid != "" {
			claimed, err := s.volIDClaimed(ctx, volid, v.ID)
			if err != nil {
				return err
			}
			if !claimed {
				*l = db.Location{VMID: l.MoveVMID, ConfigKey: l.MoveKey, VolID: volid}
				return db.RecordLocation(ctx, s.Pool, v.ID, *l)
			}
		}
	}
	if l.VolID == "" {
		return nil
	}
	return fmt.Errorf("%w: volume %s, disk %s on VM %v", errDiskMissing, v.ID, l.VolID, derefVMID(l.VMID))
}

func derefVMID(vmid *int) any {
	if vmid == nil {
		return "none"
	}
	return *vmid
}

// move hands an unused disk to target as an unused disk there.
func (s *Service) move(ctx context.Context, v *db.Volume, target int) error {
	l := &v.Location
	if l.VMID == nil || !strings.HasPrefix(l.ConfigKey, "unused") {
		return fmt.Errorf("volume %s is at %q, not an unused disk that can move", v.ID, l.ConfigKey)
	}
	config, err := s.PVE.VMConfig(ctx, target)
	if err != nil {
		return err
	}
	key := freeKey(config, "unused", 0, holderSlots-1)
	if key == "" {
		return fmt.Errorf("VM %d has no free unused slot", target)
	}
	source, sourceKey := *l.VMID, l.ConfigKey
	l.MoveVMID, l.MoveKey = &target, key
	if err := db.RecordLocation(ctx, s.Pool, v.ID, *l); err != nil {
		return err
	}
	if err := s.task(ctx, func() (string, error) { return s.PVE.MoveDisk(ctx, source, sourceKey, target, key) }); err != nil {
		return fmt.Errorf("move to VM %d: %w", target, err)
	}
	if config, err = s.PVE.VMConfig(ctx, target); err != nil {
		return err
	}
	volid := volidAt(config, key)
	if volid == "" {
		return fmt.Errorf("the disk did not arrive at VM %d as %s", target, key)
	}
	*l = db.Location{VMID: &target, ConfigKey: key, VolID: volid}
	return db.RecordLocation(ctx, s.Pool, v.ID, *l)
}

// unplug turns a plugged disk into an unused one on the same VM. On a running
// guest it is a hot-unplug, which the guest has to go along with.
func (s *Service) unplug(ctx context.Context, v *db.Volume) error {
	l := &v.Location
	if l.VMID == nil || !plugged(l.ConfigKey) {
		return nil
	}
	vmid := *l.VMID
	if err := s.PVE.UnlinkDisks(ctx, vmid, []string{l.ConfigKey}, false); err != nil {
		return fmt.Errorf("unplug %s: %w", l.ConfigKey, err)
	}
	if waiting, err := s.pendingKey(ctx, vmid, l.ConfigKey); err != nil || waiting {
		return errors.Join(err, fmt.Errorf("the guest has not released %s yet; unmount it inside the guest", l.ConfigKey))
	}
	config, err := s.PVE.VMConfig(ctx, vmid)
	if err != nil {
		return err
	}
	key := diskKeyOf(config, l.VolID)
	if !strings.HasPrefix(key, "unused") {
		return fmt.Errorf("after unplugging, VM %d holds the disk as %q", vmid, key)
	}
	l.ConfigKey = key
	return db.RecordLocation(ctx, s.Pool, v.ID, *l)
}

// diskSizeGiB reads a disk's real size from storage.
func (s *Service) diskSizeGiB(ctx context.Context, volid string) (int, bool, error) {
	if volid == "" {
		return 0, false, nil
	}
	volumes, err := s.PVE.ListVolumes(ctx, s.Site.Storage.VMDisks, "images")
	if err != nil {
		return 0, false, err
	}
	for _, volume := range volumes {
		if volume.VolID == volid {
			return int(volume.Size >> 30), true, nil
		}
	}
	return 0, false, nil
}

func (s *Service) createVolumeDisk(ctx context.Context, v *db.Volume) error {
	if err := s.ensureHolder(ctx); err != nil {
		return err
	}
	holder := s.Site.VolumeHolderVMID
	if err := s.locate(ctx, v); err != nil {
		return err
	}
	l := &v.Location
	if l.VolID == "" {
		config, err := s.PVE.VMConfig(ctx, holder)
		if err != nil {
			return err
		}
		// Allocation needs a plugged slot; the disk is unplugged straight after.
		key := freeKey(config, "scsi", 0, 30)
		if key == "" {
			return errors.New("the volume holder has no free scsi slot")
		}
		// Recorded first, so that locate finds a disk Proxmox made just before a crash.
		*l = db.Location{MoveVMID: &holder, MoveKey: key}
		if err := db.RecordLocation(ctx, s.Pool, v.ID, *l); err != nil {
			return err
		}
		disk := fmt.Sprintf("%s:%d,discard=on", s.Site.Storage.VMDisks, v.SizeGiB)
		if err := s.configure(ctx, holder, url.Values{key: {disk}}); err != nil {
			return fmt.Errorf("allocate: %w", err)
		}
		if err := s.locate(ctx, v); err != nil {
			return err
		}
		if l.VolID == "" {
			return fmt.Errorf("the holder has no disk at %s after allocating one", key)
		}
	}
	return s.unplug(ctx, v)
}

func (s *Service) attachVolumeDisk(ctx context.Context, v *db.Volume) error {
	instance, err := db.GetInstance(ctx, s.Pool, v.InstanceID)
	if err != nil {
		return err
	}
	switch {
	case instance.State == db.StateTerminated || instance.State == db.StateShuttingDown:
		return giveUp{"Client.InvalidInstanceID: instance " + instance.ID + " is being terminated"}
	case instance.PendingAction != "":
		return errBusy
	case instance.VMID == nil || !instance.VMCreated:
		return giveUp{"Server.InternalError: instance " + instance.ID + " has no VM"}
	}
	vmid := *instance.VMID
	owned, err := s.owns(ctx, vmid, instance.ID)
	if err != nil {
		return err
	}
	if !owned {
		return giveUp{fmt.Sprintf("Server.InternalError: VM %d does not belong to %s", vmid, instance.ID)}
	}
	if err := s.locate(ctx, v); err != nil {
		return err
	}
	l := &v.Location
	if l.VMID == nil || *l.VMID != vmid {
		// A resize interrupted on the holder can leave the disk plugged there.
		if err := s.unplug(ctx, v); err != nil {
			return err
		}
		if err := s.move(ctx, v, vmid); err != nil {
			return err
		}
	}
	if l.ConfigKey != v.Device {
		if plugged(l.ConfigKey) {
			return giveUp{fmt.Sprintf("Server.InternalError: the disk is plugged in as %s, not %s", l.ConfigKey, v.Device)}
		}
		config, err := s.PVE.VMConfig(ctx, vmid)
		if err != nil {
			return err
		}
		if other := volidAt(config, v.Device); other != "" {
			return giveUp{fmt.Sprintf("Client.InvalidDevice: %s is already used on the VM by %s", v.Device, other)}
		}
		disk := fmt.Sprintf("%s,discard=on,serial=%s", l.VolID, VolumeSerial(v.ID))
		if err := s.configure(ctx, vmid, url.Values{v.Device: {disk}}); err != nil {
			return fmt.Errorf("plug in as %s: %w", v.Device, err)
		}
		l.ConfigKey = v.Device
		if err := db.RecordLocation(ctx, s.Pool, v.ID, *l); err != nil {
			return err
		}
	}
	// Proxmox shows a change a running guest refused as already applied, with
	// the difference only in the pending list.
	if waiting, err := s.pendingKey(ctx, vmid, v.Device); err != nil || waiting {
		return errors.Join(err, fmt.Errorf("the guest has not taken %s; the change is pending", v.Device))
	}
	return nil
}

func (s *Service) detachVolumeDisk(ctx context.Context, v *db.Volume) error {
	holder := s.Site.VolumeHolderVMID
	if err := s.locate(ctx, v); err != nil {
		return err
	}
	l := &v.Location
	if l.VMID == nil || *l.VMID == holder {
		// Never moved (an attach given up early), or already back.
		return s.unplug(ctx, v)
	}
	if plugged(l.ConfigKey) {
		instance, err := db.GetInstance(ctx, s.Pool, v.InstanceID)
		if err != nil {
			return err
		}
		if instance.PendingAction != "" && instance.PendingAction != db.ActionTerminate {
			return errBusy
		}
		if err := s.unplug(ctx, v); err != nil {
			return err
		}
	}
	if err := s.ensureHolder(ctx); err != nil {
		return err
	}
	return s.move(ctx, v, holder)
}

func (s *Service) resizeVolumeDisk(ctx context.Context, v *db.Volume) error {
	if err := s.locate(ctx, v); err != nil {
		return err
	}
	l := &v.Location
	if l.VMID == nil {
		return giveUp{"Server.InternalError: volume " + v.ID + " has no disk"}
	}
	holder, vmid := s.Site.VolumeHolderVMID, *l.VMID
	current, found, err := s.diskSizeGiB(ctx, l.VolID)
	if err != nil {
		return err
	}
	if !found {
		return fmt.Errorf("disk %s is not on storage %s", l.VolID, s.Site.Storage.VMDisks)
	}
	if current < v.SizeGiB {
		if !plugged(l.ConfigKey) {
			if vmid != holder {
				return errBusy
			}
			// Proxmox resizes only plugged disks. The holder never runs, so
			// plugging one in there changes nothing but its config.
			config, err := s.PVE.VMConfig(ctx, holder)
			if err != nil {
				return err
			}
			key := freeKey(config, "scsi", 0, 30)
			if key == "" {
				return errors.New("the volume holder has no free scsi slot")
			}
			if err := s.configure(ctx, holder, url.Values{key: {l.VolID + ",discard=on"}}); err != nil {
				return err
			}
			l.ConfigKey = key
			if err := db.RecordLocation(ctx, s.Pool, v.ID, *l); err != nil {
				return err
			}
		}
		if err := s.PVE.ResizeDisk(ctx, vmid, l.ConfigKey, fmt.Sprintf("%dG", v.SizeGiB)); err != nil {
			return fmt.Errorf("resize: %w", err)
		}
	}
	if vmid == holder {
		return s.unplug(ctx, v)
	}
	return nil
}

func (s *Service) deleteVolumeDisk(ctx context.Context, v *db.Volume) error {
	err := s.locate(ctx, v)
	l := &v.Location
	if errors.Is(err, errDiskMissing) {
		// Destroyed by an attempt that crashed before recording it.
		if _, found, sizeErr := s.diskSizeGiB(ctx, l.VolID); sizeErr == nil && !found {
			return nil
		}
	}
	if err != nil {
		return err
	}
	if l.VolID == "" {
		return nil
	}
	holder := s.Site.VolumeHolderVMID
	if l.VMID == nil || *l.VMID != holder {
		return fmt.Errorf("volume %s is on VM %v, not on the holder", v.ID, derefVMID(l.VMID))
	}
	if err := s.PVE.UnlinkDisks(ctx, holder, []string{l.ConfigKey}, true); err != nil {
		return fmt.Errorf("destroy: %w", err)
	}
	config, err := s.PVE.VMConfig(ctx, holder)
	if err != nil {
		return err
	}
	if diskKeyOf(config, l.VolID) != "" {
		return fmt.Errorf("disk %s is still on the holder", l.VolID)
	}
	return nil
}

// returnVolumes moves every volume off a stopped instance VM and onto the
// holder, before the VM is deleted along with every disk it holds. EC2 keeps an
// instance's attached data volumes when it terminates, and so does this.
func (s *Service) returnVolumes(ctx context.Context, instance db.Instance, vmid int) error {
	onVM, err := db.VolumesOnVM(ctx, s.Pool, vmid)
	if err != nil {
		return err
	}
	attached, err := db.VolumesOfInstance(ctx, s.Pool, instance.ID)
	if err != nil {
		return err
	}
	seen := map[string]bool{}
	for _, volume := range append(onVM, attached...) {
		if seen[volume.ID] {
			continue
		}
		seen[volume.ID] = true
		if err := s.locate(ctx, &volume); err != nil {
			return err
		}
		if l := volume.Location; l.VMID != nil && *l.VMID == vmid {
			if err := s.unplug(ctx, &volume); err != nil {
				return err
			}
			if err := s.ensureHolder(ctx); err != nil {
				return err
			}
			if err := s.move(ctx, &volume, s.Site.VolumeHolderVMID); err != nil {
				return err
			}
		}
		if volume.InstanceID == instance.ID {
			reason := "Client.InstanceTerminated: detached when instance " + instance.ID + " was terminated"
			if err := db.ReturnToHolder(ctx, s.Pool, volume.ID, volume.Location, reason); err != nil {
				return err
			}
		}
	}
	return s.refuseToDestroyVolumes(ctx, vmid)
}

// refuseToDestroyVolumes is the last check before a VM is deleted with its
// disks: none of them may be a volume's.
func (s *Service) refuseToDestroyVolumes(ctx context.Context, vmid int) error {
	config, err := s.PVE.VMConfig(ctx, vmid)
	if err != nil {
		return err
	}
	for key := range config {
		volid := volidAt(config, key)
		if !diskKey.MatchString(key) || volid == "" {
			continue
		}
		volume, err := db.VolumeByVolID(ctx, s.Pool, volid)
		if err == nil {
			return fmt.Errorf("VM %d still holds %s's disk as %s; not deleting it", vmid, volume.ID, key)
		}
		if !errors.Is(err, db.ErrNotFound) {
			return err
		}
	}
	return nil
}
