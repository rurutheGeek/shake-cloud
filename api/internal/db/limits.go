package db

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5"
)

// LimitOverrides are the limits an administrator has changed. A nil field means
// the deployment default applies, so this table never holds a second copy of a
// limit nobody touched. Applying them to the defaults is the caller's job
// (compute.applyOverrides), which is where both halves are known.
//
// A zero value is not the same as nil: 0 is "unlimited" for the quota fields.
type LimitOverrides struct {
	AccountInstances     *int
	AccountVCPUs         *int
	AccountMemoryMiB     *int
	AccountRootDiskGiB   *int
	RootDiskMinGiB       *int
	RootDiskDefaultGiB   *int
	RootDiskMaxGiB       *int
	MemoryBudgetMiB      *int
	NodeMemoryReserveMiB *int
	VMDiskMaxUsedPercent *int
	ImageStoreMinFreeMiB *int
	UpdatedAt            *time.Time
	UpdatedBy            string
}

const limitColumns = `account_instances, account_vcpus, account_memory_mib, account_root_disk_gib,
	root_disk_min_gib, root_disk_default_gib, root_disk_max_gib,
	memory_budget_mib, node_memory_reserve_mib, vm_disk_max_used_percent, image_store_min_free_mib,
	updated_at, coalesce(updated_by, '')`

func scanLimitOverrides(row pgx.Row) (LimitOverrides, error) {
	var o LimitOverrides
	err := row.Scan(&o.AccountInstances, &o.AccountVCPUs, &o.AccountMemoryMiB, &o.AccountRootDiskGiB,
		&o.RootDiskMinGiB, &o.RootDiskDefaultGiB, &o.RootDiskMaxGiB,
		&o.MemoryBudgetMiB, &o.NodeMemoryReserveMiB, &o.VMDiskMaxUsedPercent, &o.ImageStoreMinFreeMiB,
		&o.UpdatedAt, &o.UpdatedBy)
	return o, noRows(err)
}

// GetLimitOverrides reads the single row. The migration inserts it, so this
// does not have to cope with it being absent.
func GetLimitOverrides(ctx context.Context, q Querier) (LimitOverrides, error) {
	return scanLimitOverrides(q.QueryRow(ctx, `SELECT `+limitColumns+` FROM limit_overrides WHERE id`))
}

// SetLimitOverrides replaces every override at once: a field left nil goes back
// to the deployment default. PUT semantics, so an administrator cannot end up
// with a limit they forgot they had set.
func SetLimitOverrides(ctx context.Context, q Querier, o LimitOverrides, byAccountID string) (LimitOverrides, error) {
	return scanLimitOverrides(q.QueryRow(ctx, `UPDATE limit_overrides SET
		account_instances = $1, account_vcpus = $2, account_memory_mib = $3, account_root_disk_gib = $4,
		root_disk_min_gib = $5, root_disk_default_gib = $6, root_disk_max_gib = $7,
		memory_budget_mib = $8, node_memory_reserve_mib = $9, vm_disk_max_used_percent = $10,
		image_store_min_free_mib = $11, updated_at = now(), updated_by = nullif($12::text, '')
		WHERE id RETURNING `+limitColumns,
		o.AccountInstances, o.AccountVCPUs, o.AccountMemoryMiB, o.AccountRootDiskGiB,
		o.RootDiskMinGiB, o.RootDiskDefaultGiB, o.RootDiskMaxGiB,
		o.MemoryBudgetMiB, o.NodeMemoryReserveMiB, o.VMDiskMaxUsedPercent, o.ImageStoreMinFreeMiB,
		byAccountID))
}
