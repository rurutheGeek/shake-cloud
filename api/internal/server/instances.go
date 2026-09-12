package server

import (
	"errors"
	"net/http"
	"sort"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/compute"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

type instanceBody struct {
	InstanceID    string `json:"instance_id"`
	AccountID     string `json:"account_id"`
	OwnerUsername string `json:"owner_username,omitempty"`
	ImageID       string `json:"image_id"`
	ImageName     string `json:"image_name,omitempty"`
	// GuestOS is "windows" for a Windows guest. InstallISOID is set when the
	// instance installs itself from ISO media instead of an image.
	GuestOS      string `json:"guest_os,omitempty"`
	InstallISOID string `json:"install_iso_id,omitempty"`
	DriverISOID  string `json:"driver_iso_id,omitempty"`
	// InstanceType is absent when the size was given as explicit numbers.
	InstanceType string `json:"instance_type,omitempty"`
	State        string `json:"state"`
	// PendingAction is the power/lifecycle action the worker is still carrying
	// out ("reboot", "stop", ...). Empty when the instance is settled. The
	// portal shows it so a second click can explain "再起動中です" instead of
	// returning a generic incorrect-state error.
	PendingAction    string            `json:"pending_action,omitempty"`
	StateReason      string            `json:"state_reason,omitempty"`
	PrivateIPAddress string            `json:"private_ip_address,omitempty"`
	MACAddress       string            `json:"mac_address"`
	VCPUs            int               `json:"vcpus"`
	MemoryMiB        int               `json:"memory_mib"`
	MemoryMinMiB     int               `json:"memory_min_mib"`
	Ballooning       bool              `json:"ballooning"`
	RootDiskGiB      int               `json:"root_disk_gib"`
	KeyName          string            `json:"key_name,omitempty"`
	Tags             map[string]string `json:"tags,omitempty"`
	ClientToken      string            `json:"client_token,omitempty"`
	LaunchTime       time.Time         `json:"launch_time"`
	TerminatedAt     *time.Time        `json:"terminated_at,omitempty"`
	// Adopted marks an instance that already existed and was registered into
	// the cloud, rather than created by a launch. It has no source image.
	Adopted bool `json:"adopted,omitempty"`
	// SecurityGroups is empty for instances from before groups existed, which
	// are unfiltered. FirewallState is "applying" while a change to the groups
	// is still on its way to the VM.
	SecurityGroups []instanceGroupBody `json:"security_groups"`
	FirewallState  string              `json:"firewall_state"`
}

type instanceGroupBody struct {
	GroupID   string `json:"group_id"`
	GroupName string `json:"group_name"`
}

// instanceJSON renders an instance. Everyone may see that an instance exists
// and what it holds, so that the cloud's use is visible to the people sharing
// it; owned decides only whether the caller's own client_token comes back.
func instanceJSON(service *compute.Service, i db.Instance, owned bool, groups []db.GroupRef) instanceBody {
	body := instanceBody{
		InstanceID: i.ID, AccountID: i.AccountID, OwnerUsername: i.OwnerUsername,
		ImageID: i.ImageID, ImageName: service.Site.Images[i.ImageID].Name, InstanceType: i.InstanceType,
		GuestOS: i.GuestOS, InstallISOID: i.InstallISOID, DriverISOID: i.DriverISOID,
		State: i.State, PendingAction: i.PendingAction, StateReason: i.StateReason,
		// The prefix length is the network's, not the instance's business.
		PrivateIPAddress: strings.SplitN(i.IPAddress, "/", 2)[0],
		MACAddress:       i.MACAddress, VCPUs: i.CPUCores, MemoryMiB: i.MemoryMiB, MemoryMinMiB: i.MemoryMinMiB,
		Ballooning:  i.Ballooning,
		RootDiskGiB: i.RootDiskGiB, KeyName: i.KeyName,
		Tags: i.Tags, LaunchTime: i.LaunchTime.UTC(), TerminatedAt: timeOrNil(i.TerminatedAt),
		Adopted: i.Adopted,
	}
	if owned {
		body.ClientToken = i.ClientToken
	}
	body.SecurityGroups = make([]instanceGroupBody, 0, len(groups))
	for _, group := range groups {
		body.SecurityGroups = append(body.SecurityGroups, instanceGroupBody{GroupID: group.GroupID, GroupName: group.GroupName})
	}
	body.FirewallState = "in-sync"
	if i.FirewallGeneration != i.FirewallApplied {
		body.FirewallState = "applying"
	}
	return body
}

// writeInstance renders one instance with its groups.
func (s *Server) writeInstance(w http.ResponseWriter, r *http.Request, status int, service *compute.Service, instance db.Instance, owned bool) {
	groups, err := db.InstanceGroups(r.Context(), s.pool, []string{instance.ID})
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, status, map[string]any{"instance": instanceJSON(service, instance, owned, groups[instance.ID])})
}

