package server

import (
	"errors"
	"net/http"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/compute"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

// Databases are PostgreSQL appliances backed by CloudNativePG, private to the
// account that owns them. cloud-admins see every account's.

type databaseBody struct {
	DatabaseID     string    `json:"database_id"`
	Name           string    `json:"name"`
	AccountID      string    `json:"account_id"`
	OwnerUsername  string    `json:"owner_username,omitempty"`
	Engine         string    `json:"engine"`
	EngineVersion  string    `json:"engine_version"`
	StorageGiB     int       `json:"storage_gib"`
	Status         string    `json:"status"`
	Instances      int       `json:"instances"`
	ReadyInstances int       `json:"ready_instances"`
	Host           string    `json:"host"`
	Port           int       `json:"port"`
	CreatedAt      time.Time `json:"created_at"`
}

type databaseCredentialsBody struct {
	Username string `json:"username"`
	Password string `json:"password"`
	Host     string `json:"host"`
	Port     string `json:"port"`
	Database string `json:"database"`
}

func (c *call) mayTouchDatabase(d db.Database) bool {
	return c.principal.account.IsAdmin || d.AccountID == c.principal.account.ID
}

func databaseJSON(status compute.DatabaseStatus) databaseBody {
	record := status.Database
	return databaseBody{
		DatabaseID: record.ID, Name: record.Name, AccountID: record.AccountID,
		OwnerUsername: record.OwnerUsername, Engine: record.Engine, EngineVersion: record.EngineVersion,
		StorageGiB: record.StorageGiB, Status: status.Phase, Instances: status.Instances,
		ReadyInstances: status.Ready,
		// The operator's read-write Service is <id>-rw in the database namespace.
		Host: record.ID + "-rw." + record.Namespace + ".svc", Port: 5432,
		CreatedAt: record.CreatedAt.UTC(),
	}
}

func (s *Server) databaseRefused(w http.ResponseWriter, r *http.Request, c *call, id string, err error) {
	if refusal := (*compute.Error)(nil); errors.As(err, &refusal) {
		event := c.event(refusal.Code, nil)
		event.ResourceID = id
		s.recordDenied(r.Context(), event)
	}
	s.computeError(w, r, err)
}

func databaseAudit(r *http.Request, c *call, tx pgx.Tx, database db.Database, detail map[string]any) error {
	if detail == nil {
		detail = map[string]any{}
	}
	detail["owner_account_id"] = database.AccountID
	detail["database_name"] = database.Name
	event := c.event("", detail)
	event.ResourceID = database.ID
	return db.RecordAudit(r.Context(), tx, event)
}

func (s *Server) describeDatabases(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	scope := ""
	if !c.principal.account.IsAdmin {
		scope = c.principal.account.ID
	}
	statuses, err := service.ListDatabases(r.Context(), scope)
	if err != nil {
		s.computeError(w, r, err)
		return
	}
	body := make([]databaseBody, 0, len(statuses))
	for _, status := range statuses {
		if !c.mayTouchDatabase(status.Database) {
			continue
		}
		body = append(body, databaseJSON(status))
	}
	writeJSON(w, http.StatusOK, map[string]any{"databases": body})
}

func (s *Server) createDatabase(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	var request struct {
		Name       string `json:"name"`
		StorageGiB int    `json:"storage_gib"`
	}
	if !decodeJSON(w, r, &request) {
		return
	}
	database, created, err := service.CreateDatabase(r.Context(), c.principal.account.ID,
		request.Name, request.StorageGiB,
		func(tx pgx.Tx, d db.Database) error { return databaseAudit(r, c, tx, d, nil) })
	if err != nil {
		s.databaseRefused(w, r, c, request.Name, err)
		return
	}
	status, err := service.GetDatabase(r.Context(), database.ID)
	if err != nil {
		s.computeError(w, r, err)
		return
	}
	statusCode := http.StatusOK
	if created {
		statusCode = http.StatusCreated
	}
	writeJSON(w, statusCode, map[string]any{"database": databaseJSON(status)})
}

func (s *Server) describeDatabase(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	status, err := service.GetDatabase(r.Context(), r.PathValue("database_id"))
	if err != nil {
		s.computeError(w, r, err)
		return
	}
	if !c.mayTouchDatabase(status.Database) {
		s.computeError(w, r, &compute.Error{Status: http.StatusNotFound, Code: "NoSuchDatabase",
			Message: "database does not exist"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"database": databaseJSON(status)})
}

func (s *Server) deleteDatabase(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	id := r.PathValue("database_id")
	status, err := service.GetDatabase(r.Context(), id)
	if err != nil {
		s.computeError(w, r, err)
		return
	}
	if !c.mayTouchDatabase(status.Database) {
		s.computeError(w, r, &compute.Error{Status: http.StatusNotFound, Code: "NoSuchDatabase",
			Message: "database does not exist"})
		return
	}
	if err := service.DeleteDatabase(r.Context(), id,
		func(tx pgx.Tx, d db.Database) error { return databaseAudit(r, c, tx, d, nil) }); err != nil {
		s.databaseRefused(w, r, c, id, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) getDatabaseCredentials(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	id := r.PathValue("database_id")
	record, credentials, err := service.DatabaseCredentials(r.Context(), id)
	if err != nil {
		s.computeError(w, r, err)
		return
	}
	if !c.mayTouchDatabase(record) {
		s.computeError(w, r, &compute.Error{Status: http.StatusNotFound, Code: "NoSuchDatabase",
			Message: "database does not exist"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"credentials": databaseCredentialsBody{
		Username: credentials.Username, Password: credentials.Password,
		Host: credentials.Host, Port: credentials.Port, Database: credentials.Database,
	}})
}
