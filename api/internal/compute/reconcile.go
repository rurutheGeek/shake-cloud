package compute

import (
	"context"
	"strings"
	"time"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

const missingReason = "Server.VMMissing: the VM is not in the cloud pool"

// RunReconciler corrects settled instances from what Proxmox reports, until ctx ends.
func (s *Service) RunReconciler(ctx context.Context, every time.Duration) {
	ticker := time.NewTicker(every)
	defer ticker.Stop()
	for {
		if err := s.Reconcile(ctx); err != nil && ctx.Err() == nil {
			s.Log.Warn("reconcile failed", "err", err)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

// Reconcile follows power changes made outside the API (a guest shutting
// itself down, an administrator in the Proxmox UI). It never deletes or
// terminates anything: a VM that has disappeared is only noted, because the
// same picture appears when the token's ACL breaks, and acting on it would
// release every account's addresses at once.
func (s *Service) Reconcile(ctx context.Context) error {
	instances, err := db.SettledInstances(ctx, s.Pool)
	if err != nil || len(instances) == 0 {
		return err
	}
	vms, err := s.PVE.ListVMs(ctx)
	if err != nil {
		return err
	}
	missing := 0
	for _, instance := range instances {
		if instance.VMID == nil || findVM(vms, *instance.VMID) == nil {
			missing++
		}
	}
	if missing == len(instances) && missing > 1 {
		s.Log.Error("reconcile skipped: no instance is visible in Proxmox; check the cloudapi token and ACL", "instances", missing)
		return nil
	}
	for _, instance := range instances {
		var vm = (*struct{ Status string })(nil)
		if instance.VMID != nil {
			if found := findVM(vms, *instance.VMID); found != nil {
				vm = &struct{ Status string }{found.Status}
			}
		}
		if vm == nil {
			if instance.StateReason != missingReason {
				s.Log.Error("instance VM missing", "instance_id", instance.ID, "vmid", instance.VMID)
			}
			if err := db.NoteReason(ctx, s.Pool, instance.ID, missingReason); err != nil {
				return err
			}
			continue
		}
		observed := map[string]string{"running": db.StateRunning, "stopped": db.StateStopped}[vm.Status]
		switch {
		case observed == "":
			continue
		case observed != instance.State:
			reason := ""
			if observed == db.StateStopped {
				reason = "Client.InstanceInitiatedShutdown: the VM stopped outside the API"
			}
			s.Log.Info("instance state changed outside the API", "instance_id", instance.ID, "from", instance.State, "to", observed)
			if err := db.ObserveState(ctx, s.Pool, instance.ID, instance.State, observed, reason); err != nil {
				return err
			}
		case strings.HasPrefix(instance.StateReason, "Server.VMMissing"):
			if err := db.NoteReason(ctx, s.Pool, instance.ID, ""); err != nil {
				return err
			}
		}
	}
	return nil
}
