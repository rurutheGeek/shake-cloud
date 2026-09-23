package server

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"mime"
	"net"
	"net/http"
	"net/netip"
	"runtime/debug"
	"strings"
	"time"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

type requestIDKey struct{}

type clientIPKey struct{}

// call carries what a handler needs to know about the request it serves.
type call struct {
	operation string
	requestID string
	sourceIP  string
	userAgent string
	principal *principal
}

type principal struct {
	account        db.Account
	credentialType string
	accessKeyID    string
	accessKeyScope string
}

func newCall(r *http.Request, operation string) *call {
	return &call{
		operation: operation,
		requestID: requestID(r),
		sourceIP:  sourceIP(r),
		userAgent: r.UserAgent(),
	}
}

// event starts an audit record for this request. errorCode is empty on success.
func (c *call) event(errorCode string, detail map[string]any) db.AuditEvent {
	e := db.AuditEvent{
		EventName:       c.operation,
		CredentialType:  db.CredentialNone,
		SourceIPAddress: c.sourceIP,
		UserAgent:       c.userAgent,
		RequestID:       c.requestID,
		ErrorCode:       errorCode,
		Detail:          detail,
	}
	if p := c.principal; p != nil {
		e.AccountID = p.account.ID
		e.CredentialType = p.credentialType
		e.AccessKeyID = p.accessKeyID
	}
	return e
}

// observe assigns a request ID, recovers panics and logs one line per request.
// Only the path is logged: the OIDC callback's query carries the code and state.
func (s *Server) observe(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := randomHex(8)
		ctx := context.WithValue(r.Context(), requestIDKey{}, id)
		r = r.WithContext(context.WithValue(ctx, clientIPKey{}, clientIP(r, s.cfg.TrustedProxies)))
		w.Header().Set("X-Request-Id", id)
		w.Header().Set("X-Content-Type-Options", "nosniff")
		recorder := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		start := time.Now()
		defer func() {
			if v := recover(); v != nil {
				s.log.Error("panic", "request_id", id, "panic", v, "stack", string(debug.Stack()))
				if !recorder.wrote {
					writeError(recorder, r, http.StatusInternalServerError, "InternalError", "internal error")
				}
			}
			if r.URL.Path == "/healthz" && recorder.status == http.StatusOK {
				return // the container health check would drown everything else
			}
			s.log.Info("request", "request_id", id, "method", r.Method, "path", loggedPath(r.URL.Path),
				"status", recorder.status, "duration_ms", time.Since(start).Milliseconds(), "source_ip", sourceIP(r))
		}()
		next.ServeHTTP(recorder, r)
	})
}

// loggedPath hides the token in a console URL. The URL only works for the
// account it was issued to, but a log line is read by more people than that.
func loggedPath(path string) string {
	rest, ok := strings.CutPrefix(path, "/console/")
	if !ok {
		return path
	}
	if strings.HasSuffix(rest, "/ws") {
		return "/console/{token}/ws"
	}
	return "/console/{token}"
}

type statusRecorder struct {
	http.ResponseWriter
	status int
	wrote  bool
}

func (r *statusRecorder) WriteHeader(status int) {
	if !r.wrote {
		r.status, r.wrote = status, true
	}
	r.ResponseWriter.WriteHeader(status)
}

func (r *statusRecorder) Write(b []byte) (int, error) {
	r.wrote = true
	return r.ResponseWriter.Write(b)
}

// Unwrap lets http.ResponseController reach the real writer through this
// wrapper. Without it, a handler that needs to change a deadline — the image
// upload, which takes far longer than the server's read timeout — is told the
// feature is not supported.
func (r *statusRecorder) Unwrap() http.ResponseWriter { return r.ResponseWriter }

func requestID(r *http.Request) string {
	id, _ := r.Context().Value(requestIDKey{}).(string)
	return id
}

// sourceIP is the client address observe worked out for this request.
func sourceIP(r *http.Request) string {
	if ip, ok := r.Context().Value(clientIPKey{}).(string); ok {
		return ip
	}
	return clientIP(r, nil)
}

// clientIP is the address written to the audit log. X-Forwarded-For is read
// only when the socket peer is a configured proxy, and then from the right,
// stopping at the first hop that is not itself a proxy. A caller who sends the
// header directly, or prepends fake hops, therefore cannot choose what is logged.
func clientIP(r *http.Request, trusted []netip.Prefix) string {
	peer := r.RemoteAddr
	if host, _, err := net.SplitHostPort(r.RemoteAddr); err == nil {
		peer = host
	}
	addr, err := netip.ParseAddr(peer)
	if err != nil || !isTrustedProxy(addr, trusted) {
		return peer
	}
	hops := strings.Split(strings.Join(r.Header.Values("X-Forwarded-For"), ","), ",")
	for i := len(hops) - 1; i >= 0; i-- {
		hop, err := netip.ParseAddr(strings.TrimSpace(hops[i]))
		if err != nil {
			break
		}
		addr = hop.Unmap()
		if !isTrustedProxy(addr, trusted) {
			break
		}
	}
	return addr.String()
}

func isTrustedProxy(addr netip.Addr, trusted []netip.Prefix) bool {
	for _, prefix := range trusted {
		if prefix.Contains(addr.Unmap()) {
			return true
		}
	}
	return false
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

type errorBody struct {
	Error struct {
		Code    string `json:"code"`
		Message string `json:"message"`
	} `json:"error"`
	RequestID string `json:"request_id"`
}

func writeError(w http.ResponseWriter, r *http.Request, status int, code, message string) {
	var body errorBody
	body.Error.Code, body.Error.Message, body.RequestID = code, message, requestID(r)
	writeJSON(w, status, body)
}

func (s *Server) internalError(w http.ResponseWriter, r *http.Request, err error) {
	s.log.Error("internal error", "request_id", requestID(r), "err", err)
	writeError(w, r, http.StatusInternalServerError, "InternalError", "internal error")
}

// decodeJSON requires application/json, which an HTML form cannot send, and
// rejects unknown fields so a typo is an error rather than a silent default.
func decodeJSON(w http.ResponseWriter, r *http.Request, dst any) bool {
	if mediaType, _, _ := mime.ParseMediaType(r.Header.Get("Content-Type")); mediaType != "application/json" {
		writeError(w, r, http.StatusUnsupportedMediaType, "MalformedRequest", "Content-Type must be application/json")
		return false
	}
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(dst); err != nil || decoder.More() {
		writeError(w, r, http.StatusBadRequest, "MalformedRequest", "the body must be one JSON object matching the schema")
		return false
	}
	return true
}

// randomToken returns 256 random bits for cookies, OIDC state and nonces.
func randomToken() string {
	b := make([]byte, 32)
	rand.Read(b)
	return base64.RawURLEncoding.EncodeToString(b)
}

func randomHex(n int) string {
	b := make([]byte, n)
	rand.Read(b)
	return hex.EncodeToString(b)
}

// hashToken is how cookies and states are stored: a database dump alone does
// not let anyone resume a session.
func hashToken(token string) []byte {
	sum := sha256.Sum256([]byte(token))
	return sum[:]
}

func timeOrNil(t *time.Time) *time.Time {
	if t == nil {
		return nil
	}
	utc := t.UTC()
	return &utc
}
