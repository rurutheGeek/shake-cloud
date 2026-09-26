package server

import (
	"context"
	"errors"
	"net/http"
	"strconv"
	"time"
	"unicode/utf8"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/accesskey"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

func (s *Server) getHealth(w http.ResponseWriter, r *http.Request, c *call) {
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()
	if err := s.pool.Ping(ctx); err != nil {
		s.log.Warn("health check: database unreachable", "err", err)
		writeError(w, r, http.StatusServiceUnavailable, "ServiceUnavailable", "database unreachable")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

type callerIdentity struct {
	AccountID      string `json:"account_id"`
	Username       string `json:"username"`
	IsAdmin        bool   `json:"is_admin"`
	CredentialType string `json:"credential_type"`
	AccessKeyID    string `json:"access_key_id,omitempty"`
	AccessKeyScope string `json:"access_key_scope,omitempty"`
}

func (s *Server) getCallerIdentity(w http.ResponseWriter, r *http.Request, c *call) {
	p := c.principal
	writeJSON(w, http.StatusOK, callerIdentity{
		AccountID: p.account.ID, Username: p.account.Username, IsAdmin: p.account.IsAdmin,
		CredentialType: p.credentialType, AccessKeyID: p.accessKeyID, AccessKeyScope: p.accessKeyScope,
	})
}

type accessKeyBody struct {
	AccessKeyID  string     `json:"access_key_id"`
	Status       string     `json:"status"`
	Description  string     `json:"description"`
	Scope        string     `json:"scope"`
	CreateDate   time.Time  `json:"create_date"`
	ExpireDate   *time.Time `json:"expire_date,omitempty"`
	LastUsedDate *time.Time `json:"last_used_date,omitempty"`
}

func (s *Server) keyBody(k db.AccessKey) accessKeyBody {
	return accessKeyBody{
		AccessKeyID: k.ID, Status: k.Status(s.now()), Description: k.Description, Scope: k.Scope,
		CreateDate: k.CreatedAt.UTC(), ExpireDate: timeOrNil(k.ExpiresAt), LastUsedDate: timeOrNil(k.LastUsedAt),
	}
}

func (s *Server) listAccessKeys(w http.ResponseWriter, r *http.Request, c *call) {
	keys, err := db.ListAccessKeys(r.Context(), s.pool, c.principal.account.ID)
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	body := make([]accessKeyBody, 0, len(keys))
	for _, k := range keys {
		body = append(body, s.keyBody(k))
	}
	writeJSON(w, http.StatusOK, map[string]any{"access_keys": body})
}

var errLimitExceeded = errors.New("limit exceeded")

func (s *Server) createAccessKey(w http.ResponseWriter, r *http.Request, c *call) {
	var body struct {
		Description   string `json:"description"`
		ExpiresInDays *int   `json:"expires_in_days"`
		Scope         string `json:"scope"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	if utf8.RuneCountInString(body.Description) > 256 {
		writeError(w, r, http.StatusBadRequest, "ValidationError", "description must be at most 256 characters")
		return
	}
	scope := body.Scope
	if scope == "" {
		scope = db.KeyScopeReadWrite
	}
	if scope != db.KeyScopeReadOnly && scope != db.KeyScopeReadWrite {
		writeError(w, r, http.StatusBadRequest, "ValidationError", "scope must be ReadOnly or ReadWrite")
		return
	}
	var expiresAt *time.Time
	if days := body.ExpiresInDays; days != nil {
		if *days < 1 || *days > 3650 {
			writeError(w, r, http.StatusBadRequest, "ValidationError", "expires_in_days must be between 1 and 3650")
			return
		}
		t := s.now().Add(time.Duration(*days) * 24 * time.Hour)
		expiresAt = &t
	}

	ctx := r.Context()
	account := c.principal.account
	token := accesskey.New()
	var created db.AccessKey
	err := pgx.BeginFunc(ctx, s.pool, func(tx pgx.Tx) error {
		// Two concurrent requests must not both pass the count.
		if err := db.LockAccount(ctx, tx, account.ID); err != nil {
			return err
		}
		active, err := db.CountActiveAccessKeys(ctx, tx, account.ID)
		if err != nil {
			return err
		}
		if active >= maxActiveAccessKeys {
			return errLimitExceeded
		}
		created, err = db.InsertAccessKey(ctx, tx, account.ID, token, body.Description, scope, expiresAt)
		if err != nil {
			return err
		}
		event := c.event("", map[string]any{"description": body.Description, "expires_in_days": body.ExpiresInDays, "scope": scope})
		event.ResourceID = created.ID
		return db.RecordAudit(ctx, tx, event)
	})
	if errors.Is(err, errLimitExceeded) {
		s.recordDenied(ctx, c.event("LimitExceeded", map[string]any{"active_keys": maxActiveAccessKeys}))
		writeError(w, r, http.StatusConflict, "LimitExceeded",
			"an account may hold "+strconv.Itoa(maxActiveAccessKeys)+" active access keys; delete one first")
		return
	}
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"access_key":        s.keyBody(created),
		"secret_access_key": token.String(),
	})
}

var errNoSuchKey = errors.New("no such key")

func (s *Server) deleteAccessKey(w http.ResponseWriter, r *http.Request, c *call) {
	ctx := r.Context()
	id := r.PathValue("access_key_id")
	p := c.principal
	notFound := func() {
		writeError(w, r, http.StatusNotFound, "NoSuchEntity", "no such access key")
	}
	if !accesskey.ValidID(id) {
		notFound()
		return
	}
	denied := false
	err := pgx.BeginFunc(ctx, s.pool, func(tx pgx.Tx) error {
		credential, err := db.LookupAccessKey(ctx, tx, id)
		if errors.Is(err, db.ErrNotFound) {
			return errNoSuchKey
		}
		if err != nil {
			return err
		}
		// Someone else's key answers exactly like a missing one.
		if credential.Account.ID != p.account.ID && !p.account.IsAdmin {
			denied = true
			return errNoSuchKey
		}
		if _, err := db.RevokeAccessKey(ctx, tx, id); errors.Is(err, db.ErrNotFound) {
			return errNoSuchKey
		} else if err != nil {
			return err
		}
		event := c.event("", map[string]any{"owner_account_id": credential.Account.ID})
		event.ResourceID = id
		return db.RecordAudit(ctx, tx, event)
	})
	switch {
	case errors.Is(err, errNoSuchKey):
		if denied {
			event := c.event("AccessDenied", nil)
			event.ResourceID = id
			s.recordDenied(ctx, event)
		}
		notFound()
	case err != nil:
		s.internalError(w, r, err)
	default:
		w.WriteHeader(http.StatusNoContent)
	}
}

type auditEventBody struct {
	EventID         string         `json:"event_id"`
	EventTime       time.Time      `json:"event_time"`
	EventName       string         `json:"event_name"`
	AccountID       string         `json:"account_id,omitempty"`
	AccessKeyID     string         `json:"access_key_id,omitempty"`
	CredentialType  string         `json:"credential_type"`
	SourceIPAddress string         `json:"source_ip_address"`
	UserAgent       string         `json:"user_agent"`
	RequestID       string         `json:"request_id"`
	ResourceID      string         `json:"resource_id,omitempty"`
	ErrorCode       string         `json:"error_code,omitempty"`
	Detail          map[string]any `json:"detail,omitempty"`
}

func (s *Server) lookupEvents(w http.ResponseWriter, r *http.Request, c *call) {
	query := r.URL.Query()
	p := c.principal
	filter := db.AuditFilter{
		AccountID:   p.account.ID,
		AccessKeyID: query.Get("access_key_id"),
		EventName:   query.Get("event_name"),
		Limit:       50,
	}
	if requested := query.Get("account_id"); requested != "" && requested != p.account.ID {
		if !p.account.IsAdmin {
			writeError(w, r, http.StatusForbidden, "UnauthorizedOperation", "only admins may read other accounts' events")
			return
		}
		filter.AccountID = requested
	} else if p.account.IsAdmin && requested == "" {
		filter.AccountID = ""
	}
	if raw := query.Get("max_results"); raw != "" {
		n, err := strconv.Atoi(raw)
		if err != nil || n < 1 || n > 1000 {
			writeError(w, r, http.StatusBadRequest, "ValidationError", "max_results must be between 1 and 1000")
			return
		}
		filter.Limit = n
	}
	if raw := query.Get("next_token"); raw != "" {
		n, err := strconv.ParseInt(raw, 10, 64)
		if err != nil || n < 1 {
			writeError(w, r, http.StatusBadRequest, "ValidationError", "next_token is not valid")
			return
		}
		filter.BeforeID = n
	}

	events, err := db.LookupAuditEvents(r.Context(), s.pool, filter)
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	body := make([]auditEventBody, 0, len(events))
	for _, e := range events {
		body = append(body, auditEventBody{
			EventID: strconv.FormatInt(e.EventID, 10), EventTime: e.EventTime.UTC(), EventName: e.EventName,
			AccountID: e.AccountID, AccessKeyID: e.AccessKeyID, CredentialType: e.CredentialType,
			SourceIPAddress: e.SourceIPAddress, UserAgent: e.UserAgent, RequestID: e.RequestID,
			ResourceID: e.ResourceID, ErrorCode: e.ErrorCode, Detail: e.Detail,
		})
	}
	response := map[string]any{"events": body}
	if len(events) == filter.Limit {
		response["next_token"] = strconv.FormatInt(events[len(events)-1].EventID, 10)
	}
	writeJSON(w, http.StatusOK, response)
}
