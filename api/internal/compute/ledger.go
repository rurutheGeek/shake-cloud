package compute

import (
	"context"
	"regexp"
	"slices"
	"time"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/netbox"
)

// Ledger is the part of *netbox.Client that registers instances as virtual
// machines, which is what the Ansible inventory reads.
type Ledger interface {
	ClusterID(ctx context.Context, name string) (int, error)
	VMsByTag(ctx context.Context, tag string) ([]netbox.VM, error)
	CreateVM(ctx context.Context, clusterID int, spec netbox.VMSpec) (netbox.VM, error)
	UpdateVM(ctx context.Context, id int, spec netbox.VMSpec) error
	DeleteVM(ctx context.Context, id int) error
	EnsureVMInterface(ctx context.Context, vmID int, name string) (int, error)
	AssignIP(ctx context.Context, ipID, interfaceID int) error
	SetPrimaryIP(ctx context.Context, vmID, ipID int) error
}

// ledgerInterface is the one interface an instance's address hangs from. The
// name matches what Terraform gives the platform VMs.
const ledgerInterface = "primary"

var ledgerName = regexp.MustCompile(`^i-[0-9a-f]{17}$`)

// RunLedger keeps NetBox's virtual machines in step with the instances, until
// ctx ends. It does nothing when the site declares no ledger cluster.
func (s *Service) RunLedger(ctx context.Context, every time.Duration) {
	if s.Ledger == nil || s.Site.Ledger.Cluster == "" {
		return
	}
	ticker := time.NewTicker(every)
	defer ticker.Stop()
	for {
		if err := s.SyncLedger(ctx); err != nil && ctx.Err() == nil {
			s.Log.Warn("ledger sync failed", "err", err)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

// SyncLedger makes NetBox list one virtual machine per instance that has an
// address: named by instance ID, active while running, with the address as
// its primary IP. Entries of instances that no longer exist are removed.
//
// It converges rather than reacting to each change, so instances that existed
// before the ledger was switched on are picked up, and a NetBox outage costs
// nothing but a delay. It touches only VMs that carry the cloud's tag and an
// instance ID for a name; what Terraform registers is never in that set.
func (s *Service) SyncLedger(ctx context.Context) error {
	instances, err := db.UnterminatedInstances(ctx, s.Pool)
	if err != nil {
		return err
	}
	return s.syncLedger(ctx, instances)
}

// syncLedger converges NetBox on instances, which must be every instance that
// still exists: an entry whose instance is not listed is removed.
func (s *Service) syncLedger(ctx context.Context, instances []db.Instance) error {
	existing, err := s.Ledger.VMsByTag(ctx, NetBoxTag)
	if err != nil {
		return err
	}
	registered := make(map[string]netbox.VM, len(existing))
	for _, vm := range existing {
		registered[vm.Name] = vm
	}
	// One entry that NetBox refuses (a tag that does not exist yet, say) must
	// not keep every other instance out of the inventory, so each is tried
	// and the first failure is reported after the pass.
	var failed error
	clusterID := 0
	live := make(map[string]bool, len(instances))
	for _, instance := range instances {
		live[instance.ID] = true
		if instance.NetBoxIPID == nil {
			// No address yet (still launching) or never one (adopted VMs).
			continue
		}
		vm, found := registered[instance.ID]
		if !found && clusterID == 0 {
			if clusterID, err = s.Ledger.ClusterID(ctx, s.Site.Ledger.Cluster); err != nil {
				return err
			}
		}
		if err := s.registerInstance(ctx, instance, vm, found, clusterID); err != nil {
			s.Log.Warn("ledger entry failed", "instance_id", instance.ID, "err", err)
			if failed == nil {
				failed = err
			}
		}
	}
	for name, vm := range registered {
		if live[name] || !ledgerName.MatchString(name) {
			continue
		}
		if err := s.Ledger.DeleteVM(ctx, vm.ID); err != nil {
			return err
		}
		s.Log.Info("ledger entry removed", "instance_id", name)
	}
	return failed
}

func (s *Service) registerInstance(ctx context.Context, instance db.Instance, vm netbox.VM, found bool, clusterID int) error {
	spec := s.ledgerSpec(instance)
	var err error
	switch {
	case !found:
		if vm, err = s.Ledger.CreateVM(ctx, clusterID, spec); err != nil {
			return err
		}
		s.Log.Info("ledger entry created", "instance_id", instance.ID, "tags", spec.Tags)
	case ledgerDiffers(vm, spec):
		if err := s.Ledger.UpdateVM(ctx, vm.ID, spec); err != nil {
			return err
		}
		s.Log.Info("ledger entry updated", "instance_id", instance.ID, "status", spec.Status, "tags", spec.Tags)
	}
	if vm.PrimaryIP4 == *instance.NetBoxIPID {
		return nil
	}
	interfaceID, err := s.Ledger.EnsureVMInterface(ctx, vm.ID, ledgerInterface)
	if err != nil {
		return err
	}
	if err := s.Ledger.AssignIP(ctx, *instance.NetBoxIPID, interfaceID); err != nil {
		return err
	}
	return s.Ledger.SetPrimaryIP(ctx, vm.ID, *instance.NetBoxIPID)
}

// ledgerSpec is what NetBox should say about an instance. Only a running
// instance is active: the inventory filters on that, so a stopped VM is not
// handed to Ansible as a target.
func (s *Service) ledgerSpec(instance db.Instance) netbox.VMSpec {
	status := "offline"
	if instance.State == db.StateRunning {
		status = "active"
	}
	description := instance.OwnerUsername
	if instance.Name != "" {
		description = instance.Name + " / " + instance.OwnerUsername
	}
	return netbox.VMSpec{
		Name: instance.ID, Status: status, Description: description,
		VCPUs: instance.CPUCores, MemoryMB: instance.MemoryMiB,
		Tags: s.ledgerTags(instance),
	}
}

// ledgerTags decides the Ansible groups, which follow NetBox tags. An
// instance's own tags never do: anyone can name a VM, and a group decides
// which secrets a playbook copies onto a host. Groups come from the site
// declaration, by name, and only for the accounts it trusts.
func (s *Service) ledgerTags(instance db.Instance) []string {
	tags := []string{NetBoxTag}
	if instance.Name == "" || !slices.Contains(s.Site.Ledger.GroupAccounts, instance.AccountID) {
		return tags
	}
	for _, tag := range s.Site.Ledger.TagsByName[instance.Name] {
		if !slices.Contains(tags, tag) {
			tags = append(tags, tag)
		}
	}
	return tags
}

func ledgerDiffers(vm netbox.VM, spec netbox.VMSpec) bool {
	have, want := slices.Clone(vm.Tags), slices.Clone(spec.Tags)
	slices.Sort(have)
	slices.Sort(want)
	return vm.Status != spec.Status || vm.Description != spec.Description ||
		vm.VCPUs != spec.VCPUs || vm.MemoryMB != spec.MemoryMB || !slices.Equal(have, want)
}
