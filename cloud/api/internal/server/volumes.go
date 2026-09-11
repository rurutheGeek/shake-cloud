package server

import (
	"errors"
	"net/http"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/compute"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

// Volumes, the EBS counterpart. Like instances, every volume is visible to
// every caller, and only its owner or a cloud-admin may change it.

type volumeAttachmentBody struct {
	InstanceID string `json:"instance_id"`
	Device     string `json:"device"`
	State      string `json:"state"`
	// DevicePath is where the guest finds the disk whatever order it was
	// plugged in: the serial is the volume ID.
	DevicePath string `json:"device_path"`
}

type volumeBody struct {
	VolumeID          string                `json:"volume_id"`
	AccountID         string                `json:"account_id"`
	OwnerUsername     string                `json:"owner_username,omitempty"`
	SizeGiB           int                   `json:"size_gib"`
	State             string                `json:"state"`
	StateReason       string                `json:"state_reason,omitempty"`
	ModificationState string                `json:"modification_state,omitempty"`
	Serial            string                `json:"serial"`
	Tags              map[string]string     `json:"tags,omitempty"`
	ClientToken       string                `json:"client_token,omitempty"`
	CreateTime        time.Time             `json:"create_time"`
	Attachment        *volumeAttachmentBody `json:"attachment,omitempty"`
}

func volumeJSON(v db.Volume, owned bool) volumeBody {
	serial := compute.VolumeSerial(v.ID)
	body := volumeBody{
		VolumeID: v.ID, AccountID: v.AccountID, OwnerUsername: v.OwnerUsername, SizeGiB: v.SizeGiB,
		State: v.State, StateReason: v.StateReason, Serial: serial, Tags: v.Tags, CreateTime: v.CreatedAt.UTC(),
	}
	if v.PendingAction == db.VolumeActionResize {
		body.ModificationState = "modifying"
	}
	if v.InstanceID != "" {
		body.Attachment = &volumeAttachmentBody{InstanceID: v.InstanceID, Device: v.Device, State: v.AttachmentState,
			DevicePath: "/dev/disk/by-id/virtio-" + serial}
	}
	// A detach waits for the guest to let go of the disk, and only the error
	// says so; without it the owner sees "detaching" and no reason.
	if v.PendingAction == db.VolumeActionDetach && v.LastError != "" && v.StateReason == "" {
		body.StateReason = "Client.VolumeBusy: " + v.LastError
	}
	if owned {
		body.ClientToken = v.ClientToken
	}
	return body
}

func (c *call) mayTouchVolume(v db.Volume) bool {
	return c.principal.account.IsAdmin || v.AccountID == c.principal.account.ID
}

// mayActOnVolume is mayAct for volumes: 404 for none, 403 for someone else's.
func (s *Server) mayActOnVolume(w http.ResponseWriter, r *http.Request, c *call, id string) bool {
	volume, err := db.GetVolume(r.Context(), s.pool, id)
	switch {
	case errors.Is(err, db.ErrNotFound):
		writeError(w, r, http.StatusNotFound, "InvalidVolume.NotFound", "volume "+id+" does not exist")
	case err != nil:
		s.internalError(w, r, err)
	case !c.mayTouchVolume(volume):
		event := c.event("UnauthorizedOperation", map[string]any{"owner_account_id": volume.AccountID})
		event.ResourceID = id
		s.recordDenied(r.Context(), event)
		writeError(w, r, http.StatusForbidden, "UnauthorizedOperation",
			"volume "+id+" belongs to another account; only its owner or a cloud-admin may change it")
	default:
		return true
	}
	return false
}

// volumeAudit records a volume change inside the transaction that makes it.
func volumeAudit(r *http.Request, c *call, detail map[string]any) func(pgx.Tx, db.Volume) error {
	return func(tx pgx.Tx, v db.Volume) error {
		if detail == nil {
			detail = map[string]any{}
		}
		detail["owner_account_id"] = v.AccountID
		event := c.event("", detail)
		event.ResourceID = v.ID
		return db.RecordAudit(r.Context(), tx, event)
	}
}

// volumeRefused records a refused volume request and writes the error.
func (s *Server) volumeRefused(w http.ResponseWriter, r *http.Request, c *call, id string, err error) {
	if refusal := (*compute.Error)(nil); errors.As(err, &refusal) {
		event := c.event(refusal.Code, nil)
		event.ResourceID = id
		s.recordDenied(r.Context(), event)
	}
	s.computeError(w, r, err)
}

func (s *Server) describeVolumes(w http.ResponseWriter, r *http.Request, c *call) {
	if s.computeService(w, r) == nil {
		return
	}
	volumes, err := db.ListVolumes(r.Context(), s.pool)
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	body := make([]volumeBody, 0, len(volumes))
	for _, volume := range volumes {
		body = append(body, volumeJSON(volume, c.mayTouchVolume(volume)))
	}
	writeJSON(w, http.StatusOK, map[string]any{"volumes": body})
}

func (s *Server) describeVolume(w http.ResponseWriter, r *http.Request, c *call) {
	if s.computeService(w, r) == nil {
		return
	}
	id := r.PathValue("volume_id")
	volume, err := db.GetVolume(r.Context(), s.pool, id)
	if errors.Is(err, db.ErrNotFound) {
		writeError(w, r, http.StatusNotFound, "InvalidVolume.NotFound", "volume "+id+" does not exist")
		return
	}
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"volume": volumeJSON(volume, c.mayTouchVolume(volume))})
}

