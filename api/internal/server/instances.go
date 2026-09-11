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
	InstanceID       string            `json:"instance_id"`
	AccountID        string            `json:"account_id"`
	ImageID          string            `json:"image_id"`
	InstanceType     string            `json:"instance_type"`
	State            string            `json:"state"`
	StateReason      string            `json:"state_reason,omitempty"`
	PrivateIPAddress string            `json:"private_ip_address,omitempty"`
	MACAddress       string            `json:"mac_address"`
	VCPUs            int               `json:"vcpus"`
	MemoryMiB        int               `json:"memory_mib"`
	MemoryMinMiB     int               `json:"memory_min_mib"`
	RootDiskGiB      int               `json:"root_disk_gib"`
	Tags             map[string]string `json:"tags,omitempty"`
	ClientToken      string            `json:"client_token,omitempty"`
	LaunchTime       time.Time         `json:"launch_time"`
	TerminatedAt     *time.Time        `json:"terminated_at,omitempty"`
}

func instanceJSON(i db.Instance) instanceBody {
	return instanceBody{
		InstanceID: i.ID, AccountID: i.AccountID, ImageID: i.ImageID, InstanceType: i.InstanceType,
		State: i.State, StateReason: i.StateReason,
		// The prefix length is the network's, not the instance's business.
		PrivateIPAddress: strings.SplitN(i.IPAddress, "/", 2)[0],
		MACAddress:       i.MACAddress, VCPUs: i.CPUCores, MemoryMiB: i.MemoryMiB, MemoryMinMiB: i.MemoryMinMiB,
		RootDiskGiB: i.RootDiskGiB,
		Tags:        i.Tags, ClientToken: i.ClientToken, LaunchTime: i.LaunchTime.UTC(), TerminatedAt: timeOrNil(i.TerminatedAt),
	}
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
	writeJSON(w, status, map[string]any{"instance": instanceJSON(instance)})
}

func (s *Server) describeInstances(w http.ResponseWriter, r *http.Request, c *call) {
	if s.computeService(w, r) == nil {
		return
	}
	scope := c.principal.account.ID
	if requested := r.URL.Query().Get("account_id"); requested != "" && requested != c.principal.account.ID {
		if !c.principal.account.IsAdmin {
			writeError(w, r, http.StatusForbidden, "UnauthorizedOperation", "only cloud-admins may list other accounts' instances")
			return
		}
		scope = requested
	} else if c.principal.account.IsAdmin && requested == "" {
		scope = ""
	}
	instances, err := db.ListInstances(r.Context(), s.pool, scope)
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	body := make([]instanceBody, 0, len(instances))
	for _, instance := range instances {
		body = append(body, instanceJSON(instance))
	}
	writeJSON(w, http.StatusOK, map[string]any{"instances": body})
}

func (s *Server) describeInstance(w http.ResponseWriter, r *http.Request, c *call) {
	if s.computeService(w, r) == nil {
		return
	}
	instance, err := db.GetInstance(r.Context(), s.pool, r.PathValue("instance_id"))
	if errors.Is(err, db.ErrNotFound) || (err == nil && !c.mayTouch(instance)) {
		writeError(w, r, http.StatusNotFound, "InvalidInstanceID.NotFound", "instance "+r.PathValue("instance_id")+" does not exist")
		return
	}
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"instance": instanceJSON(instance)})
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
		writeJSON(w, http.StatusAccepted, map[string]any{"instance": instanceJSON(instance)})
	}
}

func (s *Server) describeImages(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	type imageBody struct {
		ImageID string `json:"image_id"`
		Name    string `json:"name"`
		State   string `json:"state"`
		Public  bool   `json:"public"`
	}
	body := make([]imageBody, 0, len(service.Site.Images))
	for id, image := range service.Site.Images {
		body = append(body, imageBody{ImageID: id, Name: image.Name, State: "available", Public: true})
	}
	sort.Slice(body, func(i, j int) bool { return body[i].ImageID < body[j].ImageID })
	writeJSON(w, http.StatusOK, map[string]any{"images": body})
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
