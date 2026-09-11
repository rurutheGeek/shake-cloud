package server

import (
	"context"
	"crypto/subtle"
	"errors"
	"net/http"
	"regexp"
	"slices"
	"sync"
	"time"

	"github.com/coreos/go-oidc/v3/oidc"
	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/config"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"golang.org/x/oauth2"
)

const (
	sessionCookie = "shakecloud_session"
	loginCookie   = "shakecloud_login"
	loginTTL      = 10 * time.Minute
)

type oidcClient struct {
	cfg        config.Config
	httpClient *http.Client

	mu       sync.Mutex
	provider *oidc.Provider
}

func newOIDCClient(cfg config.Config) *oidcClient {
	return &oidcClient{cfg: cfg, httpClient: &http.Client{Timeout: 10 * time.Second}}
}

// get discovers Authentik on first use and retries on later calls until it
// works. Discovery is deliberately not done at startup: access keys must keep
// working while Authentik is down, so its absence cannot stop the API booting.
func (o *oidcClient) get(ctx context.Context) (*oidc.Provider, *oauth2.Config, error) {
	o.mu.Lock()
	defer o.mu.Unlock()
	if o.provider == nil {
		provider, err := oidc.NewProvider(oidc.ClientContext(ctx, o.httpClient), o.cfg.OIDCIssuer)
		if err != nil {
			return nil, nil, err
		}
		o.provider = provider
	}
	return o.provider, &oauth2.Config{
		ClientID:     o.cfg.OIDCClientID,
		ClientSecret: o.cfg.OIDCClientSecret,
		Endpoint:     o.provider.Endpoint(),
		RedirectURL:  o.cfg.RedirectURL(),
		// profile carries the groups claim (stacks/identity/configure.py).
		Scopes: []string{oidc.ScopeOpenID, "email", "profile"},
	}, nil
}

func (s *Server) startLogin(w http.ResponseWriter, r *http.Request, c *call) {
	ctx := r.Context()
	_, oauth, err := s.oidc.get(ctx)
	if err != nil {
		s.log.Warn("OIDC discovery failed", "err", err, "request_id", c.requestID)
		loginPage(w, http.StatusServiceUnavailable, "Authentik に接続できません。アクセスキーによる API 操作には影響しません。")
		return
	}
	state, nonce, verifier := randomToken(), randomToken(), oauth2.GenerateVerifier()
	if err := db.CreateLoginAttempt(ctx, s.pool, hashToken(state), nonce, verifier, s.now().Add(loginTTL)); err != nil {
		s.internalError(w, r, err)
		return
	}
	// Binding the state to this browser stops login CSRF: a callback URL
	// started by someone else does not carry a matching cookie.
	http.SetCookie(w, &http.Cookie{
		Name: loginCookie, Value: state, Path: "/auth/", MaxAge: int(loginTTL.Seconds()),
		HttpOnly: true, Secure: s.cfg.SecureCookies(), SameSite: http.SameSiteLaxMode,
	})
	http.Redirect(w, r, oauth.AuthCodeURL(state, oidc.Nonce(nonce), oauth2.S256ChallengeOption(verifier)), http.StatusFound)
}

var oauthErrorCode = regexp.MustCompile(`^[a-z_]{1,64}$`)

// loginClaims are the Authentik claims the API uses. groups comes from the
// profile scope mapping.
type loginClaims struct {
	Email             string   `json:"email"`
	PreferredUsername string   `json:"preferred_username"`
	Groups            []string `json:"groups"`
}

