package server

// These tests need PostgreSQL. Point SHAKECLOUD_TEST_DATABASE_URL at a server
// where the user may create databases; each test gets its own and drops it.
// Without the variable they are skipped, so `go test ./...` still runs offline.

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/go-jose/go-jose/v4"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/accesskey"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/config"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

func testServer(t *testing.T, adjust func(*config.Config)) *Server {
	t.Helper()
	dsn := os.Getenv("SHAKECLOUD_TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("SHAKECLOUD_TEST_DATABASE_URL is not set")
	}
	ctx := context.Background()
	admin, err := pgx.Connect(ctx, dsn)
	if err != nil {
		t.Fatal(err)
	}
	name := "shakecloud_test_" + randomHex(6)
	if _, err := admin.Exec(ctx, "CREATE DATABASE "+name); err != nil {
		t.Fatal(err)
	}
	poolConfig, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		t.Fatal(err)
	}
	poolConfig.ConnConfig.Database = name
	pool, err := pgxpool.NewWithConfig(ctx, poolConfig)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		pool.Close()
		_, _ = admin.Exec(ctx, "DROP DATABASE "+name+" WITH (FORCE)")
		_ = admin.Close(ctx)
	})
	if _, err := db.Migrate(ctx, pool); err != nil {
		t.Fatal(err)
	}

	public, _ := url.Parse("http://portal.test")
	cfg := config.Config{
		PublicURL: public, UserGroup: "cloud-users", AdminGroup: "cloud-admins", SessionTTL: time.Hour,
		OIDCIssuer: "http://127.0.0.1:1/unreachable/", OIDCClientID: "cloud", OIDCClientSecret: "client-secret",
	}
	if adjust != nil {
		adjust(&cfg)
	}
	return New(cfg, pool, slog.New(slog.DiscardHandler))
}

type req struct {
	method, path string
	body         any
	cookies      []*http.Cookie
	bearer       string
	headers      map[string]string
}

func do(t *testing.T, s *Server, r req) *httptest.ResponseRecorder {
	t.Helper()
	var body io.Reader
	if r.body != nil {
		raw, err := json.Marshal(r.body)
		if err != nil {
			t.Fatal(err)
		}
		body = bytes.NewReader(raw)
	}
	request := httptest.NewRequest(r.method, r.path, body)
	if r.body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	for _, cookie := range r.cookies {
		request.AddCookie(cookie)
	}
	if r.bearer != "" {
		request.Header.Set("Authorization", "Bearer "+r.bearer)
	}
	for name, value := range r.headers {
		request.Header.Set(name, value)
	}
	recorder := httptest.NewRecorder()
	s.Handler().ServeHTTP(recorder, request)
	return recorder
}

func decode[T any](t *testing.T, recorder *httptest.ResponseRecorder) T {
	t.Helper()
	var value T
	if err := json.Unmarshal(recorder.Body.Bytes(), &value); err != nil {
		t.Fatalf("decode %q: %v", recorder.Body.String(), err)
	}
	return value
}

func expectStatus(t *testing.T, recorder *httptest.ResponseRecorder, status int) {
	t.Helper()
	if recorder.Code != status {
		t.Fatalf("status %d, want %d: %s", recorder.Code, status, recorder.Body.String())
	}
}

// session logs a user in without Authentik, for tests about what comes after.
func session(t *testing.T, s *Server, username string, admin bool) (db.Account, *http.Cookie) {
	t.Helper()
	ctx := context.Background()
	account, _, err := db.RecordLogin(ctx, s.pool, "sub-"+username, username, username+"@example.test", admin)
	if err != nil {
		t.Fatal(err)
	}
	token := randomToken()
	if err := db.CreateSession(ctx, s.pool, account.ID, hashToken(token), time.Now().Add(time.Hour)); err != nil {
		t.Fatal(err)
	}
	return account, &http.Cookie{Name: sessionCookie, Value: token}
}

type createdKey struct {
	AccessKey struct {
		AccessKeyID string `json:"access_key_id"`
		Status      string `json:"status"`
	} `json:"access_key"`
	Secret string `json:"secret_access_key"`
}

