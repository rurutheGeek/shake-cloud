package server

import (
	"errors"
	"net/http"
	"strings"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/accesskey"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

type authFailure struct {
	status  int
	code    string
	message string
}

// One message for every kind of bad credential, so a caller cannot tell a
// wrong secret from a deleted key. The audit log records the real reason.
var errAuthFailure = &authFailure{http.StatusUnauthorized, "AuthFailure", "missing or invalid credentials"}

// authenticate accepts an access key in the Authorization header or, failing
// that, a portal session cookie. A request that sends a bad Authorization
// header is refused even if it also carries a valid cookie.
func (s *Server) authenticate(r *http.Request, c *call) (*principal, *authFailure) {
	ctx := r.Context()
	if header := r.Header.Get("Authorization"); header != "" {
		scheme, value, _ := strings.Cut(header, " ")
		if !strings.EqualFold(scheme, "Bearer") {
			return nil, errAuthFailure
		}
		token, err := accesskey.Parse(strings.TrimSpace(value))
		if err != nil {
			return nil, errAuthFailure
		}
		credential, err := db.LookupAccessKey(ctx, s.pool, token.ID)
		if errors.Is(err, db.ErrNotFound) {
			// Not audited: anyone can invent IDs, and each would cost a row.
			s.log.Warn("unknown access key", "access_key_id", token.ID, "source_ip", c.sourceIP, "request_id", c.requestID)
			return nil, errAuthFailure
		}
		if err != nil {
			s.log.Error("access key lookup failed", "err", err, "request_id", c.requestID)
			return nil, &authFailure{http.StatusInternalServerError, "InternalError", "internal error"}
		}
		p := &principal{account: credential.Account, credentialType: db.CredentialAccessKey, accessKeyID: token.ID, accessKeyScope: credential.Key.Scope}
		reason := ""
		if !token.Matches(credential.SecretSHA256) {
			reason = "secret_mismatch"
		} else if status := credential.Key.Status(s.now()); status != db.KeyActive {
			reason = strings.ToLower(status)
		}
		if reason != "" {
			c.principal = p
			s.recordDenied(ctx, c.event("AuthFailure", map[string]any{"reason": reason}))
			c.principal = nil
			return nil, errAuthFailure
		}
		if err := db.TouchAccessKey(ctx, s.pool, token.ID); err != nil {
			s.log.Warn("recording key use failed", "err", err, "request_id", c.requestID)
		}
		return p, nil
	}

	account, err := s.sessionAccount(r)
	switch {
	case err == nil:
		return &principal{account: account, credentialType: db.CredentialSession}, nil
	case errors.Is(err, db.ErrNotFound):
		return nil, errAuthFailure
	default:
		s.log.Error("session lookup failed", "err", err, "request_id", c.requestID)
		return nil, &authFailure{http.StatusInternalServerError, "InternalError", "internal error"}
	}
}

// sessionAccount returns db.ErrNotFound when there is no live session.
func (s *Server) sessionAccount(r *http.Request) (db.Account, error) {
	cookie, err := r.Cookie(sessionCookie)
	if err != nil || cookie.Value == "" {
		return db.Account{}, db.ErrNotFound
	}
	return db.LookupSession(r.Context(), s.pool, hashToken(cookie.Value))
}
