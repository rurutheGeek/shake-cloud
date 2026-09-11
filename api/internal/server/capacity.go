package server

import (
	"net/http"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/compute"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/site"
)

// The limits an administrator may change, and what the cloud has left. The
// deployment declares the defaults (platform/terraform/cloud.yaml); this is how
// they are read and overridden while it runs.

type quotaBody struct {
	Instances   int `json:"instances"`
	VCPUs       int `json:"vcpus"`
	MemoryMiB   int `json:"memory_mib"`
	RootDiskGiB int `json:"root_disk_gib"`
	Volumes     int `json:"volumes"`
	VolumeGiB   int `json:"volume_gib"`
}

type volumeSizeBody struct {
	Min int `json:"min"`
	Max int `json:"max"`
}

type rootDiskBody struct {
	Min     int `json:"min"`
	Default int `json:"default"`
	Max     int `json:"max"`
}

type capacityLimitsBody struct {
	MemoryBudgetMiB      int `json:"memory_budget_mib"`
	NodeMemoryReserveMiB int `json:"node_memory_reserve_mib"`
	VMDiskMaxUsedPercent int `json:"vm_disk_max_used_percent"`
	ImageStoreMinFreeMiB int `json:"image_store_min_free_mib"`
	MaxImageGiB          int `json:"max_image_gib"`
}

type limitsBody struct {
	AccountQuota  quotaBody          `json:"account_quota"`
	RootDiskGiB   rootDiskBody       `json:"root_disk_gib"`
	VolumeSizeGiB volumeSizeBody     `json:"volume_size_gib"`
	Capacity      capacityLimitsBody `json:"capacity"`
}

func limitsJSON(l site.Limits) limitsBody {
	return limitsBody{
		AccountQuota: quotaBody{Instances: l.AccountQuota.Instances, VCPUs: l.AccountQuota.VCPUs,
			MemoryMiB: l.AccountQuota.MemoryMiB, RootDiskGiB: l.AccountQuota.RootDiskGiB,
			Volumes: l.AccountQuota.Volumes, VolumeGiB: l.AccountQuota.VolumeGiB},
		VolumeSizeGiB: volumeSizeBody{Min: l.VolumeSizeGiB.Min, Max: l.VolumeSizeGiB.Max},
		RootDiskGiB:   rootDiskBody{Min: l.RootDiskGiB.Min, Default: l.RootDiskGiB.Default, Max: l.RootDiskGiB.Max},
		Capacity: capacityLimitsBody{MemoryBudgetMiB: l.Capacity.MemoryBudgetMiB,
			NodeMemoryReserveMiB: l.Capacity.NodeMemoryReserveMiB,
			VMDiskMaxUsedPercent: l.Capacity.VMDiskMaxUsedPercent,
			ImageStoreMinFreeMiB: l.Capacity.ImageStoreMinFreeMiB,
			MaxImageGiB:          l.Capacity.MaxImageGiB},
	}
}

// The patch shape: a field left out is not overridden. It is also what is
// echoed back as "overrides", so an administrator can see at a glance which
// limits they have changed and which are the deployment's own.
type quotaPatch struct {
	Instances   *int `json:"instances,omitempty"`
	VCPUs       *int `json:"vcpus,omitempty"`
	MemoryMiB   *int `json:"memory_mib,omitempty"`
	RootDiskGiB *int `json:"root_disk_gib,omitempty"`
	Volumes     *int `json:"volumes,omitempty"`
	VolumeGiB   *int `json:"volume_gib,omitempty"`
}

type volumeSizePatch struct {
	Min *int `json:"min,omitempty"`
	Max *int `json:"max,omitempty"`
}

type rootDiskPatch struct {
	Min     *int `json:"min,omitempty"`
	Default *int `json:"default,omitempty"`
	Max     *int `json:"max,omitempty"`
}

type capacityPatch struct {
	MemoryBudgetMiB      *int `json:"memory_budget_mib,omitempty"`
	NodeMemoryReserveMiB *int `json:"node_memory_reserve_mib,omitempty"`
	VMDiskMaxUsedPercent *int `json:"vm_disk_max_used_percent,omitempty"`
	ImageStoreMinFreeMiB *int `json:"image_store_min_free_mib,omitempty"`
	MaxImageGiB          *int `json:"max_image_gib,omitempty"`
}

