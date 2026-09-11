package server

import (
	"errors"
	"net/http"
	"time"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/sshkey"
)

// SSH public keys. Only the public half is ever stored, and it is copied into
// an instance's seed image at launch, so these endpoints need nothing from
// Proxmox and keep working when instances are not configured.

type keyPairBody struct {
	KeyName     string    `json:"key_name"`
	Fingerprint string    `json:"fingerprint"`
	CreatedAt   time.Time `json:"created_at"`
}

func keyPairJSON(k db.KeyPair) keyPairBody {
	// The key material itself is not echoed: the caller sent it, and a listing
	// that repeats it only widens where it can be read from.
	return keyPairBody{KeyName: k.KeyName, Fingerprint: k.Fingerprint, CreatedAt: k.CreatedAt.UTC()}
}

func (s *Server) describeKeyPairs(w http.ResponseWriter, r *http.Request, c *call) {
	keys, err := db.ListKeyPairs(r.Context(), s.pool, c.principal.account.ID)
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	body := make([]keyPairBody, 0, len(keys))
	for _, key := range keys {
		body = append(body, keyPairJSON(key))
	}
	writeJSON(w, http.StatusOK, map[string]any{"key_pairs": body})
}

func (s *Server) importKeyPair(w http.ResponseWriter, r *http.Request, c *call) {
	var body struct {
		KeyName   string `json:"key_name"`
		PublicKey string `json:"public_key"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	if !keyName.MatchString(body.KeyName) {
		writeError(w, r, http.StatusBadRequest, "ValidationError",
			"key_name must be 1-64 characters of letters, digits, space or . _ : @ -")
		return
	}
	key, err := sshkey.Parse(body.PublicKey)
	if err != nil {
		// The parse error says what is wrong with the key, which is the whole
		// point of refusing it here rather than at first boot.
		writeError(w, r, http.StatusBadRequest, "ValidationError", err.Error())
		return
	}

	created, err := db.InsertKeyPair(r.Context(), s.pool, db.KeyPair{
		AccountID: c.principal.account.ID, KeyName: body.KeyName,
		PublicKey: key.Text, Fingerprint: key.Fingerprint,
	})
	switch {
	case errors.Is(err, db.ErrKeyNameTaken):
		s.recordDenied(r.Context(), c.event("InvalidKeyPair.Duplicate", nil))
		writeError(w, r, http.StatusConflict, "InvalidKeyPair.Duplicate",
			"you already have a key called "+body.KeyName)
		return
	case err != nil:
		s.internalError(w, r, err)
		return
	}
	event := c.event("", map[string]any{"fingerprint": key.Fingerprint, "type": key.Type})
	event.ResourceID = created.KeyName
	if err := db.RecordAudit(r.Context(), s.pool, event); err != nil {
		s.log.Error("audit write failed", "err", err, "event_name", event.EventName)
	}
	writeJSON(w, http.StatusCreated, map[string]any{"key_pair": keyPairJSON(created)})
}

func (s *Server) deleteKeyPair(w http.ResponseWriter, r *http.Request, c *call) {
	name := r.PathValue("key_name")
	err := db.DeleteKeyPair(r.Context(), s.pool, c.principal.account.ID, name)
	switch {
	case errors.Is(err, db.ErrNotFound):
		writeError(w, r, http.StatusNotFound, "InvalidKeyPair.NotFound", "you have no key called "+name)
	case err != nil:
		s.internalError(w, r, err)
	default:
		event := c.event("", nil)
		event.ResourceID = name
		if err := db.RecordAudit(r.Context(), s.pool, event); err != nil {
			s.log.Error("audit write failed", "err", err, "event_name", event.EventName)
		}
		w.WriteHeader(http.StatusNoContent)
	}
}