func createKey(t *testing.T, s *Server, cookie *http.Cookie) createdKey {
	t.Helper()
	recorder := do(t, s, req{method: "POST", path: "/v1/access-keys", body: map[string]any{"description": "test"}, cookies: []*http.Cookie{cookie}})
	expectStatus(t, recorder, http.StatusCreated)
	return decode[createdKey](t, recorder)
}

type eventList struct {
	Events []struct {
		EventName   string         `json:"event_name"`
		AccountID   string         `json:"account_id"`
		AccessKeyID string         `json:"access_key_id"`
		ResourceID  string         `json:"resource_id"`
		ErrorCode   string         `json:"error_code"`
		Detail      map[string]any `json:"detail"`
	} `json:"events"`
	NextToken string `json:"next_token"`
}

func events(t *testing.T, s *Server, auth req) eventList {
	t.Helper()
	auth.method = "GET"
	if auth.path == "" {
		auth.path = "/v1/audit-events"
	}
	recorder := do(t, s, auth)
	expectStatus(t, recorder, http.StatusOK)
	return decode[eventList](t, recorder)
}

func TestHealthDoesNotNeedCredentials(t *testing.T) {
	s := testServer(t, nil)
	expectStatus(t, do(t, s, req{method: "GET", path: "/healthz"}), http.StatusOK)
}

func TestMigrationsApplyOnce(t *testing.T) {
	s := testServer(t, nil)
	applied, err := db.Migrate(context.Background(), s.pool)
	if err != nil || len(applied) != 0 {
		t.Fatalf("second Migrate applied %v, err %v", applied, err)
	}
}

func TestAccessKeyLifecycle(t *testing.T) {
	s := testServer(t, nil)
	_, cookie := session(t, s, "alice", false)
	key := createKey(t, s, cookie)
	if !strings.HasPrefix(key.Secret, "sca_"+key.AccessKey.AccessKeyID+".") || key.AccessKey.Status != "Active" {
		t.Fatalf("unexpected key: %+v", key)
	}

	identity := decode[callerIdentity](t, do(t, s, req{method: "GET", path: "/v1/caller-identity", bearer: key.Secret}))
	if identity.Username != "alice" || identity.CredentialType != "access_key" || identity.AccessKeyID != key.AccessKey.AccessKeyID {
		t.Fatalf("caller identity: %+v", identity)
	}

	listed := do(t, s, req{method: "GET", path: "/v1/access-keys", bearer: key.Secret})
	expectStatus(t, listed, http.StatusOK)
	if strings.Contains(listed.Body.String(), strings.SplitN(key.Secret, ".", 2)[1]) {
		t.Fatal("listing leaked the secret")
	}

	expectStatus(t, do(t, s, req{method: "DELETE", path: "/v1/access-keys/" + key.AccessKey.AccessKeyID, cookies: []*http.Cookie{cookie}}), http.StatusNoContent)
	expectStatus(t, do(t, s, req{method: "GET", path: "/v1/caller-identity", bearer: key.Secret}), http.StatusUnauthorized)
	expectStatus(t, do(t, s, req{method: "DELETE", path: "/v1/access-keys/" + key.AccessKey.AccessKeyID, cookies: []*http.Cookie{cookie}}), http.StatusNotFound)

	got := events(t, s, req{cookies: []*http.Cookie{cookie}})
	names := []string{}
	for _, e := range got.Events {
		names = append(names, e.EventName+"/"+e.ErrorCode)
	}
	want := []string{"GetCallerIdentity/AuthFailure", "DeleteAccessKey/", "CreateAccessKey/"}
	if strings.Join(names, ",") != strings.Join(want, ",") {
		t.Fatalf("audit events %v, want %v", names, want)
	}
	if got.Events[0].Detail["reason"] != "inactive" || got.Events[0].AccessKeyID != key.AccessKey.AccessKeyID {
		t.Fatalf("failure not attributed: %+v", got.Events[0])
	}
}