type limitsPatch struct {
	AccountQuota  *quotaPatch      `json:"account_quota,omitempty"`
	RootDiskGiB   *rootDiskPatch   `json:"root_disk_gib,omitempty"`
	VolumeSizeGiB *volumeSizePatch `json:"volume_size_gib,omitempty"`
	Capacity      *capacityPatch   `json:"capacity,omitempty"`
}

func (p limitsPatch) overrides() db.LimitOverrides {
	var o db.LimitOverrides
	if q := p.AccountQuota; q != nil {
		o.AccountInstances, o.AccountVCPUs = q.Instances, q.VCPUs
		o.AccountMemoryMiB, o.AccountRootDiskGiB = q.MemoryMiB, q.RootDiskGiB
		o.AccountVolumes, o.AccountVolumeGiB = q.Volumes, q.VolumeGiB
	}
	if v := p.VolumeSizeGiB; v != nil {
		o.VolumeMinGiB, o.VolumeMaxGiB = v.Min, v.Max
	}
	if d := p.RootDiskGiB; d != nil {
		o.RootDiskMinGiB, o.RootDiskDefaultGiB, o.RootDiskMaxGiB = d.Min, d.Default, d.Max
	}
	if c := p.Capacity; c != nil {
		o.MemoryBudgetMiB, o.NodeMemoryReserveMiB = c.MemoryBudgetMiB, c.NodeMemoryReserveMiB
		o.VMDiskMaxUsedPercent, o.ImageStoreMinFreeMiB = c.VMDiskMaxUsedPercent, c.ImageStoreMinFreeMiB
		o.MaxImageGiB = c.MaxImageGiB
	}
	return o
}

func overridesJSON(o db.LimitOverrides) limitsPatch {
	var p limitsPatch
	if o.AccountInstances != nil || o.AccountVCPUs != nil || o.AccountMemoryMiB != nil || o.AccountRootDiskGiB != nil ||
		o.AccountVolumes != nil || o.AccountVolumeGiB != nil {
		p.AccountQuota = &quotaPatch{Instances: o.AccountInstances, VCPUs: o.AccountVCPUs,
			MemoryMiB: o.AccountMemoryMiB, RootDiskGiB: o.AccountRootDiskGiB,
			Volumes: o.AccountVolumes, VolumeGiB: o.AccountVolumeGiB}
	}
	if o.VolumeMinGiB != nil || o.VolumeMaxGiB != nil {
		p.VolumeSizeGiB = &volumeSizePatch{Min: o.VolumeMinGiB, Max: o.VolumeMaxGiB}
	}
	if o.RootDiskMinGiB != nil || o.RootDiskDefaultGiB != nil || o.RootDiskMaxGiB != nil {
		p.RootDiskGiB = &rootDiskPatch{Min: o.RootDiskMinGiB, Default: o.RootDiskDefaultGiB, Max: o.RootDiskMaxGiB}
	}
	if o.MemoryBudgetMiB != nil || o.NodeMemoryReserveMiB != nil || o.VMDiskMaxUsedPercent != nil ||
		o.ImageStoreMinFreeMiB != nil || o.MaxImageGiB != nil {
		p.Capacity = &capacityPatch{MemoryBudgetMiB: o.MemoryBudgetMiB, NodeMemoryReserveMiB: o.NodeMemoryReserveMiB,
			VMDiskMaxUsedPercent: o.VMDiskMaxUsedPercent, ImageStoreMinFreeMiB: o.ImageStoreMinFreeMiB,
			MaxImageGiB: o.MaxImageGiB}
	}
	return p
}

func limitsResponse(service *compute.Service, effective site.Limits, o db.LimitOverrides) map[string]any {
	body := map[string]any{
		"limits":    limitsJSON(effective),
		"defaults":  limitsJSON(service.Site.Limits),
		"overrides": overridesJSON(o),
	}
	if o.UpdatedAt != nil {
		body["updated_at"] = o.UpdatedAt.UTC()
		if o.UpdatedBy != "" {
			body["updated_by"] = o.UpdatedBy
		}
	}
	return body
}

func (s *Server) describeLimits(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	effective, overrides, err := service.EffectiveLimits(r.Context(), nil)
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, limitsResponse(service, effective, overrides))
}

