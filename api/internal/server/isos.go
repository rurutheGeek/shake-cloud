package server

import (
	"errors"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/compute"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

// ISO installation media, uploaded and attached as a CD-ROM. It is separate
// from an image because it never becomes a root disk.
type isoBody struct {
	ISOID         string     `json:"iso_id"`
	Name          string     `json:"name"`
	OS            string     `json:"os,omitempty"`
	Public        bool       `json:"public,omitempty"`
	AccountID     string     `json:"account_id,omitempty"`
	OwnerUsername string     `json:"owner_username,omitempty"`
	SizeMiB       int64      `json:"size_mib,omitempty"`
	CreatedAt     *time.Time `json:"created_at,omitempty"`
}

func isoJSON(i compute.ISO) isoBody {
	body := isoBody{ISOID: i.ID, Name: i.Name, OS: i.OS, Public: i.Public, AccountID: i.AccountID,
		OwnerUsername: i.OwnerUsername, SizeMiB: sizeMiB(i.SizeBytes)}
	if !i.CreatedAt.IsZero() {
		created := i.CreatedAt.UTC()
		body.CreatedAt = &created
	}
	return body
}

func (s *Server) describeISOs(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	isos, err := service.ISOs(r.Context())
	if err != nil {
		s.computeError(w, r, err)
		return
	}
	body := make([]isoBody, 0, len(isos))
	for _, iso := range isos {
		body = append(body, isoJSON(iso))
	}
	writeJSON(w, http.StatusOK, map[string]any{"isos": body})
}

// importISO streams an uploaded ISO into the image store. It reads the
// multipart body part by part, as importImage does, because a Windows ISO is
// several gigabytes and must not be buffered in RAM.
func (s *Server) importISO(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	if err := http.NewResponseController(w).SetReadDeadline(time.Time{}); err != nil {
		s.log.Warn("could not clear the read deadline for an ISO upload", "err", err)
	}
	parts, err := r.MultipartReader()
	if err != nil {
		writeError(w, r, http.StatusBadRequest, "MalformedRequest", "the body must be multipart/form-data with a name, an os and a file")
		return
	}
	name, guestOS := "", ""
	for {
		part, err := parts.NextPart()
		if errors.Is(err, io.EOF) {
			writeError(w, r, http.StatusBadRequest, "MalformedRequest", "the body has no file part")
			return
		}
		if err != nil {
			writeError(w, r, http.StatusBadRequest, "MalformedRequest", "the multipart body could not be read")
			return
		}
		switch part.FormName() {
		case "name", "os":
			value, err := io.ReadAll(io.LimitReader(part, maxImageNameField))
			if err != nil {
				writeError(w, r, http.StatusBadRequest, "MalformedRequest", part.FormName()+" could not be read")
				return
			}
			if part.FormName() == "name" {
				name = strings.TrimSpace(string(value))
			} else {
				guestOS = strings.TrimSpace(string(value))
			}
		case "file":
			if name == "" {
				// Streaming means the metadata cannot be waited for.
				writeError(w, r, http.StatusBadRequest, "MalformedRequest", "send the name and os parts before the file part")
				return
			}
			iso, err := service.ImportISO(r.Context(), c.principal.account.ID, name, guestOS, part.FileName(), part,
				func(created db.ISO) error {
					event := c.event("", map[string]any{"name": created.Name, "os": created.OS, "size_mib": sizeMiB(created.SizeBytes)})
					event.ResourceID = created.ID
					return db.RecordAudit(r.Context(), s.pool, event)
				})
			if err != nil {
				if refusal := (*compute.Error)(nil); errors.As(err, &refusal) {
					s.recordDenied(r.Context(), c.event(refusal.Code, map[string]any{"name": name}))
				}
				s.computeError(w, r, err)
				return
			}
			writeJSON(w, http.StatusCreated, map[string]any{"iso": isoJSON(compute.ISO{
				ID: iso.ID, Name: iso.Name, Volume: iso.Volume, OS: iso.OS,
				AccountID: iso.AccountID, OwnerUsername: iso.OwnerUsername,
				SizeBytes: iso.SizeBytes, CreatedAt: iso.CreatedAt,
			})})
			return
		default:
			writeError(w, r, http.StatusBadRequest, "MalformedRequest",
				"unexpected part "+part.FormName()+"; send name, os and file")
			return
		}
	}
}

func (s *Server) deleteISO(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	id := r.PathValue("iso_id")
	mayDelete := func(i db.ISO) bool {
		return c.principal.account.IsAdmin || i.AccountID == c.principal.account.ID
	}
	err := service.DeleteISO(r.Context(), id, mayDelete, func(deleted db.ISO) error {
		event := c.event("", map[string]any{"owner_account_id": deleted.AccountID, "name": deleted.Name})
		event.ResourceID = deleted.ID
		return db.RecordAudit(r.Context(), s.pool, event)
	})
	if err != nil {
		if refusal := (*compute.Error)(nil); errors.As(err, &refusal) {
			event := c.event(refusal.Code, nil)
			event.ResourceID = id
			s.recordDenied(r.Context(), event)
		}
		s.computeError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