func TestWrongSecretIsAuditedButUnknownKeyIsNot(t *testing.T) {
	s := testServer(t, nil)
	_, cookie := session(t, s, "alice", false)
	key := createKey(t, s, cookie)
	wrong := "sca_" + key.AccessKey.AccessKeyID + "." + accesskey.New().Secret
	unknown := accesskey.New().String()
	for _, bearer := range []string{wrong, unknown, "not-a-key"} {
		recorder := do(t, s, req{method: "GET", path: "/v1/access-keys", bearer: bearer, cookies: []*http.Cookie{cookie}})
		// A bad Authorization header is refused even alongside a valid session.
		expectStatus(t, recorder, http.StatusUnauthorized)
		if !strings.Contains(recorder.Body.String(), "missing or invalid credentials") {
			t.Fatalf("failure message differs by cause: %s", recorder.Body.String())
		}
	}
	failures := 0
	for _, e := range events(t, s, req{cookies: []*http.Cookie{cookie}}).Events {
		if e.ErrorCode == "AuthFailure" {
			failures++
			if e.Detail["reason"] != "secret_mismatch" {
				t.Errorf("reason %v", e.Detail["reason"])
			}
		}
	}
	if failures != 1 {
		t.Fatalf("%d AuthFailure events, want 1", failures)
	}
}

func TestExpiredKeysStopWorking(t *testing.T) {
	s := testServer(t, nil)
	_, cookie := session(t, s, "alice", false)
	recorder := do(t, s, req{method: "POST", path: "/v1/access-keys", body: map[string]any{"expires_in_days": 1}, cookies: []*http.Cookie{cookie}})
	expectStatus(t, recorder, http.StatusCreated)
	key := decode[createdKey](t, recorder)
	expectStatus(t, do(t, s, req{method: "GET", path: "/v1/caller-identity", bearer: key.Secret}), http.StatusOK)
	s.now = func() time.Time { return time.Now().Add(25 * time.Hour) }
	expectStatus(t, do(t, s, req{method: "GET", path: "/v1/caller-identity", bearer: key.Secret}), http.StatusUnauthorized)
}

func TestAccessKeysCannotCreateAccessKeys(t *testing.T) {
	s := testServer(t, nil)
	_, cookie := session(t, s, "alice", false)
	key := createKey(t, s, cookie)
	recorder := do(t, s, req{method: "POST", path: "/v1/access-keys", body: map[string]any{}, bearer: key.Secret})
	expectStatus(t, recorder, http.StatusForbidden)
	if decode[errorBody](t, recorder).Error.Code != "UnauthorizedOperation" {
		t.Fatal(recorder.Body.String())
	}
}

func TestCrossSiteRequestsCannotUseTheSession(t *testing.T) {
	s := testServer(t, nil)
	_, cookie := session(t, s, "alice", false)
	cross := do(t, s, req{method: "POST", path: "/v1/access-keys", body: map[string]any{}, cookies: []*http.Cookie{cookie},
		headers: map[string]string{"Sec-Fetch-Site": "cross-site"}})
	expectStatus(t, cross, http.StatusForbidden)
	same := do(t, s, req{method: "POST", path: "/v1/access-keys", body: map[string]any{}, cookies: []*http.Cookie{cookie},
		headers: map[string]string{"Sec-Fetch-Site": "same-origin"}})
	expectStatus(t, same, http.StatusCreated)
}

func TestRequestBodiesMustBeStrictJSON(t *testing.T) {
	s := testServer(t, nil)
	_, cookie := session(t, s, "alice", false)
	expectStatus(t, do(t, s, req{method: "POST", path: "/v1/access-keys", body: map[string]any{"descripton": "typo"}, cookies: []*http.Cookie{cookie}}), http.StatusBadRequest)
	expectStatus(t, do(t, s, req{method: "POST", path: "/v1/access-keys", body: map[string]any{"expires_in_days": 0}, cookies: []*http.Cookie{cookie}}), http.StatusBadRequest)
	expectStatus(t, do(t, s, req{method: "POST", path: "/v1/access-keys", cookies: []*http.Cookie{cookie}}), http.StatusUnsupportedMediaType)
}

func TestActiveKeyLimit(t *testing.T) {
	s := testServer(t, nil)
	_, cookie := session(t, s, "alice", false)
	var last createdKey
	for range maxActiveAccessKeys {
		last = createKey(t, s, cookie)
	}
	expectStatus(t, do(t, s, req{method: "POST", path: "/v1/access-keys", body: map[string]any{}, cookies: []*http.Cookie{cookie}}), http.StatusConflict)
	expectStatus(t, do(t, s, req{method: "DELETE", path: "/v1/access-keys/" + last.AccessKey.AccessKeyID, cookies: []*http.Cookie{cookie}}), http.StatusNoContent)
	createKey(t, s, cookie)
}