func (s *Server) completeLogin(w http.ResponseWriter, r *http.Request, c *call) {
	ctx := r.Context()
	query := r.URL.Query()
	http.SetCookie(w, &http.Cookie{Name: loginCookie, Path: "/auth/", MaxAge: -1, HttpOnly: true,
		Secure: s.cfg.SecureCookies(), SameSite: http.SameSiteLaxMode})

	if code := query.Get("error"); code != "" {
		if !oauthErrorCode.MatchString(code) {
			code = "invalid"
		}
		loginPage(w, http.StatusForbidden, "Authentik がログインを完了しませんでした（"+code+"）。")
		return
	}
	state := query.Get("state")
	cookie, err := r.Cookie(loginCookie)
	if err != nil || state == "" || subtle.ConstantTimeCompare([]byte(cookie.Value), []byte(state)) != 1 {
		loginPage(w, http.StatusBadRequest, "ログインの途中情報がこのブラウザと一致しません。最初からやり直してください。")
		return
	}
	nonce, verifier, err := db.TakeLoginAttempt(ctx, s.pool, hashToken(state))
	if errors.Is(err, db.ErrNotFound) {
		loginPage(w, http.StatusBadRequest, "ログインの有効期限が切れたか、既に使われています。最初からやり直してください。")
		return
	}
	if err != nil {
		s.internalError(w, r, err)
		return
	}

	provider, oauth, err := s.oidc.get(ctx)
	if err != nil {
		s.log.Warn("OIDC discovery failed", "err", err, "request_id", c.requestID)
		loginPage(w, http.StatusServiceUnavailable, "Authentik に接続できません。")
		return
	}
	token, err := oauth.Exchange(oidc.ClientContext(ctx, s.oidc.httpClient), query.Get("code"), oauth2.VerifierOption(verifier))
	if err != nil {
		s.log.Warn("OIDC code exchange failed", "err", err, "request_id", c.requestID)
		loginPage(w, http.StatusBadGateway, "Authentik からトークンを受け取れませんでした。最初からやり直してください。")
		return
	}
	rawIDToken, _ := token.Extra("id_token").(string)
	idToken, err := provider.VerifierContext(oidc.ClientContext(ctx, s.oidc.httpClient),
		&oidc.Config{ClientID: s.cfg.OIDCClientID}).Verify(ctx, rawIDToken)
	if err != nil || subtle.ConstantTimeCompare([]byte(idToken.Nonce), []byte(nonce)) != 1 {
		s.log.Warn("ID token rejected", "err", err, "request_id", c.requestID)
		loginPage(w, http.StatusBadGateway, "Authentik から受け取ったトークンを検証できませんでした。")
		return
	}
	var claims loginClaims
	if err := idToken.Claims(&claims); err != nil {
		s.log.Warn("ID token claims unreadable", "err", err, "request_id", c.requestID)
		loginPage(w, http.StatusBadGateway, "Authentik から受け取ったトークンを読めませんでした。")
		return
	}
	username := claims.PreferredUsername
	if username == "" {
		username = idToken.Subject
	}
	who := map[string]any{"subject": idToken.Subject, "username": username, "email": claims.Email}

	// Authentik already limits the application to these groups. Checking again
	// means a policy binding removed by mistake does not open the cloud to
	// everyone with an Authentik account.
	isAdmin := slices.Contains(claims.Groups, s.cfg.AdminGroup)
	if !isAdmin && !slices.Contains(claims.Groups, s.cfg.UserGroup) {
		s.recordDenied(ctx, c.event("AccessDenied", who))
		loginPage(w, http.StatusForbidden, "このアカウントはクラウドの利用者グループに入っていません。管理者に依頼してください。")
		return
	}

	account, created, err := db.RecordLogin(ctx, s.pool, idToken.Subject, username, claims.Email, isAdmin)
	if errors.Is(err, db.ErrEmailConflict) {
		s.log.Warn("login refused: known email with a new subject", "subject", idToken.Subject, "request_id", c.requestID)
		s.recordDenied(ctx, c.event("AccountConflict", who))
		loginPage(w, http.StatusForbidden,
			"このメールアドレスは別のアカウントに登録されています。Authentik のユーザーを作り直した可能性があるので、管理者に連絡してください。")
		return
	}
	if err != nil {
		s.internalError(w, r, err)
		return
	}

	sessionToken := randomToken()
	c.principal = &principal{account: account, credentialType: db.CredentialSession}
	err = pgx.BeginFunc(ctx, s.pool, func(tx pgx.Tx) error {
		if err := db.CreateSession(ctx, tx, account.ID, hashToken(sessionToken), s.now().Add(s.cfg.SessionTTL)); err != nil {
			return err
		}
		who["account_created"], who["is_admin"] = created, isAdmin
		return db.RecordAudit(ctx, tx, c.event("", who))
	})
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	http.SetCookie(w, &http.Cookie{
		Name: sessionCookie, Value: sessionToken, Path: "/", MaxAge: int(s.cfg.SessionTTL.Seconds()),
		HttpOnly: true, Secure: s.cfg.SecureCookies(), SameSite: http.SameSiteLaxMode,
	})
	http.Redirect(w, r, "/", http.StatusFound)
}

func (s *Server) logout(w http.ResponseWriter, r *http.Request, c *call) {
	ctx := r.Context()
	if cookie, err := r.Cookie(sessionCookie); err == nil && cookie.Value != "" {
		account, err := db.LookupSession(ctx, s.pool, hashToken(cookie.Value))
		if err == nil {
			c.principal = &principal{account: account, credentialType: db.CredentialSession}
			err = pgx.BeginFunc(ctx, s.pool, func(tx pgx.Tx) error {
				if err := db.DeleteSession(ctx, tx, hashToken(cookie.Value)); err != nil {
					return err
				}
				return db.RecordAudit(ctx, tx, c.event("", nil))
			})
		}
		if err != nil && !errors.Is(err, db.ErrNotFound) {
			s.internalError(w, r, err)
			return
		}
	}
	http.SetCookie(w, &http.Cookie{Name: sessionCookie, Path: "/", MaxAge: -1, HttpOnly: true,
		Secure: s.cfg.SecureCookies(), SameSite: http.SameSiteLaxMode})
	w.WriteHeader(http.StatusNoContent)
}
