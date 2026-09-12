package compute

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path"
	"strings"
	"time"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/seed"
)

// ISO is installation media. Unlike an Image it is never copied to the root
// disk; the worker attaches it as a CD-ROM.
type ISO struct {
	ID   string
	Name string
	// Volume is the Proxmox volume the CD-ROM points at. A shared ISO keeps
	// the administrator's volume as-is; an uploaded one lives in the cloud's
	// own store.
	Volume string
	OS     string
	// Public marks an ISO the administrator declared in Terraform. Everyone
	// may install from it, nobody may delete it through the API.
	Public        bool
	AccountID     string
	OwnerUsername string
	SizeBytes     int64
	CreatedAt     time.Time
}

// Only .iso. Proxmox does not import anything else into a CD-ROM.
var isoExtensions = map[string]bool{".iso": true}

func newISOID() string {
	b := make([]byte, 9)
	rand.Read(b)
	return "iso-" + hex.EncodeToString(b)[:17]
}

func isoOf(i db.ISO) ISO {
	return ISO{ID: i.ID, Name: i.Name, Volume: i.Volume, OS: i.OS,
		AccountID: i.AccountID, OwnerUsername: i.OwnerUsername, SizeBytes: i.SizeBytes, CreatedAt: i.CreatedAt}
}

// ResolveISO finds an ISO by ID.
func (s *Service) ResolveISO(ctx context.Context, q db.Querier, isoID string) (ISO, error) {
	if shared, ok := s.Site.SharedISOs[isoID]; ok {
		return ISO{ID: isoID, Name: shared.Name, Volume: shared.Volume, OS: shared.OS, Public: true}, nil
	}
	if q == nil {
		q = s.Pool
	}
	stored, err := db.GetISO(ctx, q, isoID)
	if errors.Is(err, db.ErrNotFound) {
		return ISO{}, refuse(http.StatusBadRequest, "InvalidISOID.NotFound",
			"ISO %q does not exist; see GET /v1/isos", isoID)
	}
	if err != nil {
		return ISO{}, err
	}
	return isoOf(stored), nil
}

// ISOs lists the administrator's shared ISOs and every account's uploaded
// ones, newest first, as images do.
func (s *Service) ISOs(ctx context.Context) ([]ISO, error) {
	stored, err := db.ListISOs(ctx, s.Pool)
	if err != nil {
		return nil, err
	}
	isos := make([]ISO, 0, len(s.Site.SharedISOs)+len(stored))
	for id, shared := range s.Site.SharedISOs {
		isos = append(isos, ISO{ID: id, Name: shared.Name, Volume: shared.Volume, OS: shared.OS, Public: true})
	}
	for _, i := range stored {
		isos = append(isos, isoOf(i))
	}
	return isos, nil
}

