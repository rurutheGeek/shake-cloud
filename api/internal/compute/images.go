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
	"sort"
	"strings"
	"time"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

// Image is something an instance can be launched from: either one of the
// deployment's shared images, declared in Terraform and rendered into
// site.json, or one a user uploaded. The two are merged here rather than
// copied into one table, so neither becomes a second copy of the other.
type Image struct {
	ID   string
	Name string
	// OS is "windows" for a Windows guest and "" for a Linux one. Shared
	// images declare it; an uploaded image is a Linux guest.
	OS            string
	Volume        string
	Format        string
	Public        bool
	AccountID     string
	OwnerUsername string
	SizeBytes     int64
	CreatedAt     time.Time
}

// Extensions Proxmox's import store recognises. The file is validated by
// qemu-img either way; refusing an unknown suffix up front just fails faster
// and with a clearer reason than a task log would give.
var imageExtensions = map[string]bool{".qcow2": true, ".raw": true, ".img": true, ".vmdk": true}

func newImageID() string {
	b := make([]byte, 9)
	rand.Read(b)
	return "img-" + hex.EncodeToString(b)[:17]
}

// ResolveImage finds an image by ID, shared ones first.
func (s *Service) ResolveImage(ctx context.Context, q db.Querier, imageID string) (Image, error) {
	if shared, ok := s.Site.Images[imageID]; ok {
		return Image{ID: imageID, Name: shared.Name, Volume: shared.Volume, OS: shared.OS, Public: true}, nil
	}
	if q == nil {
		q = s.Pool
	}
	uploaded, err := db.GetImage(ctx, q, imageID)
	if errors.Is(err, db.ErrNotFound) {
		return Image{}, refuse(http.StatusBadRequest, "InvalidImageID.NotFound",
			"image %q does not exist; see GET /v1/images", imageID)
	}
	if err != nil {
		return Image{}, err
	}
	return imageOf(uploaded), nil
}

func imageOf(i db.Image) Image {
	return Image{
		ID: i.ID, Name: i.Name, Volume: i.Volume, Format: i.Format,
		AccountID: i.AccountID, OwnerUsername: i.OwnerUsername,
		SizeBytes: i.SizeBytes, CreatedAt: i.CreatedAt,
	}
}

// Images lists the shared images and every account's uploaded ones.
func (s *Service) Images(ctx context.Context) ([]Image, error) {
	images := make([]Image, 0, len(s.Site.Images))
	for id, shared := range s.Site.Images {
		images = append(images, Image{ID: id, Name: shared.Name, Volume: shared.Volume, OS: shared.OS, Public: true})
	}
	sort.Slice(images, func(i, j int) bool { return images[i].ID < images[j].ID })
	uploaded, err := db.ListImages(ctx, s.Pool)
	if err != nil {
		return nil, err
	}
	for _, image := range uploaded {
		images = append(images, imageOf(image))
	}
	return images, nil
}

// tooLarge is returned by the capped reader once an upload passes its limit.
var errTooLarge = errors.New("image is larger than the limit")

// cappedReader stops an upload that grows past what the administrator allows.
// The size is not known in advance — the body is streamed and a client's
// Content-Length cannot be trusted — so the cap has to be enforced while
// copying. Failing here breaks the pipe, the Proxmox task fails, and nothing is
// stored.
type cappedReader struct {
	r    io.Reader
	left int64
}

func (c *cappedReader) Read(p []byte) (int, error) {
	if c.left <= 0 {
		return 0, errTooLarge
	}
	if int64(len(p)) > c.left {
		p = p[:c.left]
	}
	n, err := c.r.Read(p)
	c.left -= int64(n)
	return n, err
}

