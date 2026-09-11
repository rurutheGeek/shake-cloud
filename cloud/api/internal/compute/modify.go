package compute

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strconv"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

// ModifyRequest is the body of ModifyInstance. Every field is optional and the
// ones left out keep their current value.
type ModifyRequest struct {
	VCPUs        *int  `json:"vcpus"`
	MemoryMiB    *int  `json:"memory_mib"`
	MemoryMinMiB *int  `json:"memory_min_mib"`
	Ballooning   *bool `json:"ballooning"`
	RootDiskGiB  *int  `json:"root_disk_gib"`
}

func (r ModifyRequest) empty() bool {
	return r.VCPUs == nil && r.MemoryMiB == nil && r.MemoryMinMiB == nil &&
		r.Ballooning == nil && r.RootDiskGiB == nil
}

// target is the size the instance ends up with. A floor that no longer fits the
// ceiling is recomputed rather than refused: the caller asked to change the
// memory, not to keep a floor they never mentioned.
func (r ModifyRequest) target(i db.Instance) Spec {
	spec := Spec{CPUCores: i.CPUCores, MemoryMiB: i.MemoryMiB, MemoryMinMiB: i.MemoryMinMiB, Ballooning: i.Ballooning}
	if r.VCPUs != nil {
		spec.CPUCores = *r.VCPUs
	}
	if r.MemoryMiB != nil {
		spec.MemoryMiB = *r.MemoryMiB
	}
	if r.Ballooning != nil {
		spec.Ballooning = *r.Ballooning
	}
	switch {
	case !spec.Ballooning:
		spec.MemoryMinMiB = 0
	case r.MemoryMinMiB != nil:
		spec.MemoryMinMiB = *r.MemoryMinMiB
	case r.MemoryMiB != nil || spec.MemoryMinMiB == 0 || spec.MemoryMinMiB > spec.MemoryMiB:
		// A changed ceiling recomputes the floor, exactly as at launch: a floor
		// nobody mentioned should not survive the number it was derived from.
		// This also covers ballooning being turned back on.
		spec.MemoryMinMiB = balloonFloor(spec.MemoryMiB)
	}
	return spec
}

