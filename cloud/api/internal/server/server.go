// Package server is the HTTP side of the API: the JSON endpoints described by
// cloud/openapi/shakecloud.yaml, the OIDC login, and the Phase 1 portal page.
package server

import (
	"context"
	"log/slog"
	"net/http"
	"regexp"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/compute"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/config"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

// An account may hold this many active keys: enough for a laptop, a desktop
// and CI plus one being rotated in.
const maxActiveAccessKeys = 5

// keyName is what an SSH key pair may be called. It matches the database's own
// check, so a name the API accepts is one the database accepts.
var keyName = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9 ._:@-]{0,63}$`)

type Server struct {
	cfg  config.Config
	pool *pgxpool.Pool
	log  *slog.Logger
	oidc *oidcClient
	now  func() time.Time
	// consoles holds console URLs handed out in the last few minutes.
	consoles *consoleStore
	// Compute serves the instance endpoints. It is nil when the deployment has
	// no Proxmox or NetBox settings, and those endpoints then answer 503.
	Compute *compute.Service
}

func New(cfg config.Config, pool *pgxpool.Pool, log *slog.Logger) *Server {
	return &Server{
		cfg:      cfg,
		pool:     pool,
		log:      log,
		oidc:     newOIDCClient(cfg),
		now:      time.Now,
		consoles: newConsoleStore(),
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
		{"GET", "/v1/key-pairs", "DescribeKeyPairs", anyCredential, (*Server).describeKeyPairs},
		{"POST", "/v1/key-pairs", "ImportKeyPair", anyCredential, (*Server).importKeyPair},
		{"DELETE", "/v1/key-pairs/{key_name}", "DeleteKeyPair", anyCredential, (*Server).deleteKeyPair},
		{"GET", "/v1/images", "DescribeImages", anyCredential, (*Server).describeImages},
		{"POST", "/v1/images", "ImportImage", anyCredential, (*Server).importImage},
		{"DELETE", "/v1/images/{image_id}", "DeleteImage", anyCredential, (*Server).deleteImage},
		{"GET", "/v1/instance-types", "DescribeInstanceTypes", anyCredential, (*Server).describeInstanceTypes},
		{"GET", "/v1/capacity", "DescribeCapacity", anyCredential, (*Server).describeCapacity},
		{"GET", "/v1/limits", "DescribeLimits", anyCredential, (*Server).describeLimits},
		{"PUT", "/v1/limits", "UpdateLimits", anyCredential, (*Server).updateLimits},
		{"POST", "/v1/instances", "RunInstances", anyCredential, (*Server).runInstances},
		{"POST", "/v1/instances/adopt", "AdoptInstance", anyCredential, (*Server).adoptInstance},
		{"GET", "/v1/instances", "DescribeInstances", anyCredential, (*Server).describeInstances},
		{"GET", "/v1/instances/{instance_id}", "DescribeInstance", anyCredential, (*Server).describeInstance},
		{"PATCH", "/v1/instances/{instance_id}", "ModifyInstance", anyCredential, (*Server).modifyInstance},
		{"DELETE", "/v1/instances/{instance_id}", "TerminateInstance", anyCredential, instanceAction(db.ActionTerminate)},
		{"POST", "/v1/instances/{instance_id}/start", "StartInstance", anyCredential, instanceAction(db.ActionStart)},
		{"POST", "/v1/instances/{instance_id}/stop", "StopInstance", anyCredential, instanceAction(db.ActionStop)},
		{"POST", "/v1/instances/{instance_id}/reboot", "RebootInstance", anyCredential, instanceAction(db.ActionReboot)},
		{"POST", "/v1/instances/{instance_id}/console", "CreateConsoleSession", anyCredential, (*Server).createConsoleSession},
		{"PUT", "/v1/instances/{instance_id}/security-groups", "ModifyInstanceSecurityGroups", anyCredential, (*Server).modifyInstanceSecurityGroups},
		{"GET", "/v1/volumes", "DescribeVolumes", anyCredential, (*Server).describeVolumes},
		{"POST", "/v1/volumes", "CreateVolume", anyCredential, (*Server).createVolume},
		{"GET", "/v1/volumes/{volume_id}", "DescribeVolume", anyCredential, (*Server).describeVolume},
		{"PATCH", "/v1/volumes/{volume_id}", "ModifyVolume", anyCredential, (*Server).modifyVolume},
		{"DELETE", "/v1/volumes/{volume_id}", "DeleteVolume", anyCredential, (*Server).deleteVolume},
		{"POST", "/v1/volumes/{volume_id}/attach", "AttachVolume", anyCredential, (*Server).attachVolume},
		{"POST", "/v1/volumes/{volume_id}/detach", "DetachVolume", anyCredential, (*Server).detachVolume},
		{"GET", "/v1/security-groups", "DescribeSecurityGroups", anyCredential, (*Server).describeSecurityGroups},
		{"POST", "/v1/security-groups", "CreateSecurityGroup", anyCredential, (*Server).createSecurityGroup},
		{"GET", "/v1/security-groups/{group_id}", "DescribeSecurityGroup", anyCredential, (*Server).describeSecurityGroup},
		{"DELETE", "/v1/security-groups/{group_id}", "DeleteSecurityGroup", anyCredential, (*Server).deleteSecurityGroup},
		{"POST", "/v1/security-groups/{group_id}/ingress", "AuthorizeSecurityGroupIngress", anyCredential, authorizeRules(db.DirectionIngress)},
		{"POST", "/v1/security-groups/{group_id}/egress", "AuthorizeSecurityGroupEgress", anyCredential, authorizeRules(db.DirectionEgress)},
		{"DELETE", "/v1/security-groups/{group_id}/rules/{rule_id}", "RevokeSecurityGroupRule", anyCredential, (*Server).revokeSecurityGroupRule},
		{"GET", "/v1/buckets", "DescribeBuckets", anyCredential, (*Server).describeBuckets},
		{"POST", "/v1/buckets", "CreateBucket", anyCredential, (*Server).createBucket},
		{"GET", "/v1/buckets/{bucket_name}", "DescribeBucket", anyCredential, (*Server).describeBucket},
		{"DELETE", "/v1/buckets/{bucket_name}", "DeleteBucket", anyCredential, (*Server).deleteBucket},
		{"PUT", "/v1/buckets/{bucket_name}/keys/{key_id}", "PutBucketKey", anyCredential, (*Server).setBucketPermission},
		{"DELETE", "/v1/buckets/{bucket_name}/keys/{key_id}", "DeleteBucketKey", anyCredential, (*Server).revokeBucketPermission},
		{"GET", "/v1/s3-keys", "ListS3Keys", anyCredential, (*Server).listS3Keys},
		{"POST", "/v1/s3-keys", "CreateS3Key", anyCredential, (*Server).createS3Key},
		{"DELETE", "/v1/s3-keys/{key_id}", "DeleteS3Key", anyCredential, (*Server).deleteS3Key},
	}
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	for _, rt := range routes() {
		mux.Handle(rt.method+" "+rt.pattern, s.endpoint(rt))
	}
	mux.HandleFunc("GET /{$}", s.portal)
	// Browser endpoints of a console, like the portal page: not API operations.
	mux.HandleFunc("GET /console/{token}", s.consolePage)
	mux.HandleFunc("GET /console/{token}/ws", s.consoleSocket)
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