func (s *Server) createVolume(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	var request compute.CreateVolumeRequest
	if !decodeJSON(w, r, &request) {
		return
	}
	volume, created, err := service.CreateVolume(r.Context(), c.principal.account.ID, request,
		volumeAudit(r, c, map[string]any{"size_gib": request.SizeGiB}))
	if err != nil {
		s.volumeRefused(w, r, c, "", err)
		return
	}
	status := http.StatusAccepted
	if !created {
		// A repeated client_token returns the original volume unchanged.
		status = http.StatusOK
	}
	writeJSON(w, status, map[string]any{"volume": volumeJSON(volume, true)})
}

func (s *Server) modifyVolume(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	id := r.PathValue("volume_id")
	if !s.mayActOnVolume(w, r, c, id) {
		return
	}
	var request struct {
		SizeGiB int `json:"size_gib"`
	}
	if !decodeJSON(w, r, &request) {
		return
	}
	volume, err := service.ModifyVolume(r.Context(), id, request.SizeGiB, c.mayTouchVolume,
		volumeAudit(r, c, map[string]any{"size_gib": request.SizeGiB}))
	if err != nil {
		s.volumeRefused(w, r, c, id, err)
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"volume": volumeJSON(volume, true)})
}

func (s *Server) deleteVolume(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	id := r.PathValue("volume_id")
	if !s.mayActOnVolume(w, r, c, id) {
		return
	}
	volume, err := service.DeleteVolume(r.Context(), id, c.mayTouchVolume, volumeAudit(r, c, nil))
	if err != nil {
		s.volumeRefused(w, r, c, id, err)
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"volume": volumeJSON(volume, true)})
}

func (s *Server) attachVolume(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	id := r.PathValue("volume_id")
	if !s.mayActOnVolume(w, r, c, id) {
		return
	}
	var request struct {
		InstanceID string `json:"instance_id"`
		Device     string `json:"device"`
	}
	if !decodeJSON(w, r, &request) {
		return
	}
	volume, err := service.AttachVolume(r.Context(), id, request.InstanceID, request.Device, c.mayTouchVolume,
		func(tx pgx.Tx, v db.Volume) error {
			return volumeAudit(r, c, map[string]any{"instance_id": v.InstanceID, "device": v.Device})(tx, v)
		})
	if err != nil {
		s.volumeRefused(w, r, c, id, err)
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"volume": volumeJSON(volume, true)})
}

func (s *Server) detachVolume(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	id := r.PathValue("volume_id")
	if !s.mayActOnVolume(w, r, c, id) {
		return
	}
	// The body is optional; when there is one, it must be an empty object.
	if r.ContentLength != 0 {
		var request struct{}
		if !decodeJSON(w, r, &request) {
			return
		}
	}
	volume, err := service.DetachVolume(r.Context(), id, c.mayTouchVolume,
		func(tx pgx.Tx, v db.Volume) error {
			return volumeAudit(r, c, map[string]any{"instance_id": v.InstanceID, "device": v.Device})(tx, v)
		})
	if err != nil {
		s.volumeRefused(w, r, c, id, err)
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"volume": volumeJSON(volume, true)})
}