func TestAccountsAreIsolatedAndAdminsAreNot(t *testing.T) {
	s := testServer(t, nil)
	alice, aliceCookie := session(t, s, "alice", false)
	_, bobCookie := session(t, s, "bob", false)
	_, adminCookie := session(t, s, "root", true)
	aliceKey := createKey(t, s, aliceCookie)
	bobKey := createKey(t, s, bobCookie)

	// Bob cannot tell Alice's key from a key that does not exist.
	recorder := do(t, s, req{method: "DELETE", path: "/v1/access-keys/" + aliceKey.AccessKey.AccessKeyID, bearer: bobKey.Secret})
	expectStatus(t, recorder, http.StatusNotFound)
	if strings.Contains(do(t, s, req{method: "GET", path: "/v1/access-keys", bearer: bobKey.Secret}).Body.String(), aliceKey.AccessKey.AccessKeyID) {
		t.Fatal("Bob sees Alice's key")
	}
	expectStatus(t, do(t, s, req{method: "GET", path: "/v1/audit-events?account_id=" + alice.ID, bearer: bobKey.Secret}), http.StatusForbidden)
	for _, e := range events(t, s, req{bearer: bobKey.Secret}).Events {
		if e.AccountID != "" && e.AccountID == alice.ID {
			t.Fatalf("Bob sees Alice's event %+v", e)
		}
	}

	// An administrator may revoke anyone's key, and sees every account's events.
	expectStatus(t, do(t, s, req{method: "DELETE", path: "/v1/access-keys/" + aliceKey.AccessKey.AccessKeyID, cookies: []*http.Cookie{adminCookie}}), http.StatusNoContent)
	expectStatus(t, do(t, s, req{method: "GET", path: "/v1/caller-identity", bearer: aliceKey.Secret}), http.StatusUnauthorized)
	accounts := map[string]bool{}
	for _, e := range events(t, s, req{cookies: []*http.Cookie{adminCookie}}).Events {
		accounts[e.AccountID] = true
	}
	if !accounts[alice.ID] || len(accounts) < 3 {
		t.Fatalf("admin sees events of %v", accounts)
	}
	denied := events(t, s, req{path: "/v1/audit-events?event_name=DeleteAccessKey", cookies: []*http.Cookie{adminCookie}})
	if len(denied.Events) != 2 || denied.Events[1].ErrorCode != "AccessDenied" {
		t.Fatalf("Bob's attempt was not recorded: %+v", denied.Events)
	}
}

func TestAuditPaging(t *testing.T) {
	s := testServer(t, nil)
	_, cookie := session(t, s, "alice", false)
	for range 3 {
		key := createKey(t, s, cookie)
		expectStatus(t, do(t, s, req{method: "DELETE", path: "/v1/access-keys/" + key.AccessKey.AccessKeyID, cookies: []*http.Cookie{cookie}}), http.StatusNoContent)
	}
	first := events(t, s, req{path: "/v1/audit-events?max_results=4", cookies: []*http.Cookie{cookie}})
	if len(first.Events) != 4 || first.NextToken == "" {
		t.Fatalf("first page: %+v", first)
	}
	second := events(t, s, req{path: "/v1/audit-events?max_results=4&next_token=" + first.NextToken, cookies: []*http.Cookie{cookie}})
	if len(second.Events) != 2 || second.NextToken != "" {
		t.Fatalf("second page: %+v", second)
	}
}

func TestAuditEventsAreAppendOnly(t *testing.T) {
	s := testServer(t, nil)
	_, cookie := session(t, s, "alice", false)
	createKey(t, s, cookie)
	ctx := context.Background()
	for _, statement := range []string{"UPDATE audit_events SET error_code = 'x'", "DELETE FROM audit_events", "TRUNCATE audit_events"} {
		if _, err := s.pool.Exec(ctx, statement); err == nil || !strings.Contains(err.Error(), "append-only") {
			t.Errorf("%s: %v", statement, err)
		}
	}
}

