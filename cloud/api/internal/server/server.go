// Package server is the HTTP side of the API: the JSON endpoints described by
// cloud/openapi/shakecloud.yaml, the OIDC login, and the Phase 1 portal page.
package server

import (
	"context"
	"log/slog"
	"net/http"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/compute"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/config"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

// An account may hold this many active keys: enough for a laptop, a desktop
// and CI plus one being rotated in.
const maxActiveAccessKeys = 5

type Server struct {
	cfg  config.Config
	pool *pgxpool.Pool
	log  *slog.Logger
	oidc *oidcClient
	now  func() time.Time
	// Compute serves the instance endpoints. It is nil when the deployment has
	// no Proxmox or NetBox settings, and those endpoints then answer 503.
	Compute *compute.Service
}

func New(cfg config.Config, pool *pgxpool.Pool, log *slog.Logger) *Server {
	return &Server{
		cfg:  cfg,
		pool: pool,
		log:  log,
		oidc: newOIDCClient(cfg),
		now:  time.Now,
	}
}

type authMode int

const (
	public authMode = iota
	anyCredential
	// sessionOnly refuses access keys, so a leaked key cannot mint more keys.
	sessionOnly
)

type route struct {
	method      string
	pattern     string
	operationID string
	auth        authMode
	handle      func(*Server, http.ResponseWriter, *http.Request, *call)
}

// routes is the API table. routes_test.go checks it against the OpenAPI
// document in both directions.
func routes() []route {
	return []route{
		{"GET", "/healthz", "GetHealth", public, (*Server).getHealth},
		{"GET", "/auth/login", "StartLogin", public, (*Server).startLogin},
		{"GET", "/auth/callback", "CompleteLogin", public, (*Server).completeLogin},
		{"POST", "/auth/logout", "Logout", public, (*Server).logout},
		{"GET", "/v1/caller-identity", "GetCallerIdentity", anyCredential, (*Server).getCallerIdentity},
		{"GET", "/v1/access-keys", "ListAccessKeys", anyCredential, (*Server).listAccessKeys},
		{"POST", "/v1/access-keys", "CreateAccessKey", sessionOnly, (*Server).createAccessKey},
		{"DELETE", "/v1/access-keys/{access_key_id}", "DeleteAccessKey", anyCredential, (*Server).deleteAccessKey},
		{"GET", "/v1/audit-events", "LookupEvents", anyCredential, (*Server).lookupEvents},
		{"GET", "/v1/images", "DescribeImages", anyCredential, (*Server).describeImages},
		{"GET", "/v1/instance-types", "DescribeInstanceTypes", anyCredential, (*Server).describeInstanceTypes},
		{"GET", "/v1/capacity", "DescribeCapacity", anyCredential, (*Server).describeCapacity},
		{"GET", "/v1/limits", "DescribeLimits", anyCredential, (*Server).describeLimits},
		{"PUT", "/v1/limits", "UpdateLimits", anyCredential, (*Server).updateLimits},
		{"POST", "/v1/instances", "RunInstances", anyCredential, (*Server).runInstances},
		{"GET", "/v1/instances", "DescribeInstances", anyCredential, (*Server).describeInstances},
		{"GET", "/v1/instances/{instance_id}", "DescribeInstance", anyCredential, (*Server).describeInstance},
		{"DELETE", "/v1/instances/{instance_id}", "TerminateInstance", anyCredential, instanceAction(db.ActionTerminate)},
		{"POST", "/v1/instances/{instance_id}/start", "StartInstance", anyCredential, instanceAction(db.ActionStart)},
		{"POST", "/v1/instances/{instance_id}/stop", "StopInstance", anyCredential, instanceAction(db.ActionStop)},
		{"POST", "/v1/instances/{instance_id}/reboot", "RebootInstance", anyCredential, instanceAction(db.ActionReboot)},
	}
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	for _, rt := range routes() {
		mux.Handle(rt.method+" "+rt.pattern, s.endpoint(rt))
	}
	mux.HandleFunc("GET /{$}", s.portal)
	mux.Handle("GET /static/", staticFiles())
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		writeError(w, r, http.StatusNotFound, "NotFound", "no such endpoint")
	})

	// Rejects cross-site browser requests with unsafe methods, which is what
	// makes the session cookie safe to accept on POST and DELETE. Clients that
	// send neither Sec-Fetch-Site nor Origin (Terraform, curl) pass through.
	csrf := http.NewCrossOriginProtection()
	csrf.SetDenyHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		writeError(w, r, http.StatusForbidden, "CrossOriginRequestBlocked", "cross-origin request refused")
	}))
	return s.observe(csrf.Handler(mux))
}

// endpoint authenticates according to the route before calling its handler.
func (s *Server) endpoint(rt route) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		c := newCall(r, rt.operationID)
		if rt.auth != public {
			p, failure := s.authenticate(r, c)
			if failure != nil {
				if failure.status == http.StatusUnauthorized {
					w.Header().Set("WWW-Authenticate", `Bearer realm="shake-cloud"`)
				}
				writeError(w, r, failure.status, failure.code, failure.message)
				return
			}
			c.principal = p
			if rt.auth == sessionOnly && p.credentialType != db.CredentialSession {
				s.recordDenied(r.Context(), c.event("UnauthorizedOperation", map[string]any{"reason": "requires a portal session"}))
				writeError(w, r, http.StatusForbidden, "UnauthorizedOperation",
					"this operation requires a portal login; an access key cannot create access keys")
				return
			}
		}
		rt.handle(s, w, r, c)
	})
}

// RunJanitor deletes expired sessions and login attempts until ctx ends.
func (s *Server) RunJanitor(ctx context.Context) {
	ticker := time.NewTicker(10 * time.Minute)
	defer ticker.Stop()
	for {
		if err := db.DeleteExpired(ctx, s.pool); err != nil && ctx.Err() == nil {
			s.log.Warn("deleting expired sessions failed", "err", err)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

// recordDenied writes an audit event for a refused request. The request fails
// either way, so a write error is logged rather than returned.
func (s *Server) recordDenied(ctx context.Context, e db.AuditEvent) {
	if err := db.RecordAudit(ctx, s.pool, e); err != nil {
		s.log.Error("audit write failed", "err", err, "event_name", e.EventName, "request_id", e.RequestID)
	}
}