// mayAct reports whether the caller may change this instance, writing the
// refusal itself. Now that every instance is visible, refusing with 404 would
// deny something the caller can see listed, so this says 403 instead.
func (s *Server) mayAct(w http.ResponseWriter, r *http.Request, c *call, id string) bool {
	instance, err := db.GetInstance(r.Context(), s.pool, id)
	switch {
	case errors.Is(err, db.ErrNotFound):
		writeError(w, r, http.StatusNotFound, "InvalidInstanceID.NotFound", "instance "+id+" does not exist")
	case err != nil:
		s.internalError(w, r, err)
	case !c.mayTouch(instance):
		event := c.event("UnauthorizedOperation", map[string]any{"owner_account_id": instance.AccountID})
		event.ResourceID = id
		s.recordDenied(r.Context(), event)
		writeError(w, r, http.StatusForbidden, "UnauthorizedOperation",
			"instance "+id+" belongs to another account; only its owner or a cloud-admin may change it")
	default:
		return true
	}
	return false
}

// computeService returns the service, or nil after writing the error when
// instances are not configured (no Proxmox or NetBox settings).
func (s *Server) computeService(w http.ResponseWriter, r *http.Request) *compute.Service {
	if s.Compute == nil {
		writeError(w, r, http.StatusServiceUnavailable, "ServiceUnavailable", "instances are not configured on this deployment")
		return nil
	}
	return s.Compute
}

// computeError maps the service's refusals onto the JSON error body.
func (s *Server) computeError(w http.ResponseWriter, r *http.Request, err error) {
	var refusal *compute.Error
	if errors.As(err, &refusal) {
		writeError(w, r, refusal.Status, refusal.Code, refusal.Message)
		return
	}
	s.internalError(w, r, err)
}

// mayTouch decides whether the caller sees an instance at all. Someone else's
// instance answers exactly like one that does not exist.
func (c *call) mayTouch(i db.Instance) bool {
	return c.principal.account.IsAdmin || i.AccountID == c.principal.account.ID
}

func (s *Server) runInstances(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	var request compute.RunRequest
	if !decodeJSON(w, r, &request) {
		return
	}
	instance, created, err := service.Run(r.Context(), c.principal.account.ID, request, func(tx pgx.Tx, i db.Instance) error {
		event := c.event("", map[string]any{"image_id": i.ImageID, "instance_type": i.InstanceType, "vmid": i.VMID})
		event.ResourceID = i.ID
		return db.RecordAudit(r.Context(), tx, event)
	})
	if err != nil {
		if refusal := (*compute.Error)(nil); errors.As(err, &refusal) {
			event := c.event(refusal.Code, map[string]any{"image_id": request.ImageID, "instance_type": request.InstanceType})
			s.recordDenied(r.Context(), event)
		}
		s.computeError(w, r, err)
		return
	}
	status := http.StatusAccepted
	if !created {
		// A repeated client_token returns the original instance unchanged.
		status = http.StatusOK
	}
	s.writeInstance(w, r, status, service, instance, true)
}

// adoptInstance registers a VM that already exists into the cloud. Only
// admins may: it picks another account to own the VM and takes over a
// machine that already has its own contents.
func (s *Server) adoptInstance(w http.ResponseWriter, r *http.Request, c *call) {
	if !c.principal.account.IsAdmin {
		s.recordDenied(r.Context(), c.event("UnauthorizedOperation", map[string]any{"reason": "requires admins"}))
		writeError(w, r, http.StatusForbidden, "UnauthorizedOperation", "only admins may adopt a VM")
		return
	}
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	var request compute.AdoptRequest
	if !decodeJSON(w, r, &request) {
		return
	}
	instance, err := service.Adopt(r.Context(), request, func(tx pgx.Tx, i db.Instance) error {
		event := c.event("", map[string]any{"owner_account_id": i.AccountID, "vmid": i.VMID, "adopted": true})
		event.ResourceID = i.ID
		return db.RecordAudit(r.Context(), tx, event)
	})
	if err != nil {
		if refusal := (*compute.Error)(nil); errors.As(err, &refusal) {
			event := c.event(refusal.Code, map[string]any{"vmid": request.VMID, "account_id": request.AccountID})
			s.recordDenied(r.Context(), event)
		}
		s.computeError(w, r, err)
		return
	}
	s.writeInstance(w, r, http.StatusCreated, service, instance, true)
}