func TestBootstrapKeyFollowsTheFile(t *testing.T) {
	first := accesskey.New()
	s := testServer(t, func(cfg *config.Config) { cfg.BootstrapKey = &first })
	ctx := context.Background()
	reconcile := func(token *accesskey.Token) error {
		s.cfg.BootstrapKey = token
		return s.ReconcileBootstrapKey(ctx)
	}
	works := func(token accesskey.Token) bool {
		return do(t, s, req{method: "GET", path: "/v1/caller-identity", bearer: token.String()}).Code == http.StatusOK
	}

	if err := reconcile(&first); err != nil {
		t.Fatal(err)
	}
	if err := reconcile(&first); err != nil {
		t.Fatalf("restart with the same file: %v", err)
	}
	identity := decode[callerIdentity](t, do(t, s, req{method: "GET", path: "/v1/caller-identity", bearer: first.String()}))
	if !identity.IsAdmin || identity.Username != "bootstrap-admin" {
		t.Fatalf("bootstrap identity: %+v", identity)
	}

	second := accesskey.New()
	if err := reconcile(&second); err != nil {
		t.Fatal(err)
	}
	if works(first) || !works(second) {
		t.Fatal("rotating the file did not replace the key")
	}

	tampered := second
	tampered.Secret = accesskey.New().Secret
	if err := reconcile(&tampered); err == nil {
		t.Fatal("a file with a known ID and a different secret was accepted")
	}

	// Deleted through the API: a restart must not bring it back.
	expectStatus(t, do(t, s, req{method: "DELETE", path: "/v1/access-keys/" + second.ID, bearer: second.String()}), http.StatusNoContent)
	if err := reconcile(&second); err != nil || works(second) {
		t.Fatalf("revoked bootstrap key came back (err %v)", err)
	}

	third := accesskey.New()
	if err := reconcile(&third); err != nil || !works(third) {
		t.Fatal(err)
	}
	if err := reconcile(nil); err != nil || works(third) {
		t.Fatalf("an empty file did not disable the key (err %v)", err)
	}
}

func TestAPIKeepsWorkingWhileAuthentikIsDown(t *testing.T) {
	// The default test issuer points at a closed port.
	s := testServer(t, nil)
	_, cookie := session(t, s, "alice", false)
	key := createKey(t, s, cookie)
	expectStatus(t, do(t, s, req{method: "GET", path: "/v1/caller-identity", bearer: key.Secret}), http.StatusOK)
	expectStatus(t, do(t, s, req{method: "GET", path: "/auth/login"}), http.StatusServiceUnavailable)
}

func TestLogoutEndsTheSession(t *testing.T) {
	s := testServer(t, nil)
	_, cookie := session(t, s, "alice", false)
	expectStatus(t, do(t, s, req{method: "POST", path: "/auth/logout", cookies: []*http.Cookie{cookie}}), http.StatusNoContent)
	expectStatus(t, do(t, s, req{method: "GET", path: "/v1/access-keys", cookies: []*http.Cookie{cookie}}), http.StatusUnauthorized)
}

// fakeAuthentik is just enough of an OIDC provider to run the real login code:
// discovery, keys, and a token endpoint that checks the code and PKCE verifier.
type fakeAuthentik struct {
	server    *httptest.Server
	key       *rsa.PrivateKey
	code      string
	challenge string
	nonce     string
	claims    map[string]any
}

