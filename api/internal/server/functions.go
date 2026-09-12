package server

import (
	"errors"
	"net/http"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/compute"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

// Functions are serverless HTTP services backed by Knative, private to the
// account that owns them. admins see every account's.

type functionBody struct {
	FunctionID    string    `json:"function_id"`
	Name          string    `json:"name"`
	AccountID     string    `json:"account_id"`
	OwnerUsername string    `json:"owner_username,omitempty"`
	Image         string    `json:"image"`
	Status        string    `json:"status"`
	URL           string    `json:"url,omitempty"`
	CreatedAt     time.Time `json:"created_at"`
}

func (c *call) mayTouchFunction(f db.Function) bool {
	return c.principal.account.IsAdmin || f.AccountID == c.principal.account.ID
}

func functionJSON(status compute.FunctionStatus) functionBody {
	state := "Provisioning"
	if status.Ready {
		state = "Ready"
	}
	return functionBody{
		FunctionID: status.Function.ID, Name: status.Function.Name, AccountID: status.Function.AccountID,
		OwnerUsername: status.Function.OwnerUsername, Image: status.Function.Image,
		Status: state, URL: status.URL, CreatedAt: status.Function.CreatedAt.UTC(),
	}
}

func (s *Server) functionRefused(w http.ResponseWriter, r *http.Request, c *call, id string, err error) {
	if refusal := (*compute.Error)(nil); errors.As(err, &refusal) {
		event := c.event(refusal.Code, nil)
		event.ResourceID = id
		s.recordDenied(r.Context(), event)
	}
	s.computeError(w, r, err)
}

func functionAudit(r *http.Request, c *call, tx pgx.Tx, function db.Function, detail map[string]any) error {
	if detail == nil {
		detail = map[string]any{}
	}
	detail["owner_account_id"] = function.AccountID
	detail["function_name"] = function.Name
	event := c.event("", detail)
	event.ResourceID = function.ID
	return db.RecordAudit(r.Context(), tx, event)
}

func (s *Server) describeFunctions(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	scope := ""
	if !c.principal.account.IsAdmin {
		scope = c.principal.account.ID
	}
	statuses, err := service.ListFunctions(r.Context(), scope)
	if err != nil {
		s.computeError(w, r, err)
		return
	}
	body := make([]functionBody, 0, len(statuses))
	for _, status := range statuses {
		if !c.mayTouchFunction(status.Function) {
			continue
		}
		body = append(body, functionJSON(status))
	}
	writeJSON(w, http.StatusOK, map[string]any{"functions": body})
}

func (s *Server) createFunction(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	var request struct {
		Name  string `json:"name"`
		Image string `json:"image"`
	}
	if !decodeJSON(w, r, &request) {
		return
	}
	function, created, err := service.CreateFunction(r.Context(), c.principal.account.ID,
		request.Name, request.Image,
		func(tx pgx.Tx, f db.Function) error { return functionAudit(r, c, tx, f, nil) })
	if err != nil {
		s.functionRefused(w, r, c, request.Name, err)
		return
	}
	status, err := service.GetFunction(r.Context(), function.ID)
	if err != nil {
		s.computeError(w, r, err)
		return
	}
	statusCode := http.StatusOK
	if created {
		statusCode = http.StatusCreated
	}
	writeJSON(w, statusCode, map[string]any{"function": functionJSON(status)})
}

func (s *Server) describeFunction(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	status, err := service.GetFunction(r.Context(), r.PathValue("function_id"))
	if err != nil {
		s.computeError(w, r, err)
		return
	}
	if !c.mayTouchFunction(status.Function) {
		s.computeError(w, r, &compute.Error{Status: http.StatusNotFound, Code: "NoSuchFunction",
			Message: "function does not exist"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"function": functionJSON(status)})
}

func (s *Server) deleteFunction(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	id := r.PathValue("function_id")
	status, err := service.GetFunction(r.Context(), id)
	if err != nil {
		s.computeError(w, r, err)
		return
	}
	if !c.mayTouchFunction(status.Function) {
		s.computeError(w, r, &compute.Error{Status: http.StatusNotFound, Code: "NoSuchFunction",
			Message: "function does not exist"})
		return
	}
	if err := service.DeleteFunction(r.Context(), id,
		func(tx pgx.Tx, f db.Function) error { return functionAudit(r, c, tx, f, nil) }); err != nil {
		s.functionRefused(w, r, c, id, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
