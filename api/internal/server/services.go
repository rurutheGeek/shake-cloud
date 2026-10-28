package server

import (
	"errors"
	"net/http"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/api/internal/compute"
	"github.com/rurutheGeek/shake-cloud/api/internal/db"
)

// Services are always-on containers, private to the account that owns them.
// admins see every account's. Secret values are written, never read back.

type serviceDiskBody struct {
	SizeGiB   int    `json:"size_gib"`
	MountPath string `json:"mount_path"`
}

type serviceBody struct {
	ServiceID     string            `json:"service_id"`
	Name          string            `json:"name"`
	AccountID     string            `json:"account_id"`
	OwnerUsername string            `json:"owner_username,omitempty"`
	Image         string            `json:"image"`
	Port          int               `json:"port,omitempty"`
	MemoryMiB     int               `json:"memory_mib"`
	Env           map[string]string `json:"env"`
	SecretNames   []string          `json:"secret_names"`
	Disk          *serviceDiskBody  `json:"disk,omitempty"`
	Status        string            `json:"status"`
	URL           string            `json:"url,omitempty"`
	CreatedAt     time.Time         `json:"created_at"`
}

func (c *call) mayTouchService(s db.Service) bool {
	return c.principal.account.IsAdmin || s.AccountID == c.principal.account.ID
}

func serviceJSON(status compute.ServiceStatus) serviceBody {
	record := status.Service
	state := "Provisioning"
	if status.Ready {
		state = "Running"
	}
	body := serviceBody{
		ServiceID: record.ID, Name: record.Name, AccountID: record.AccountID,
		OwnerUsername: record.OwnerUsername, Image: record.Image, Port: record.Port,
		MemoryMiB: record.MemoryMiB, Env: record.Env, SecretNames: record.SecretNames,
		Status: state, URL: status.URL, CreatedAt: record.CreatedAt.UTC(),
	}
	if body.Env == nil {
		body.Env = map[string]string{}
	}
	if body.SecretNames == nil {
		body.SecretNames = []string{}
	}
	if record.DiskGiB > 0 {
		body.Disk = &serviceDiskBody{SizeGiB: record.DiskGiB, MountPath: record.MountPath}
	}
	return body
}

func (s *Server) serviceRefused(w http.ResponseWriter, r *http.Request, c *call, id string, err error) {
	if refusal := (*compute.Error)(nil); errors.As(err, &refusal) {
		event := c.event(refusal.Code, nil)
		event.ResourceID = id
		s.recordDenied(r.Context(), event)
	}
	s.computeError(w, r, err)
}

// serviceAudit records the change. Secret values never reach the audit log;
// only their names do.
func serviceAudit(r *http.Request, c *call, tx pgx.Tx, service db.Service) error {
	event := c.event("", map[string]any{
		"owner_account_id": service.AccountID,
		"service_name":     service.Name,
		"image":            service.Image,
		"secret_names":     service.SecretNames,
	})
	event.ResourceID = service.ID
	return db.RecordAudit(r.Context(), tx, event)
}

func (s *Server) ownedService(w http.ResponseWriter, r *http.Request, c *call, service *compute.Service) (compute.ServiceStatus, bool) {
	status, err := service.GetService(r.Context(), r.PathValue("service_id"))
	if err != nil {
		s.computeError(w, r, err)
		return compute.ServiceStatus{}, false
	}
	if !c.mayTouchService(status.Service) {
		s.computeError(w, r, &compute.Error{Status: http.StatusNotFound, Code: "NoSuchService",
			Message: "service does not exist"})
		return compute.ServiceStatus{}, false
	}
	return status, true
}

func (s *Server) describeServices(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	scope := ""
	if !c.principal.account.IsAdmin {
		scope = c.principal.account.ID
	}
	statuses, err := service.ListServices(r.Context(), scope)
	if err != nil {
		s.computeError(w, r, err)
		return
	}
	body := make([]serviceBody, 0, len(statuses))
	for _, status := range statuses {
		if !c.mayTouchService(status.Service) {
			continue
		}
		body = append(body, serviceJSON(status))
	}
	writeJSON(w, http.StatusOK, map[string]any{"services": body})
}

func (s *Server) createService(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	var request struct {
		Name      string            `json:"name"`
		Image     string            `json:"image"`
		Port      int               `json:"port"`
		MemoryMiB int               `json:"memory_mib"`
		Env       map[string]string `json:"env"`
		Secrets   map[string]string `json:"secrets"`
		Disk      *serviceDiskBody  `json:"disk"`
	}
	if !decodeJSON(w, r, &request) {
		return
	}
	spec := compute.ServiceRequest{
		Name: request.Name, Image: request.Image, Port: request.Port, MemoryMiB: request.MemoryMiB,
		Env: request.Env, Secrets: request.Secrets,
	}
	if request.Disk != nil {
		spec.DiskGiB, spec.MountPath = request.Disk.SizeGiB, request.Disk.MountPath
		if spec.DiskGiB == 0 {
			s.computeError(w, r, &compute.Error{Status: http.StatusBadRequest, Code: "InvalidParameterValue",
				Message: "disk.size_gib is required"})
			return
		}
	}
	record, created, err := service.CreateService(r.Context(), c.principal.account.ID, spec,
		func(tx pgx.Tx, sv db.Service) error { return serviceAudit(r, c, tx, sv) })
	if err != nil {
		s.serviceRefused(w, r, c, request.Name, err)
		return
	}
	status, err := service.GetService(r.Context(), record.ID)
	if err != nil {
		s.computeError(w, r, err)
		return
	}
	statusCode := http.StatusOK
	if created {
		statusCode = http.StatusCreated
	}
	writeJSON(w, statusCode, map[string]any{"service": serviceJSON(status)})
}

func (s *Server) describeService(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	status, ok := s.ownedService(w, r, c, service)
	if !ok {
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"service": serviceJSON(status)})
}

func (s *Server) modifyService(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	current, ok := s.ownedService(w, r, c, service)
	if !ok {
		return
	}
	var request struct {
		Image     *string            `json:"image"`
		MemoryMiB *int               `json:"memory_mib"`
		Env       *map[string]string `json:"env"`
		Secrets   *map[string]string `json:"secrets"`
	}
	if !decodeJSON(w, r, &request) {
		return
	}
	change := compute.ServiceChange{Image: request.Image, MemoryMiB: request.MemoryMiB}
	if request.Env != nil {
		change.Env, change.SetEnv = *request.Env, true
	}
	if request.Secrets != nil {
		change.Secrets, change.SetSecret = *request.Secrets, true
	}
	if change.Image == nil && change.MemoryMiB == nil && !change.SetEnv && !change.SetSecret {
		s.computeError(w, r, &compute.Error{Status: http.StatusBadRequest, Code: "InvalidParameterValue",
			Message: "nothing to change"})
		return
	}
	id := current.Service.ID
	if _, err := service.ModifyService(r.Context(), id, change,
		func(tx pgx.Tx, sv db.Service) error { return serviceAudit(r, c, tx, sv) }); err != nil {
		s.serviceRefused(w, r, c, id, err)
		return
	}
	status, err := service.GetService(r.Context(), id)
	if err != nil {
		s.computeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"service": serviceJSON(status)})
}

func (s *Server) deleteService(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	current, ok := s.ownedService(w, r, c, service)
	if !ok {
		return
	}
	id := current.Service.ID
	if err := service.DeleteService(r.Context(), id,
		func(tx pgx.Tx, sv db.Service) error { return serviceAudit(r, c, tx, sv) }); err != nil {
		s.serviceRefused(w, r, c, id, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