func newFakeAuthentik(t *testing.T) *fakeAuthentik {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	idp := &fakeAuthentik{key: key}
	mux := http.NewServeMux()
	idp.server = httptest.NewServer(mux)
	t.Cleanup(idp.server.Close)
	base := idp.server.URL

	mux.HandleFunc("GET /.well-known/openid-configuration", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{
			"issuer": base, "authorization_endpoint": base + "/authorize", "token_endpoint": base + "/token",
			"jwks_uri": base + "/jwks", "id_token_signing_alg_values_supported": []string{"RS256"},
		})
	})
	mux.HandleFunc("GET /jwks", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, jose.JSONWebKeySet{Keys: []jose.JSONWebKey{{Key: &key.PublicKey, KeyID: "k", Algorithm: "RS256", Use: "sig"}}})
	})
	mux.HandleFunc("POST /token", func(w http.ResponseWriter, r *http.Request) {
		_ = r.ParseForm()
		verifier := sha256.Sum256([]byte(r.PostForm.Get("code_verifier")))
		clientID, clientSecret, basic := r.BasicAuth()
		if !basic {
			clientID, clientSecret = r.PostForm.Get("client_id"), r.PostForm.Get("client_secret")
		}
		if r.PostForm.Get("code") != idp.code || base64.RawURLEncoding.EncodeToString(verifier[:]) != idp.challenge ||
			clientID != "cloud" || clientSecret != "client-secret" {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid_grant"})
			return
		}
		idp.code = "" // single use
		claims := map[string]any{"iss": base, "aud": "cloud", "iat": time.Now().Unix(), "exp": time.Now().Add(time.Minute).Unix(), "nonce": idp.nonce}
		for name, value := range idp.claims {
			claims[name] = value
		}
		signer, err := jose.NewSigner(jose.SigningKey{Algorithm: jose.RS256, Key: key}, (&jose.SignerOptions{}).WithType("JWT").WithHeader("kid", "k"))
		if err != nil {
			t.Error(err)
			return
		}
		payload, _ := json.Marshal(claims)
		signed, err := signer.Sign(payload)
		if err != nil {
			t.Error(err)
			return
		}
		raw, _ := signed.CompactSerialize()
		writeJSON(w, http.StatusOK, map[string]any{"access_token": "at", "token_type": "Bearer", "expires_in": 60, "id_token": raw})
	})
	return idp
}

// login drives the browser side: start, "approve" at Authentik, come back.
func (idp *fakeAuthentik) login(t *testing.T, s *Server, claims map[string]any) *httptest.ResponseRecorder {
	t.Helper()
	start := do(t, s, req{method: "GET", path: "/auth/login"})
	expectStatus(t, start, http.StatusFound)
	location, err := url.Parse(start.Header().Get("Location"))
	if err != nil {
		t.Fatal(err)
	}
	query := location.Query()
	if query.Get("code_challenge_method") != "S256" || query.Get("redirect_uri") != "http://portal.test/auth/callback" {
		t.Fatalf("authorization request: %s", location)
	}
	idp.code, idp.challenge, idp.nonce, idp.claims = randomToken(), query.Get("code_challenge"), query.Get("nonce"), claims
	callback := "/auth/callback?" + url.Values{"code": {idp.code}, "state": {query.Get("state")}}.Encode()
	return do(t, s, req{method: "GET", path: callback, cookies: start.Result().Cookies()})
}

func sessionCookieFrom(recorder *httptest.ResponseRecorder) *http.Cookie {
	for _, cookie := range recorder.Result().Cookies() {
		if cookie.Name == sessionCookie && cookie.Value != "" {
			return cookie
		}
	}
	return nil
}

func withAuthentik(t *testing.T) (*Server, *fakeAuthentik) {
	idp := newFakeAuthentik(t)
	return testServer(t, func(cfg *config.Config) { cfg.OIDCIssuer = idp.server.URL }), idp
}

func TestLoginCreatesTheAccountThenReusesIt(t *testing.T) {
	s, idp := withAuthentik(t)
	claims := map[string]any{"sub": "uuid-1", "preferred_username": "alice", "email": "alice@example.test", "groups": []string{"cloud-users"}}
	recorder := idp.login(t, s, claims)
	expectStatus(t, recorder, http.StatusFound)
	cookie := sessionCookieFrom(recorder)
	if cookie == nil || !cookie.HttpOnly || cookie.SameSite != http.SameSiteLaxMode {
		t.Fatalf("session cookie: %+v", cookie)
	}
	first := decode[callerIdentity](t, do(t, s, req{method: "GET", path: "/v1/caller-identity", cookies: []*http.Cookie{cookie}}))
	if first.Username != "alice" || first.IsAdmin {
		t.Fatalf("identity: %+v", first)
	}

	// Promoted in Authentik: the next login picks it up, same account.
	claims["groups"] = []string{"cloud-users", "cloud-admins"}
	again := sessionCookieFrom(idp.login(t, s, claims))
	second := decode[callerIdentity](t, do(t, s, req{method: "GET", path: "/v1/caller-identity", cookies: []*http.Cookie{again}}))
	if second.AccountID != first.AccountID || !second.IsAdmin {
		t.Fatalf("second login: %+v, first %+v", second, first)
	}
}