// describeInstances lists every instance in the cloud, to whoever asks. Two
// people sharing one host need to see what the other is running to make sense
// of the capacity page; acting on an instance still needs to own it.
func (s *Server) describeInstances(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	instances, err := db.ListInstances(r.Context(), s.pool, r.URL.Query().Get("account_id"))
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	ids := make([]string, 0, len(instances))
	for _, instance := range instances {
		ids = append(ids, instance.ID)
	}
	groups, err := db.InstanceGroups(r.Context(), s.pool, ids)
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	body := make([]instanceBody, 0, len(instances))
	for _, instance := range instances {
		body = append(body, instanceJSON(service, instance, c.mayTouch(instance), groups[instance.ID]))
	}
	writeJSON(w, http.StatusOK, map[string]any{"instances": body})
}

func (s *Server) describeInstance(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	instance, err := db.GetInstance(r.Context(), s.pool, r.PathValue("instance_id"))
	if errors.Is(err, db.ErrNotFound) {
		writeError(w, r, http.StatusNotFound, "InvalidInstanceID.NotFound", "instance "+r.PathValue("instance_id")+" does not exist")
		return
	}
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	s.writeInstance(w, r, http.StatusOK, service, instance, c.mayTouch(instance))
}

// modifyInstance changes an instance's size. Only admins may: a resize
// reaches into a VM someone else is using, and the quota it is re-checked
// against is the account's, not the caller's.
func (s *Server) modifyInstance(w http.ResponseWriter, r *http.Request, c *call) {
	if !c.principal.account.IsAdmin {
		s.recordDenied(r.Context(), c.event("UnauthorizedOperation", map[string]any{"reason": "requires admins"}))
		writeError(w, r, http.StatusForbidden, "UnauthorizedOperation", "only admins may change an instance's size")
		return
	}
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	var request compute.ModifyRequest
	if !decodeJSON(w, r, &request) {
		return
	}
	id := r.PathValue("instance_id")
	instance, err := service.Modify(r.Context(), id, request, func(tx pgx.Tx, i db.Instance) error {
		event := c.event("", map[string]any{"owner_account_id": i.AccountID, "vcpus": i.CPUCores,
			"memory_mib": i.MemoryMiB, "memory_min_mib": i.MemoryMinMiB, "ballooning": i.Ballooning,
			"root_disk_gib": i.RootDiskGiB})
		event.ResourceID = i.ID
		return db.RecordAudit(r.Context(), tx, event)
	})
	if err != nil {
		if refusal := (*compute.Error)(nil); errors.As(err, &refusal) {
			event := c.event(refusal.Code, nil)
			event.ResourceID = id
			s.recordDenied(r.Context(), event)
		}
		s.computeError(w, r, err)
		return
	}
	s.writeInstance(w, r, http.StatusOK, service, instance, true)
}

// instanceAction handles terminate, start, stop and reboot, which differ only
// in the word they record.
func instanceAction(action string) func(*Server, http.ResponseWriter, *http.Request, *call) {
	return func(s *Server, w http.ResponseWriter, r *http.Request, c *call) {
		service := s.computeService(w, r)
		if service == nil {
			return
		}
		id := r.PathValue("instance_id")
		if !s.mayAct(w, r, c, id) {
			return
		}
		instance, err := service.Request(r.Context(), id, action, c.mayTouch, func(tx pgx.Tx, i db.Instance) error {
			event := c.event("", map[string]any{"owner_account_id": i.AccountID, "state": i.State})
			event.ResourceID = i.ID
			return db.RecordAudit(r.Context(), tx, event)
		})
		if err != nil {
			if refusal := (*compute.Error)(nil); errors.As(err, &refusal) {
				event := c.event(refusal.Code, nil)
				event.ResourceID = id
				s.recordDenied(r.Context(), event)
			}
			s.computeError(w, r, err)
			return
		}
		s.writeInstance(w, r, http.StatusAccepted, service, instance, c.mayTouch(instance))
	}
}

func (s *Server) describeInstanceTypes(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	type typeBody struct {
		InstanceType string `json:"instance_type"`
		VCPUs        int    `json:"vcpus"`
		MemoryMiB    int    `json:"memory_mib"`
		MemoryMinMiB int    `json:"memory_min_mib"`
	}
	body := make([]typeBody, 0, len(service.Site.InstanceTypes))
	for name, t := range service.Site.InstanceTypes {
		body = append(body, typeBody{InstanceType: name, VCPUs: t.CPUCores, MemoryMiB: t.MemoryMiB, MemoryMinMiB: t.MemoryMinMiB})
	}
	sort.Slice(body, func(i, j int) bool { return body[i].MemoryMiB < body[j].MemoryMiB })
	writeJSON(w, http.StatusOK, map[string]any{"instance_types": body})
}