// updateLimits replaces every override at once, so a limit an administrator
// leaves out of the request goes back to the deployment's default rather than
// silently keeping a value they have forgotten about.
func (s *Server) updateLimits(w http.ResponseWriter, r *http.Request, c *call) {
	// Checked before anything else, so a user who may not do this cannot tell
	// whether the deployment has instances configured.
	if !c.principal.account.IsAdmin {
		s.recordDenied(r.Context(), c.event("UnauthorizedOperation", map[string]any{"reason": "requires cloud-admins"}))
		writeError(w, r, http.StatusForbidden, "UnauthorizedOperation", "only cloud-admins may change limits")
		return
	}
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	var patch limitsPatch
	if !decodeJSON(w, r, &patch) {
		return
	}
	effective, stored, err := service.SetLimits(r.Context(), patch.overrides(), c.principal.account.ID,
		func(tx pgx.Tx) error {
			// The overrides asked for and the limits they produce, so reading the
			// log does not require reconstructing them.
			detail := map[string]any{"overrides": overridesJSON(patch.overrides()), "limits": limitsJSON(effectiveOf(service, patch))}
			return db.RecordAudit(r.Context(), tx, c.event("", detail))
		})
	if err != nil {
		s.computeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, limitsResponse(service, effective, stored))
}

// effectiveOf is what the request adds up to, for the audit record.
func effectiveOf(service *compute.Service, patch limitsPatch) site.Limits {
	return compute.WithOverrides(service.Site.Limits, patch.overrides())
}

func (s *Server) describeCapacity(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	account := c.principal.account
	capacity, err := service.Capacity(r.Context(), account.ID, account.IsAdmin)
	if err != nil {
		s.computeError(w, r, err)
		return
	}

	type usageBody struct {
		AccountID   string `json:"account_id,omitempty"`
		Username    string `json:"username,omitempty"`
		Instances   int    `json:"instances"`
		VCPUs       int    `json:"vcpus"`
		MemoryMiB   int    `json:"memory_mib"`
		RootDiskGiB int    `json:"root_disk_gib"`
		Volumes     int    `json:"volumes"`
		VolumeGiB   int    `json:"volume_gib"`
	}
	usage := func(u db.Usage) usageBody {
		return usageBody{Instances: u.Instances, VCPUs: u.VCPUs, MemoryMiB: u.MemoryMiB, RootDiskGiB: u.RootDiskGiB,
			Volumes: u.Volumes, VolumeGiB: u.VolumeGiB}
	}
	node := capacity.Node
	body := map[string]any{
		"node": map[string]any{
			"name": node.Name, "cpu_model": node.CPUModel, "cpu_cores": node.CPUCores, "cpu_threads": node.CPUThreads,
			"cpu_usage_percent": round1(node.CPUUsagePercent), "memory_total_mib": node.MemoryTotalMiB,
			"memory_used_mib": node.MemoryUsedMiB, "memory_available_mib": node.MemoryAvailableMiB,
			"kernel_version": node.KernelVersion, "pve_version": node.PVEVersion, "uptime_seconds": node.UptimeSeconds,
		},
		"cloud":   usage(capacity.Cloud),
		"account": usage(capacity.Account),
		"limits":  limitsJSON(capacity.Limits),
	}
	stores := make([]map[string]any, 0, len(capacity.Storage))
	for _, store := range capacity.Storage {
		stores = append(stores, map[string]any{
			"name": store.Name, "purpose": store.Purpose, "total_mib": store.TotalMiB,
			"used_mib": store.UsedMiB, "avail_mib": store.AvailMiB, "used_percent": round1(store.UsedPercent),
			"max_used_percent": store.MaxUsedPercent, "min_free_mib": store.MinFreeMiB,
		})
	}
	body["storage"] = stores
	if account.IsAdmin {
		accounts := make([]usageBody, 0, len(capacity.Accounts))
		for _, a := range capacity.Accounts {
			entry := usage(a.Usage)
			entry.AccountID, entry.Username = a.AccountID, a.Username
			accounts = append(accounts, entry)
		}
		body["accounts"] = accounts
	}
	writeJSON(w, http.StatusOK, body)
}

// round1 keeps percentages readable instead of shipping float noise.
func round1(value float64) float64 {
	return float64(int64(value*10+0.5)) / 10
}
