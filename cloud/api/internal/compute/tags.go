package compute

import (
	"context"
	"errors"
	"net/http"
	"net/url"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/seed"
)

// SetInstanceTags replaces the tags of an instance.
//
// `Name` is the display name. Changing it renames the VM in the hypervisor and
// in the ledger, but not inside the guest: its hostname was written by
// cloud-init at first boot and stays what it was.
func (s *Service) SetInstanceTags(ctx context.Context, instanceID string, tags map[string]string, authorize func(db.Instance) bool, audit func(pgx.Tx, db.Instance) error) (db.Instance, error) {
	if tags == nil {
		tags = map[string]string{}
	}
	if err := validateTags(tags); err != nil {
		return db.Instance{}, err
	}
	var result db.Instance
	err := pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		instance, err := db.LockInstance(ctx, tx, instanceID)
		if errors.Is(err, db.ErrNotFound) || (err == nil && !authorize(instance)) {
			return refuse(http.StatusNotFound, "InvalidInstanceID.NotFound", "instance %s does not exist", instanceID)
		}
		if err != nil {
			return err
		}
		if instance.State == db.StateTerminated || instance.State == db.StateShuttingDown {
			return refuse(http.StatusConflict, "IncorrectInstanceState", "instance %s is %s", instanceID, describeState(instance))
		}
		name := tags["Name"]
		if name != instance.Name && instance.VMID != nil && instance.VMCreated {
			// The hypervisor first, as in Modify: a failure leaves the ledger
			// with the old name, which matches the VM.
			params := url.Values{"name": {seed.Hostname(name, instance.ID)}}
			if err := s.PVE.UpdateVMConfig(ctx, *instance.VMID, params); err != nil {
				return err
			}
		}
		if err := db.SetInstanceTags(ctx, tx, instanceID, name, tags); err != nil {
			return err
		}
		if result, err = db.GetInstance(ctx, tx, instanceID); err != nil {
			return err
		}
		if audit != nil {
			return audit(tx, result)
		}
		return nil
	})
	if err == nil {
		// The ledger carries the name, and the groups follow it.
		s.wakeLedger()
	}
	return result, err
}
