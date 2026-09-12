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

type imageBody struct {
	ImageID string `json:"image_id"`
	Name    string `json:"name"`
	State   string `json:"state"`
	Public  bool   `json:"public"`
	// Absent for the deployment's shared images, which have no uploader.
	AccountID     string `json:"account_id,omitempty"`
	OwnerUsername string `json:"owner_username,omitempty"`
	Format        string `json:"format,omitempty"`
	// A pointer so that a shared image, whose size the ledger does not hold, is
	// absent rather than reported as zero.
	SizeMiB   *int64     `json:"size_mib,omitempty"`
	CreatedAt *time.Time `json:"created_at,omitempty"`
}

// sizeMiB rounds up, because a file smaller than a mebibyte still occupies
// something and reporting 0 for it would read as "size unknown".
func sizeMiB(bytes int64) int64 { return (bytes + (1 << 20) - 1) >> 20 }

func imageJSON(i compute.Image) imageBody {
	body := imageBody{ImageID: i.ID, Name: i.Name, State: "available", Public: i.Public,
		AccountID: i.AccountID, OwnerUsername: i.OwnerUsername, Format: i.Format}
	if i.SizeBytes > 0 {
		mib := sizeMiB(i.SizeBytes)
		body.SizeMiB = &mib
	}
	if !i.CreatedAt.IsZero() {
		created := i.CreatedAt.UTC()
		body.CreatedAt = &created
	}
	return body
}

func (s *Server) describeImages(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	images, err := service.Images(r.Context())
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	body := make([]imageBody, 0, len(images))
	for _, image := range images {
		body = append(body, imageJSON(image))
	}
	writeJSON(w, http.StatusOK, map[string]any{"images": body})
}

// maxImageNameField bounds the small text part of the upload. The image itself
// is streamed and bounded by the administrator's limit instead.
const maxImageNameField = 1 << 12

// importImage hands an uploaded disk image to the image store.
//
// It reads the multipart body part by part instead of calling
// ParseMultipartForm, which would decide for itself where to put a
// multi-gigabyte file. The compute layer spools it to the configured upload
// directory — real disk, never the RAM-backed /tmp — because the node refuses a
// request whose length is not declared, and a length cannot be known without
// measuring the body first.
func (s *Server) importImage(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	// The server's read timeout is meant for ordinary requests; an image takes
	// minutes. Clearing the deadline for this one request keeps the timeout
	// protecting everything else.
	if err := http.NewResponseController(w).SetReadDeadline(time.Time{}); err != nil {
		s.log.Warn("could not clear the read deadline for an upload", "err", err)
	}

	parts, err := r.MultipartReader()
	if err != nil {
		writeError(w, r, http.StatusBadRequest, "MalformedRequest", "the body must be multipart/form-data with a name and a file")
		return
	}
	name := ""
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
		case "name":
			value, err := io.ReadAll(io.LimitReader(part, maxImageNameField))
			if err != nil {
				writeError(w, r, http.StatusBadRequest, "MalformedRequest", "the name could not be read")
				return
			}
			name = strings.TrimSpace(string(value))
		case "file":
			if name == "" {
				// Streaming means the name cannot be waited for: it has to
				// arrive before the bytes it names.
				writeError(w, r, http.StatusBadRequest, "MalformedRequest", "send the name part before the file part")
				return
			}
			image, err := service.ImportImage(r.Context(), c.principal.account.ID, name, part.FileName(), part,
				func(created db.Image) error {
					event := c.event("", map[string]any{"name": created.Name, "format": created.Format,
						"size_mib": sizeMiB(created.SizeBytes)})
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
			writeJSON(w, http.StatusCreated, map[string]any{"image": imageJSON(compute.Image{
				ID: image.ID, Name: image.Name, Volume: image.Volume, Format: image.Format,
				AccountID: image.AccountID, OwnerUsername: image.OwnerUsername,
				SizeBytes: image.SizeBytes, CreatedAt: image.CreatedAt,
			})})
			return
		default:
			// An unexpected part is a typo in the client, not something to skip.
			writeError(w, r, http.StatusBadRequest, "MalformedRequest",
				"unexpected part "+part.FormName()+"; send name and file")
			return
		}
	}
}

func (s *Server) deleteImage(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	id := r.PathValue("image_id")
	mayDelete := func(i db.Image) bool {
		return c.principal.account.IsAdmin || i.AccountID == c.principal.account.ID
	}
	err := service.DeleteImage(r.Context(), id, mayDelete, func(deleted db.Image) error {
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