// ImportISO streams an uploaded ISO into the image store and records it. Only
// the envelope is held in memory; the file is spooled to disk because Proxmox
// needs the exact length up front, exactly as an image upload does.
func (s *Service) ImportISO(ctx context.Context, accountID, name, guestOS, fileName string, body io.Reader,
	audit func(db.ISO) error) (db.ISO, error) {
	name = strings.TrimSpace(name)
	if name == "" || len(name) > 128 {
		return db.ISO{}, refuse(http.StatusBadRequest, "InvalidParameterValue", "name must be 1-128 characters")
	}
	if guestOS != "" && guestOS != seed.OSLinux && guestOS != seed.OSWindows {
		return db.ISO{}, refuse(http.StatusBadRequest, "InvalidParameterValue", "os must be linux or windows")
	}
	extension := strings.ToLower(path.Ext(fileName))
	if !isoExtensions[extension] {
		return db.ISO{}, refuse(http.StatusBadRequest, "InvalidParameterValue",
			"the file must be an ISO image (.iso), not %q", extension)
	}
	limits, _, err := s.EffectiveLimits(ctx, s.Pool)
	if err != nil {
		return db.ISO{}, err
	}
	store := s.Site.Storage.Images
	status, err := s.PVE.StorageStatus(ctx, store)
	if err != nil {
		return db.ISO{}, s.unavailable(err)
	}
	minFree := int64(limits.Capacity.ImageStoreMinFreeMiB) << 20
	if status.Avail <= minFree {
		return db.ISO{}, refuse(http.StatusConflict, "ImageLimitExceeded",
			"the image store has %d MiB free and %d MiB must stay free", status.Avail>>20, limits.Capacity.ImageStoreMinFreeMiB)
	}
	allowed := status.Avail - minFree
	if cap := int64(limits.Capacity.MaxImageGiB) << 30; cap > 0 && cap < allowed {
		allowed = cap
	}
	if s.UploadDir == "" {
		return db.ISO{}, refuse(http.StatusServiceUnavailable, "ServiceUnavailable",
			"this deployment has no upload directory configured, so ISOs cannot be uploaded")
	}
	isoID := newISOID()
	fileName = isoID + extension

	spool, err := os.CreateTemp(s.UploadDir, "upload-*")
	if err != nil {
		return db.ISO{}, fmt.Errorf("open a spool file: %w", err)
	}
	defer func() {
		spool.Close()
		if err := os.Remove(spool.Name()); err != nil && !os.IsNotExist(err) {
			s.Log.Error("could not remove an upload spool file", "path", spool.Name(), "err", err)
		}
	}()
	written, err := io.Copy(spool, &cappedReader{r: body, left: allowed})
	switch {
	case errors.Is(err, errTooLarge):
		return db.ISO{}, refuse(http.StatusRequestEntityTooLarge, "RequestEntityTooLarge",
			"the ISO is larger than the %d MiB this upload may use", allowed>>20)
	case err != nil:
		return db.ISO{}, fmt.Errorf("receive the ISO: %w", err)
	case written == 0:
		return db.ISO{}, refuse(http.StatusBadRequest, "InvalidParameterValue", "the file is empty")
	}
	if _, err := spool.Seek(0, io.SeekStart); err != nil {
		return db.ISO{}, err
	}
	upid, err := s.PVE.UploadISOStream(ctx, store, fileName, spool, written)
	if err != nil {
		return db.ISO{}, fmt.Errorf("upload ISO: %w", err)
	}
	if err := s.PVE.WaitTask(ctx, upid); err != nil {
		return db.ISO{}, refuse(http.StatusBadRequest, "InvalidParameterValue",
			"the image store refused the file: %s", truncate(err.Error(), 300))
	}
	volume := store + ":iso/" + fileName
	stored, err := db.InsertISO(ctx, s.Pool, db.ISO{
		ID: isoID, AccountID: accountID, Name: name, Volume: volume, SizeBytes: written, OS: guestOS,
	})
	if err != nil {
		if removeErr := s.PVE.DeleteVolume(ctx, store, volume); removeErr != nil {
			s.Log.Error("could not remove an ISO the ledger rejected", "volume", volume, "err", removeErr)
		}
		return db.ISO{}, err
	}
	if audit != nil {
		if err := audit(stored); err != nil {
			return db.ISO{}, err
		}
	}
	s.Log.Info("ISO uploaded", "iso_id", isoID, "account_id", accountID, "size_bytes", written, "os", guestOS)
	return stored, nil
}

// DeleteISO removes an uploaded ISO. authorize decides whether the caller may.
func (s *Service) DeleteISO(ctx context.Context, isoID string, authorize func(db.ISO) bool,
	audit func(db.ISO) error) error {
	if _, shared := s.Site.SharedISOs[isoID]; shared {
		return refuse(http.StatusConflict, "InvalidParameterValue",
			"%s is a shared ISO declared in Terraform, not through the API", isoID)
	}
	iso, err := db.GetISO(ctx, s.Pool, isoID)
	if errors.Is(err, db.ErrNotFound) {
		return refuse(http.StatusNotFound, "InvalidISOID.NotFound", "ISO %s does not exist", isoID)
	}
	if err != nil {
		return err
	}
	if authorize != nil && !authorize(iso) {
		return refuse(http.StatusForbidden, "UnauthorizedOperation",
			"ISO %s belongs to another account", isoID)
	}
	// A live instance keeps booting from this media; deleting it would remove
	// the CD-ROM from under a running guest.
	inUse, err := db.ISOInUse(ctx, s.Pool, isoID)
	if err != nil {
		return err
	}
	if inUse > 0 {
		return refuse(http.StatusConflict, "IncorrectInstanceState",
			"%d live instance(s) still use %s; delete them first", inUse, isoID)
	}
	if err := s.PVE.DeleteVolume(ctx, s.Site.Storage.Images, iso.Volume); err != nil {
		return fmt.Errorf("delete ISO volume: %w", err)
	}
	if err := db.DeleteISO(ctx, s.Pool, isoID); err != nil {
		return err
	}
	if audit != nil {
		if err := audit(iso); err != nil {
			return err
		}
	}
	s.Log.Info("ISO deleted", "iso_id", isoID, "volume", iso.Volume)
	return nil
}
