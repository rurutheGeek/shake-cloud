package compute

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"regexp"
	"strconv"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/site"
)

// Volumes are extra disks. Requests are admitted here and recorded; the
// worker (volume_worker.go) then moves the disks in Proxmox.

// An instance's root disk is virtio0, which leaves virtio1 to virtio15.
const lastVolumeDevice = 15

// holderSlots is how many detached volumes the holder can keep: Proxmox
// numbers unused disks unused0 to unused255.
const holderSlots = 256

var volumeDevice = regexp.MustCompile(`^virtio([1-9]|1[0-5])$`)

type CreateVolumeRequest struct {
	SizeGiB     int               `json:"size_gib"`
	ClientToken string            `json:"client_token"`
	Tags        map[string]string `json:"tags"`
}

func newVolumeID() string {
	b := make([]byte, 9)
	rand.Read(b)
	return "vol-" + hex.EncodeToString(b)[:17]
}

// VolumeSerial is the serial number the guest sees, and so its name under
// /dev/disk/by-id: the volume ID without the hyphen. EC2 names NVMe volumes
// the same way, and it is exactly the 20 characters Proxmox allows.
func VolumeSerial(volumeID string) string {
	return strings.Replace(volumeID, "-", "", 1)
}

func volumeNotFound(id string) error {
	return refuse(http.StatusNotFound, "InvalidVolume.NotFound", "volume %s does not exist", id)
}

func describeVolume(v db.Volume) string {
	switch {
	case v.PendingAction != "":
		return v.State + " (" + v.PendingAction + " in progress)"
	case v.AttachmentState != "":
		return v.State + " (" + v.AttachmentState + " to " + v.InstanceID + ")"
	}
	return v.State
}

// CreateVolume admits a new volume. It returns the volume and whether this
// call created it; a retry with the same client token gets the original.
func (s *Service) CreateVolume(ctx context.Context, accountID string, r CreateVolumeRequest, audit func(pgx.Tx, db.Volume) error) (db.Volume, bool, error) {
	limits, _, err := s.EffectiveLimits(ctx, s.Pool)
	if err != nil {
		return db.Volume{}, false, err
	}
	if size := limits.VolumeSizeGiB; r.SizeGiB < size.Min || r.SizeGiB > size.Max {
		return db.Volume{}, false, refuse(http.StatusBadRequest, "InvalidParameterValue", "size_gib must be between %d and %d", size.Min, size.Max)
	}
	if r.ClientToken != "" && !clientToken.MatchString(r.ClientToken) {
		return db.Volume{}, false, refuse(http.StatusBadRequest, "InvalidParameterValue", "client_token must be 1-64 printable ASCII characters")
	}
	if err := validateTags(r.Tags); err != nil {
		return db.Volume{}, false, err
	}
	hash := volumeRequestHash(r)
	if r.ClientToken != "" {
		existing, err := db.VolumeByClientToken(ctx, s.Pool, accountID, r.ClientToken)
		if err == nil {
			return idempotentVolume(existing, hash)
		}
		if !errors.Is(err, db.ErrNotFound) {
			return db.Volume{}, false, err
		}
	}
	if err := s.checkDiskPool(ctx, limits); err != nil {
		return db.Volume{}, false, err
	}

	var volume db.Volume
	created := false
	err = pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		if err := db.LockCapacity(ctx, tx); err != nil {
			return err
		}
		if r.ClientToken != "" {
			existing, err := db.VolumeByClientToken(ctx, tx, accountID, r.ClientToken)
			if err == nil {
				volume = existing
				return nil
			}
			if !errors.Is(err, db.ErrNotFound) {
				return err
			}
		}
		if err := checkVolumeQuota(ctx, tx, accountID, 1, r.SizeGiB, limits); err != nil {
			return err
		}
		live, err := db.LiveVolumeCount(ctx, tx)
		if err != nil {
			return err
		}
		if live >= holderSlots {
			return refuse(http.StatusServiceUnavailable, "InsufficientVolumeCapacity",
				"the cloud holds %d volumes, as many as Proxmox can keep detached", live)
		}
		volume, err = db.InsertVolume(ctx, tx, db.Volume{
			ID: newVolumeID(), AccountID: accountID, ClientToken: r.ClientToken, RequestSHA256: hash,
			SizeGiB: r.SizeGiB, Tags: r.Tags,
		})
		if err != nil {
			return err
		}
		created = true
		if audit != nil {
			return audit(tx, volume)
		}
		return nil
	})
	if err != nil {
		return db.Volume{}, false, err
	}
	if !created {
		return idempotentVolume(volume, hash)
	}
	s.Wake()
	return volume, true, nil
}