// Modify changes an existing instance's cpu, memory, ballooning or disk size.
//
// The hypervisor is changed before the ledger, so a failure leaves the ledger
// behind the VM rather than ahead of it: the reconciler and a repeated call can
// recover from that, whereas a ledger claiming resources the VM does not have
// would mis-price every later admission. Quota is checked first, in its own
// transaction, so the window between the check and the write is short but not
// zero — acceptable for an operation only administrators can perform.
func (s *Service) Modify(ctx context.Context, id string, r ModifyRequest, audit func(pgx.Tx, db.Instance) error) (db.Instance, error) {
	if r.empty() {
		return db.Instance{}, refuse(http.StatusBadRequest, "InvalidParameterValue",
			"give at least one of vcpus, memory_mib, memory_min_mib, ballooning or root_disk_gib")
	}
	instance, err := db.GetInstance(ctx, s.Pool, id)
	if errors.Is(err, db.ErrNotFound) {
		return db.Instance{}, refuse(http.StatusNotFound, "InvalidInstanceID.NotFound", "instance %s does not exist", id)
	}
	if err != nil {
		return db.Instance{}, err
	}
	limits, _, err := s.EffectiveLimits(ctx, s.Pool)
	if err != nil {
		return db.Instance{}, err
	}

	target := r.target(instance)
	if err := validateSpec(target); err != nil {
		return db.Instance{}, err
	}
	disk := instance.RootDiskGiB
	if r.RootDiskGiB != nil {
		disk = *r.RootDiskGiB
		if disk < instance.RootDiskGiB {
			// Shrinking a disk destroys whatever is past the new end, and the
			// guest filesystem has no idea it happened.
			return db.Instance{}, refuse(http.StatusBadRequest, "InvalidParameterValue",
				"a root disk can only grow: it is %d GiB and cannot become %d GiB", instance.RootDiskGiB, disk)
		}
		if disk > limits.RootDiskGiB.Max {
			return db.Instance{}, refuse(http.StatusBadRequest, "InvalidParameterValue",
				"root_disk_gib must be at most %d", limits.RootDiskGiB.Max)
		}
	}

	current := Spec{CPUCores: instance.CPUCores, MemoryMiB: instance.MemoryMiB,
		MemoryMinMiB: instance.MemoryMinMiB, Ballooning: instance.Ballooning}
	if target == current && disk == instance.RootDiskGiB {
		return instance, nil
	}
	switch {
	case instance.State == db.StateTerminated || instance.PendingAction == db.ActionTerminate:
		return db.Instance{}, refuse(http.StatusConflict, "IncorrectInstanceState", "instance %s is %s", id, describeState(instance))
	case instance.PendingAction != "":
		// Racing the worker would write a size it is about to overwrite.
		return db.Instance{}, refuse(http.StatusConflict, "IncorrectInstanceState", "instance %s is %s", id, describeState(instance))
	case target != current && instance.State != db.StateStopped:
		// Proxmox accepts these while a VM runs but only applies them at the
		// next start, which would make the ledger disagree with the guest.
		return db.Instance{}, refuse(http.StatusConflict, "IncorrectInstanceState",
			"vcpus, memory and ballooning can only be changed while the instance is stopped; it is %s", describeState(instance))
	case instance.VMID == nil || !instance.VMCreated:
		return db.Instance{}, refuse(http.StatusConflict, "IncorrectInstanceState", "instance %s has no VM yet", id)
	}

	if err := s.checkHost(ctx, target, max(0, target.MemoryMiB-instance.MemoryMiB), limits); err != nil {
		return db.Instance{}, err
	}
	err = pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		if err := db.LockCapacity(ctx, tx); err != nil {
			return err
		}
		return s.checkQuota(ctx, tx, instance.AccountID, target, disk, limits, &instance)
	})
	if err != nil {
		return db.Instance{}, err
	}

	vmid := *instance.VMID
	if owned, err := s.owns(ctx, vmid, instance); err != nil || !owned {
		return db.Instance{}, errors.Join(err, refuse(http.StatusConflict, "IncorrectInstanceState",
			"VM %d does not belong to %s", vmid, instance.ID))
	}
	params := url.Values{}
	if target.CPUCores != current.CPUCores {
		params.Set("cores", strconv.Itoa(target.CPUCores))
	}
	if target.MemoryMiB != current.MemoryMiB {
		params.Set("memory", strconv.Itoa(target.MemoryMiB))
	}
	if target.MemoryMinMiB != current.MemoryMinMiB {
		// 0 is how Proxmox disables the balloon driver.
		params.Set("balloon", strconv.Itoa(target.MemoryMinMiB))
	}
	if len(params) > 0 {
		if err := s.PVE.UpdateVMConfig(ctx, vmid, params); err != nil {
			return db.Instance{}, fmt.Errorf("update VM config: %w", err)
		}
	}
	if disk > instance.RootDiskGiB {
		if err := s.PVE.ResizeDisk(ctx, vmid, "virtio0", fmt.Sprintf("%dG", disk)); err != nil {
			return db.Instance{}, fmt.Errorf("resize disk: %w", err)
		}
	}

	var modified db.Instance
	err = pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		var err error
		modified, err = db.SetSpec(ctx, tx, id, target.CPUCores, target.MemoryMiB, target.MemoryMinMiB, target.Ballooning, disk)
		if err != nil {
			return err
		}
		if audit != nil {
			return audit(tx, modified)
		}
		return nil
	})
	if err != nil {
		return db.Instance{}, err
	}
	s.Log.Info("instance resized", "instance_id", id, "vcpus", target.CPUCores,
		"memory_mib", target.MemoryMiB, "memory_min_mib", target.MemoryMinMiB, "root_disk_gib", disk)
	return modified, nil
}