func TestLoginRequiresACloudGroup(t *testing.T) {
	s, idp := withAuthentik(t)
	recorder := idp.login(t, s, map[string]any{"sub": "uuid-2", "preferred_username": "media", "groups": []string{"media-users"}})
	expectStatus(t, recorder, http.StatusForbidden)
	if sessionCookieFrom(recorder) != nil {
		t.Fatal("refused login still set a session")
	}
	_, adminCookie := session(t, s, "root", true)
	found := events(t, s, req{path: "/v1/audit-events?event_name=CompleteLogin", cookies: []*http.Cookie{adminCookie}})
	if len(found.Events) != 1 || found.Events[0].ErrorCode != "AccessDenied" {
		t.Fatalf("refusal not audited: %+v", found)
	}
}

func TestLoginRefusesAKnownEmailUnderANewSubject(t *testing.T) {
	s, idp := withAuthentik(t)
	claims := map[string]any{"sub": "uuid-old", "preferred_username": "alice", "email": "Alice@example.test", "groups": []string{"cloud-users"}}
	expectStatus(t, idp.login(t, s, claims), http.StatusFound)
	claims["sub"], claims["email"] = "uuid-new", "alice@example.test"
	expectStatus(t, idp.login(t, s, claims), http.StatusForbidden)
}

func TestCallbackStateIsBoundToTheBrowserAndSingleUse(t *testing.T) {
	s, idp := withAuthentik(t)
	start := do(t, s, req{method: "GET", path: "/auth/login"})
	location, _ := url.Parse(start.Header().Get("Location"))
	query := location.Query()
	idp.code, idp.challenge, idp.nonce = randomToken(), query.Get("code_challenge"), query.Get("nonce")
	idp.claims = map[string]any{"sub": "uuid-3", "groups": []string{"cloud-users"}}
	callback := "/auth/callback?" + url.Values{"code": {idp.code}, "state": {query.Get("state")}}.Encode()

	// Someone else's browser (no login cookie) cannot complete this login.
	expectStatus(t, do(t, s, req{method: "GET", path: callback}), http.StatusBadRequest)
	expectStatus(t, do(t, s, req{method: "GET", path: callback, cookies: start.Result().Cookies()}), http.StatusFound)
	expectStatus(t, do(t, s, req{method: "GET", path: callback, cookies: start.Result().Cookies()}), http.StatusBadRequest)
}

func TestLoginRejectsATokenWithTheWrongNonce(t *testing.T) {
	s, idp := withAuthentik(t)
	start := do(t, s, req{method: "GET", path: "/auth/login"})
	location, _ := url.Parse(start.Header().Get("Location"))
	query := location.Query()
	idp.code, idp.challenge, idp.nonce = randomToken(), query.Get("code_challenge"), "replayed-nonce"
	idp.claims = map[string]any{"sub": "uuid-4", "groups": []string{"cloud-users"}}
	callback := "/auth/callback?" + url.Values{"code": {idp.code}, "state": {query.Get("state")}}.Encode()
	recorder := do(t, s, req{method: "GET", path: callback, cookies: start.Result().Cookies()})
	expectStatus(t, recorder, http.StatusBadGateway)
	if sessionCookieFrom(recorder) != nil {
		t.Fatal("session issued for a token with the wrong nonce")
	}
}

func TestPortalPageRendersForBothStates(t *testing.T) {
	s := testServer(t, nil)
	out := do(t, s, req{method: "GET", path: "/"})
	expectStatus(t, out, http.StatusOK)
	if !strings.Contains(out.Body.String(), `href="/auth/login"`) || !strings.Contains(out.Header().Get("Content-Security-Policy"), "script-src 'self'") {
		t.Fatal("logged-out page")
	}
	account, cookie := session(t, s, "<alice>", false)
	in := do(t, s, req{method: "GET", path: "/", cookies: []*http.Cookie{cookie}})
	if !strings.Contains(in.Body.String(), account.ID) || strings.Contains(in.Body.String(), "<alice>") {
		t.Fatal("logged-in page is missing the account or does not escape the username")
	}
	expectStatus(t, do(t, s, req{method: "GET", path: "/static/portal.js"}), http.StatusOK)
}