func volumeRequestHash(r CreateVolumeRequest) []byte {
	r.ClientToken = ""
	encoded, _ := json.Marshal(r)
	sum := sha256.Sum256(encoded)
	return sum[:]
}

func idempotentVolume(existing db.Volume, hash []byte) (db.Volume, bool, error) {
	if string(existing.RequestSHA256) != string(hash) {
		return db.Volume{}, false, refuse(http.StatusConflict, "IdempotentParameterMismatch",
			"client_token was already used for a request with different parameters (volume %s)", existing.ID)
	}
	return existing, false, nil
}

// checkVolumeQuota enforces an account's share of volumes; 0 is unlimited.
func checkVolumeQuota(ctx context.Context, q db.Querier, accountID string, addVolumes, addGiB int, limits site.Limits) error {
	usage, err := db.AccountUsage(ctx, q, accountID)
	if err != nil {
		return err
	}
	quota := limits.AccountQuota
	switch {
	case quota.Volumes > 0 && usage.Volumes+addVolumes > quota.Volumes:
		return refuse(http.StatusConflict, "VolumeLimitExceeded", "an account may hold %d volumes", quota.Volumes)
	case quota.VolumeGiB > 0 && usage.VolumeGiB+addGiB > quota.VolumeGiB:
		return refuse(http.StatusConflict, "VolumeLimitExceeded", "an account may hold %d GiB of volumes; %d are in use", quota.VolumeGiB, usage.VolumeGiB)
	}
	return nil
}

// ModifyVolume grows a volume. Shrinking is refused: the filesystem on it
// would be cut off, and Proxmox cannot shrink a disk either.
func (s *Service) ModifyVolume(ctx context.Context, id string, sizeGiB int, authorize func(db.Volume) bool, audit func(pgx.Tx, db.Volume) error) (db.Volume, error) {
	limits, _, err := s.EffectiveLimits(ctx, s.Pool)
	if err != nil {
		return db.Volume{}, err
	}
	if sizeGiB > limits.VolumeSizeGiB.Max {
		return db.Volume{}, refuse(http.StatusBadRequest, "InvalidParameterValue", "size_gib must be at most %d", limits.VolumeSizeGiB.Max)
	}
	if err := s.checkDiskPool(ctx, limits); err != nil {
		return db.Volume{}, err
	}
	var result db.Volume
	err = pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		if err := db.LockCapacity(ctx, tx); err != nil {
			return err
		}
		volume, err := db.LockVolume(ctx, tx, id)
		if errors.Is(err, db.ErrNotFound) || (err == nil && !authorize(volume)) {
			return volumeNotFound(id)
		}
		if err != nil {
			return err
		}
		if (volume.State != db.VolumeAvailable && volume.State != db.VolumeInUse) || volume.PendingAction != "" {
			return refuse(http.StatusConflict, "IncorrectState", "volume %s is %s", id, describeVolume(volume))
		}
		if sizeGiB <= volume.SizeGiB {
			return refuse(http.StatusBadRequest, "InvalidParameterValue", "a volume can only grow; %s is %d GiB", id, volume.SizeGiB)
		}
		if err := checkVolumeQuota(ctx, tx, volume.AccountID, 0, sizeGiB-volume.SizeGiB, limits); err != nil {
			return err
		}
		if result, err = db.RequestResize(ctx, tx, id, sizeGiB); err != nil {
			return err
		}
		if audit != nil {
			return audit(tx, result)
		}
		return nil
	})
	if err == nil {
		s.Wake()
	}
	return result, err
}

// DeleteVolume deletes a volume that is not attached. Deleting one that is
// already being deleted, or is gone, answers with it again.
func (s *Service) DeleteVolume(ctx context.Context, id string, authorize func(db.Volume) bool, audit func(pgx.Tx, db.Volume) error) (db.Volume, error) {
	var result db.Volume
	err := pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		volume, err := db.LockVolume(ctx, tx, id)
		if errors.Is(err, db.ErrNotFound) || (err == nil && !authorize(volume)) {
			return volumeNotFound(id)
		}
		if err != nil {
			return err
		}
		result = volume
		switch {
		case volume.State == db.VolumeDeleted || volume.PendingAction == db.VolumeActionDelete:
			return nil
		case volume.InstanceID != "":
			return refuse(http.StatusConflict, "VolumeInUse", "volume %s is attached to %s; detach it first", id, volume.InstanceID)
		case (volume.State != db.VolumeAvailable && volume.State != db.VolumeError) || volume.PendingAction != "":
			return refuse(http.StatusConflict, "IncorrectState", "volume %s is %s", id, describeVolume(volume))
		}
		if result, err = db.RequestDelete(ctx, tx, id); err != nil {
			return err
		}
		if audit != nil {
			return audit(tx, result)
		}
		return nil
	})
	if err == nil {
		s.Wake()
	}
	return result, err
}

