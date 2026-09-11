package compute

import (
	"context"
	"net/http"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/site"
)

// Purposes tell the reader which limit applies to which storage.
const (
	PurposeInstanceDisks = "instance_disks"
	PurposeImages        = "images_and_seed_isos"
)

// Capacity is what the machine has, what the cloud has handed out of it, and
// the limits in force. It answers the question a user actually has before
// launching something big: is there room, and am I allowed.
//
// Allotted figures are sums of maxima, not measurements of use. With ballooning
// a guest may be holding far less than its ceiling, so the node's own memory
// figures and the allotted total will not agree, and both are shown.
type Capacity struct {
	Node    NodeCapacity
	Storage []StorageCapacity
	// Cloud is every account's instances together; Account is the caller's.
	Cloud   db.Usage
	Account db.Usage
	Limits  site.Limits
	// Accounts is filled in for cloud-admins only.
	Accounts []db.PerAccountUsage
}

type NodeCapacity struct {
	Name string
	// Cores are physical, Threads are what the scheduler sees.
	CPUModel           string
	CPUCores           int
	CPUThreads         int
	CPUUsagePercent    float64
	MemoryTotalMiB     int64
	MemoryUsedMiB      int64
	MemoryAvailableMiB int64
	KernelVersion      string
	PVEVersion         string
	UptimeSeconds      int64
}

type StorageCapacity struct {
	Name        string
	Purpose     string
	TotalMiB    int64
	UsedMiB     int64
	AvailMiB    int64
	UsedPercent float64
	// The limit that applies to this store; 0 when none does.
	MaxUsedPercent int
	MinFreeMiB     int
}

// Capacity reads the node and the ledger. accountID is whose own usage to
// report; accounts is true for a cloud-admin, who also gets the per-account
// breakdown.
func (s *Service) Capacity(ctx context.Context, accountID string, accounts bool) (Capacity, error) {
	limits, _, err := s.EffectiveLimits(ctx, s.Pool)
	if err != nil {
		return Capacity{}, err
	}
	status, err := s.PVE.NodeStatus(ctx)
	if err != nil {
		return Capacity{}, s.unavailable(err)
	}
	capacity := Capacity{
		Limits: limits,
		Node: NodeCapacity{
			Name: s.Site.Node, CPUModel: status.CPUInfo.Model,
			CPUCores: status.CPUInfo.Cores, CPUThreads: status.CPUInfo.CPUs,
			CPUUsagePercent:    status.Usage * 100,
			MemoryTotalMiB:     status.Memory.Total >> 20,
			MemoryUsedMiB:      (status.Memory.Total - status.Memory.Free) >> 20,
			MemoryAvailableMiB: status.Memory.Available >> 20,
			KernelVersion:      status.KernelVersion, PVEVersion: status.PVEVersion,
			UptimeSeconds: status.Uptime,
		},
	}

	stores := []struct {
		name, purpose  string
		maxUsedPercent int
		minFreeMiB     int
	}{
		{s.Site.Storage.VMDisks, PurposeInstanceDisks, limits.Capacity.VMDiskMaxUsedPercent, 0},
		{s.Site.Storage.Images, PurposeImages, 0, limits.Capacity.ImageStoreMinFreeMiB},
	}
	for _, store := range stores {
		if store.name == "" || (len(capacity.Storage) > 0 && capacity.Storage[0].Name == store.name) {
			continue // one deployment may use a single store for both
		}
		st, err := s.PVE.StorageStatus(ctx, store.name)
		if err != nil {
			return Capacity{}, s.unavailable(err)
		}
		used := 0.0
		if st.Total > 0 {
			used = float64(st.Used) * 100 / float64(st.Total)
		}
		capacity.Storage = append(capacity.Storage, StorageCapacity{
			Name: store.name, Purpose: store.purpose,
			TotalMiB: st.Total >> 20, UsedMiB: st.Used >> 20, AvailMiB: st.Avail >> 20,
			UsedPercent: used, MaxUsedPercent: store.maxUsedPercent, MinFreeMiB: store.minFreeMiB,
		})
	}

	if capacity.Cloud, err = db.CloudUsage(ctx, s.Pool); err != nil {
		return Capacity{}, err
	}
	if accountID != "" {
		if capacity.Account, err = db.AccountUsage(ctx, s.Pool, accountID); err != nil {
			return Capacity{}, err
		}
	}
	if accounts {
		if capacity.Accounts, err = db.UsageByAccount(ctx, s.Pool); err != nil {
			return Capacity{}, err
		}
	}
	return capacity, nil
}

// SetLimits stores an administrator's overrides after checking that the set
// they add up to is usable. The write and its audit event share one
// transaction, so a recorded change is one that took effect.
func (s *Service) SetLimits(ctx context.Context, overrides db.LimitOverrides, byAccountID string,
	audit func(pgx.Tx) error) (site.Limits, db.LimitOverrides, error) {
	if err := ValidateLimits(WithOverrides(s.Site.Limits, overrides)); err != nil {
		return site.Limits{}, db.LimitOverrides{}, err
	}
	var stored db.LimitOverrides
	err := pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		var err error
		if stored, err = db.SetLimitOverrides(ctx, tx, overrides, byAccountID); err != nil {
			return err
		}
		if audit != nil {
			return audit(tx)
		}
		return nil
	})
	if err != nil {
		return site.Limits{}, db.LimitOverrides{}, err
	}
	return WithOverrides(s.Site.Limits, stored), stored, nil
}

// ValidateLimits refuses a set of limits that cannot be satisfied by any
// request, which would leave the cloud unable to launch anything without
// telling the administrator why. 0 is allowed where it means "unlimited"; the
// root disk sizes are the one place a 0 would be meaningless.
func ValidateLimits(l site.Limits) error {
	bad := func(format string, args ...any) error {
		return refuse(http.StatusBadRequest, "ValidationError", format, args...)
	}
	q, d, c := l.AccountQuota, l.RootDiskGiB, l.Capacity
	switch {
	case q.Instances < 0 || q.VCPUs < 0 || q.MemoryMiB < 0 || q.RootDiskGiB < 0:
		return bad("account quotas cannot be negative; use 0 for unlimited")
	case d.Min <= 0 || d.Default <= 0 || d.Max <= 0:
		return bad("root disk sizes must be at least 1 GiB")
	case d.Min > d.Default || d.Default > d.Max:
		return bad("root disk sizes must satisfy min <= default <= max, got %d <= %d <= %d", d.Min, d.Default, d.Max)
	case c.MemoryBudgetMiB < 0 || c.NodeMemoryReserveMiB < 0 || c.ImageStoreMinFreeMiB < 0:
		return bad("capacity limits cannot be negative; use 0 to turn one off")
	case c.VMDiskMaxUsedPercent < 0 || c.VMDiskMaxUsedPercent > 100:
		return bad("vm_disk_max_used_percent must be between 0 and 100")
	}
	return nil
}