// ImportImage streams an uploaded disk image into the image store and records
// it. The bytes never touch the API's filesystem: /tmp is RAM-backed and an
// image is measured in gigabytes.
func (s *Service) ImportImage(ctx context.Context, accountID, name, fileName string, body io.Reader,
	audit func(db.Image) error) (db.Image, error) {
	name = strings.TrimSpace(name)
	if name == "" || len(name) > 128 {
		return db.Image{}, refuse(http.StatusBadRequest, "InvalidParameterValue", "name must be 1-128 characters")
	}
	extension := strings.ToLower(path.Ext(fileName))
	if !imageExtensions[extension] {
		return db.Image{}, refuse(http.StatusBadRequest, "InvalidParameterValue",
			"the file must be a disk image (.qcow2, .raw, .img or .vmdk), not %q", extension)
	}
	limits, _, err := s.EffectiveLimits(ctx, s.Pool)
	if err != nil {
		return db.Image{}, err
	}

	store := s.Site.Storage.Images
	status, err := s.PVE.StorageStatus(ctx, store)
	if err != nil {
		return db.Image{}, s.unavailable(err)
	}
	minFree := int64(limits.Capacity.ImageStoreMinFreeMiB) << 20
	if status.Avail <= minFree {
		return db.Image{}, refuse(http.StatusConflict, "ImageLimitExceeded",
			"the image store has %d MiB free and %d MiB must stay free", status.Avail>>20, limits.Capacity.ImageStoreMinFreeMiB)
	}
	// Never let one upload eat the reserve, whatever the configured cap says.
	allowed := status.Avail - minFree
	if cap := int64(limits.Capacity.MaxImageGiB) << 30; cap > 0 && cap < allowed {
		allowed = cap
	}

	if s.UploadDir == "" {
		return db.Image{}, refuse(http.StatusServiceUnavailable, "ServiceUnavailable",
			"this deployment has no upload directory configured, so images cannot be uploaded")
	}
	imageID := newImageID()
	fileName = imageID + extension

	// Spooled to disk first because the node needs the exact length declared up
	// front: it answers 501 to a chunked body, and the length of an upload is
	// not known until the body ends.
	spool, err := os.CreateTemp(s.UploadDir, "upload-*")
	if err != nil {
		return db.Image{}, fmt.Errorf("open a spool file: %w", err)
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
		return db.Image{}, refuse(http.StatusRequestEntityTooLarge, "RequestEntityTooLarge",
			"the image is larger than the %d MiB this upload may use", allowed>>20)
	case err != nil:
		return db.Image{}, fmt.Errorf("receive the image: %w", err)
	case written == 0:
		return db.Image{}, refuse(http.StatusBadRequest, "InvalidParameterValue", "the file is empty")
	}
	if _, err := spool.Seek(0, io.SeekStart); err != nil {
		return db.Image{}, err
	}

	upid, err := s.PVE.UploadImage(ctx, store, fileName, spool, written)
	if err != nil {
		return db.Image{}, fmt.Errorf("upload image: %w", err)
	}
	if err := s.PVE.WaitTask(ctx, upid); err != nil {
		// qemu-img refused it: the file is the caller's problem, not the server's.
		return db.Image{}, refuse(http.StatusBadRequest, "InvalidParameterValue",
			"the image store refused the file: %s", truncate(err.Error(), 300))
	}

	volume := store + ":import/" + fileName
	stored, err := s.storedVolume(ctx, store, volume)
	if err != nil {
		return db.Image{}, err
	}
	image, err := db.InsertImage(ctx, s.Pool, db.Image{
		ID: imageID, AccountID: accountID, Name: name, Volume: volume,
		Format: stored.Format, SizeBytes: stored.Size,
	})
	if err != nil {
		// The ledger is the record of ownership; a file nobody owns is litter.
		if removeErr := s.PVE.DeleteVolume(ctx, store, volume); removeErr != nil {
			s.Log.Error("could not remove an image the ledger rejected", "volume", volume, "err", removeErr)
		}
		return db.Image{}, err
	}
	if audit != nil {
		if err := audit(image); err != nil {
			return db.Image{}, err
		}
	}
	s.Log.Info("image uploaded", "image_id", imageID, "account_id", accountID,
		"size_bytes", stored.Size, "format", stored.Format)
	return image, nil
}

// storedVolume reads back what the store actually made of the upload, so the
// recorded size and format are the store's answer rather than our guess.
func (s *Service) storedVolume(ctx context.Context, store, volume string) (proxmoxVolume, error) {
	volumes, err := s.PVE.ListVolumes(ctx, store, "import")
	if err != nil {
		return proxmoxVolume{}, s.unavailable(err)
	}
	for _, v := range volumes {
		if v.VolID == volume {
			format := v.Format
			if format == "" {
				format = strings.TrimPrefix(path.Ext(volume), ".")
			}
			return proxmoxVolume{Size: v.Size, Format: format}, nil
		}
	}
	return proxmoxVolume{}, fmt.Errorf("the image store accepted %s but does not list it", volume)
}

type proxmoxVolume struct {
	Size   int64
	Format string
}

// DeleteImage removes an uploaded image. authorize decides whether the caller
// may; a shared image cannot be deleted at all, because Terraform declares it.
func (s *Service) DeleteImage(ctx context.Context, imageID string, authorize func(db.Image) bool,
	audit func(db.Image) error) error {
	if _, shared := s.Site.Images[imageID]; shared {
		return refuse(http.StatusConflict, "ImageLimitExceeded",
			"%s is one of the deployment's shared images and is declared in Terraform, not through the API", imageID)
	}
	image, err := db.GetImage(ctx, s.Pool, imageID)
	if errors.Is(err, db.ErrNotFound) {
		return refuse(http.StatusNotFound, "InvalidImageID.NotFound", "image %s does not exist", imageID)
	}
	if err != nil {
		return err
	}
	if authorize != nil && !authorize(image) {
		return refuse(http.StatusForbidden, "UnauthorizedOperation",
			"image %s belongs to another account", imageID)
	}
	// A launch copies the image into the instance's disk, so only one still
	// being created would notice it going away.
	launching, err := db.LaunchingFromImage(ctx, s.Pool, imageID)
	if err != nil {
		return err
	}
	if launching > 0 {
		return refuse(http.StatusConflict, "IncorrectInstanceState",
			"%d instance(s) are still being created from %s; try again once they are running", launching, imageID)
	}
	if err := s.PVE.DeleteVolume(ctx, s.Site.Storage.Images, image.Volume); err != nil {
		return fmt.Errorf("delete image volume: %w", err)
	}
	if err := db.DeleteImage(ctx, s.Pool, imageID); err != nil {
		return err
	}
	if audit != nil {
		if err := audit(image); err != nil {
			return err
		}
	}
	s.Log.Info("image deleted", "image_id", imageID, "volume", image.Volume)
	return nil
}