// AttachVolume attaches an available volume to a running or stopped instance
// of the same account. device may be empty for the lowest free one.
func (s *Service) AttachVolume(ctx context.Context, id, instanceID, device string, authorize func(db.Volume) bool, audit func(pgx.Tx, db.Volume) error) (db.Volume, error) {
	if device != "" && !volumeDevice.MatchString(device) {
		return db.Volume{}, refuse(http.StatusBadRequest, "InvalidParameterValue", "device must be virtio1 to virtio15")
	}
	var result db.Volume
	err := pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		volume, err := db.LockVolume(ctx, tx, id)
		if errors.Is(err, db.ErrNotFound) || (err == nil && !authorize(volume)) {
			return volumeNotFound(id)
		}
		if err != nil {
			return err
		}
		if volume.State != db.VolumeAvailable || volume.PendingAction != "" || volume.InstanceID != "" {
			return refuse(http.StatusConflict, "IncorrectState", "volume %s is %s", id, describeVolume(volume))
		}
		instance, err := db.LockInstance(ctx, tx, instanceID)
		if errors.Is(err, db.ErrNotFound) {
			return refuse(http.StatusNotFound, "InvalidInstanceID.NotFound", "instance %s does not exist", instanceID)
		}
		if err != nil {
			return err
		}
		if instance.AccountID != volume.AccountID {
			return refuse(http.StatusBadRequest, "InvalidParameterValue", "volume %s and instance %s belong to different accounts", id, instanceID)
		}
		if (instance.State != db.StateRunning && instance.State != db.StateStopped) || instance.PendingAction != "" {
			return refuse(http.StatusConflict, "IncorrectInstanceState", "instance %s is %s", instanceID, describeState(instance))
		}
		attached, err := db.VolumesOfInstance(ctx, tx, instanceID)
		if err != nil {
			return err
		}
		used := map[string]bool{}
		for _, other := range attached {
			used[other.Device] = true
		}
		if device == "" {
			for n := 1; n <= lastVolumeDevice && device == ""; n++ {
				if candidate := "virtio" + strconv.Itoa(n); !used[candidate] {
					device = candidate
				}
			}
			if device == "" {
				return refuse(http.StatusConflict, "AttachmentLimitExceeded", "instance %s already has %d volumes", instanceID, lastVolumeDevice)
			}
		} else if used[device] {
			return refuse(http.StatusBadRequest, "InvalidParameterValue", "%s is already in use on instance %s", device, instanceID)
		}
		if result, err = db.RequestAttach(ctx, tx, id, instanceID, device); err != nil {
			return err
		}
		if audit != nil {
			return audit(tx, result)
		}
		return nil
	})
	if err == nil {
		s.Wake()
	}
	return result, err
}

// DetachVolume detaches an attached volume. The guest should have unmounted it:
// on a running instance this is a hot-unplug, as in EC2.
func (s *Service) DetachVolume(ctx context.Context, id string, authorize func(db.Volume) bool, audit func(pgx.Tx, db.Volume) error) (db.Volume, error) {
	var result db.Volume
	err := pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		volume, err := db.LockVolume(ctx, tx, id)
		if errors.Is(err, db.ErrNotFound) || (err == nil && !authorize(volume)) {
			return volumeNotFound(id)
		}
		if err != nil {
			return err
		}
		result = volume
		switch {
		case volume.PendingAction == db.VolumeActionDetach:
			return nil
		case volume.InstanceID == "":
			return refuse(http.StatusConflict, "IncorrectState", "volume %s is not attached", id)
		case volume.AttachmentState != db.AttachmentAttached || volume.PendingAction != "":
			return refuse(http.StatusConflict, "IncorrectState", "volume %s is %s", id, describeVolume(volume))
		}
		if result, err = db.RequestDetach(ctx, tx, id); err != nil {
			return err
		}
		if audit != nil {
			return audit(tx, result)
		}
		return nil
	})
	if err == nil {
		s.Wake()
	}
	return result, err
}
