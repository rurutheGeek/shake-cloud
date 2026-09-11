package server

import (
	"embed"
	"errors"
	"html/template"
	"io/fs"
	"net/http"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

// The Phase 1 page: log in, manage access keys, read the audit log. It calls
// the same JSON API as Terraform. The self-service portal replaces it in Phase 5.

//go:embed web
var webFiles embed.FS

var templates = template.Must(template.ParseFS(webFiles, "web/*.html"))

// No inline script or style, and nothing from other origins.
const contentSecurityPolicy = "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; " +
	"img-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"

func staticFiles() http.Handler {
	root, err := fs.Sub(webFiles, "web")
	if err != nil {
		panic(err)
	}
	return http.FileServerFS(root)
}

func (s *Server) portal(w http.ResponseWriter, r *http.Request) {
	var data struct {
		LoggedIn bool
		Account  db.Account
	}
	account, err := s.sessionAccount(r)
	switch {
	case err == nil:
		data.LoggedIn, data.Account = true, account
	case !errors.Is(err, db.ErrNotFound):
		s.internalError(w, r, err)
		return
	}
	renderHTML(w, http.StatusOK, "index.html", data)
}

// loginPage explains a failed login to a person; the login endpoints are
// reached by browser navigation, so JSON would be unreadable there.
func loginPage(w http.ResponseWriter, status int, message string) {
	renderHTML(w, status, "message.html", message)
}

func renderHTML(w http.ResponseWriter, status int, name string, data any) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Content-Security-Policy", contentSecurityPolicy)
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Referrer-Policy", "same-origin")
	w.WriteHeader(status)
	_ = templates.ExecuteTemplate(w, name, data)
}
