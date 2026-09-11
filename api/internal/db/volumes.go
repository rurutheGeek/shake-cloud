package db

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5"
)

// Volume states follow EC2's lifecycle.
const (
	VolumeCreating  = "creating"
	VolumeAvailable = "available"
	VolumeInUse     = "in-use"
	VolumeDeleting  = "deleting"
	VolumeDeleted   = "deleted"
	VolumeError     = "error"
)

// Attachment states, also EC2's. A volume that is not attached has none.
const (
	AttachmentAttaching = "attaching"
	AttachmentAttached  = "attached"
	AttachmentDetaching = "detaching"
)

// Volume actions the worker carries out.
const (
	VolumeActionCreate = "create"
	VolumeActionAttach = "attach"
	VolumeActionDetach = "detach"
	VolumeActionResize = "resize"
	VolumeActionDelete = "delete"
)

type Volume struct {
	ID        string
	AccountID string
	// OwnerUsername comes from the account row, as for instances.
	OwnerUsername string
	ClientToken   string
	RequestSHA256 []byte
	// SizeGiB is the size asked for. During a resize the disk is still smaller.
	SizeGiB int
	Tags    map[string]string
	State   string
	// InstanceID, Device and AttachmentState are set from the moment an attach
	// is requested until the disk is back on the holder.
	InstanceID      string
	Device          string
	AttachmentState string
	PendingAction   string
	StateReason     string
	LastError       string
	Attempts        int
	NextAttemptAt   time.Time
	Location        Location
	CreatedAt       time.Time
	DeletedAt       *time.Time
	UpdatedAt       time.Time
}

// Location is where a volume's disk sits in Proxmox: the VM whose config holds
// it, under which key, and its volume ID. MoveVMID and MoveKey are the
// destination of a move_disk in progress, written before the move starts.
type Location struct {
	VMID      *int
	ConfigKey string
	VolID     string
	MoveVMID  *int
	MoveKey   string
}

const volumeColumns = `v.volume_id, v.account_id,
	coalesce((SELECT a.username FROM accounts a WHERE a.id = v.account_id), ''),
	coalesce(v.client_token, ''), v.request_sha256, v.size_gib, v.tags, v.state,
	coalesce(v.instance_id, ''), coalesce(v.device, ''), coalesce(v.attachment_state, ''),
	coalesce(v.pending_action, ''), v.state_reason, v.last_error, v.attempts, v.next_attempt_at,
	v.vmid, coalesce(v.config_key, ''), coalesce(v.volid, ''), v.move_vmid, coalesce(v.move_key, ''),
	v.created_at, v.deleted_at, v.updated_at`

func scanVolume(row pgx.Row) (Volume, error) {
	var v Volume
	err := row.Scan(&v.ID, &v.AccountID, &v.OwnerUsername, &v.ClientToken, &v.RequestSHA256, &v.SizeGiB, &v.Tags, &v.State,
		&v.InstanceID, &v.Device, &v.AttachmentState,
		&v.PendingAction, &v.StateReason, &v.LastError, &v.Attempts, &v.NextAttemptAt,
		&v.Location.VMID, &v.Location.ConfigKey, &v.Location.VolID, &v.Location.MoveVMID, &v.Location.MoveKey,
		&v.CreatedAt, &v.DeletedAt, &v.UpdatedAt)
	return v, noRows(err)
}

func collectVolumes(rows pgx.Rows, err error) ([]Volume, error) {
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (Volume, error) { return scanVolume(row) })
}

// InsertVolume records a new volume with its disk still to be created.
func InsertVolume(ctx context.Context, q Querier, v Volume) (Volume, error) {
	if v.Tags == nil {
		v.Tags = map[string]string{}
	}
	return scanVolume(q.QueryRow(ctx, `INSERT INTO volumes AS v
		(volume_id, account_id, client_token, request_sha256, size_gib, tags, state, pending_action)
		VALUES ($1, $2, nullif($3::text, ''), $4, $5, $6, 'creating', 'create')
		RETURNING `+volumeColumns,
		v.ID, v.AccountID, v.ClientToken, v.RequestSHA256, v.SizeGiB, v.Tags))
}

func GetVolume(ctx context.Context, q Querier, id string) (Volume, error) {
	return scanVolume(q.QueryRow(ctx, `SELECT `+volumeColumns+` FROM volumes v WHERE v.volume_id = $1`, id))
}

// LockVolume reads a volume and holds its row until the transaction ends.
func LockVolume(ctx context.Context, q Querier, id string) (Volume, error) {
	return scanVolume(q.QueryRow(ctx, `SELECT `+volumeColumns+` FROM volumes v WHERE v.volume_id = $1 FOR UPDATE`, id))
}

func VolumeByClientToken(ctx context.Context, q Querier, accountID, token string) (Volume, error) {
	return scanVolume(q.QueryRow(ctx, `SELECT `+volumeColumns+` FROM volumes v
		WHERE v.account_id = $1 AND v.client_token = $2`, accountID, token))
}

// VolumeByVolID finds the live volume whose disk has this Proxmox volume ID.
func VolumeByVolID(ctx context.Context, q Querier, volid string) (Volume, error) {
	return scanVolume(q.QueryRow(ctx, `SELECT `+volumeColumns+` FROM volumes v
		WHERE v.volid = $1 AND v.state <> 'deleted'`, volid))
}

// ListVolumes returns every account's volumes, newest first. Deleted ones stay
// visible for an hour, like terminated instances.
func ListVolumes(ctx context.Context, q Querier) ([]Volume, error) {
	return collectVolumes(q.Query(ctx, `SELECT `+volumeColumns+` FROM volumes v
		WHERE v.state <> 'deleted' OR v.deleted_at > now() - interval '1 hour'
		ORDER BY v.created_at DESC, v.volume_id`))
}

// VolumesOfInstance lists the volumes attached, or being attached or detached,
// to an instance.
func VolumesOfInstance(ctx context.Context, q Querier, instanceID string) ([]Volume, error) {
	return collectVolumes(q.Query(ctx, `SELECT `+volumeColumns+` FROM volumes v
		WHERE v.instance_id = $1 ORDER BY v.device`, instanceID))
}

// VolumesOnVM lists the live volumes whose disk is on vmid, or is being moved
// there. This is what must be moved away before that VM is deleted.
func VolumesOnVM(ctx context.Context, q Querier, vmid int) ([]Volume, error) {
	return collectVolumes(q.Query(ctx, `SELECT `+volumeColumns+` FROM volumes v
		WHERE v.state <> 'deleted' AND (v.vmid = $1 OR v.move_vmid = $1)
		ORDER BY v.volume_id`, vmid))
}

// LiveVolumeCount is how many volumes exist across the cloud. Each one may
// need an unused slot on the holder, and Proxmox has 256 of those.
func LiveVolumeCount(ctx context.Context, q Querier) (int, error) {
	var count int
	err := q.QueryRow(ctx, `SELECT count(*) FROM volumes WHERE state <> 'deleted'`).Scan(&count)
	return count, err
}

// ClaimVolumeWork leases the next volume with work due, or returns ErrNotFound.
func ClaimVolumeWork(ctx context.Context, q Querier, lease time.Duration) (Volume, error) {
	return scanVolume(q.QueryRow(ctx, `UPDATE volumes AS v SET lease_until = now() + make_interval(secs => $1)
		WHERE v.volume_id = (
			SELECT volume_id FROM volumes
			WHERE pending_action IS NOT NULL AND next_attempt_at <= now()
			  AND (lease_until IS NULL OR lease_until < now())
			ORDER BY next_attempt_at, volume_id
			LIMIT 1 FOR UPDATE SKIP LOCKED)
		RETURNING `+volumeColumns, lease.Seconds()))
}

// RecordLocation writes where the disk is, as soon as a step has moved it.
func RecordLocation(ctx context.Context, q Querier, id string, l Location) error {
	_, err := q.Exec(ctx, `UPDATE volumes SET vmid = $2, config_key = nullif($3::text, ''), volid = nullif($4::text, ''),
		move_vmid = $5, move_key = nullif($6::text, ''), updated_at = now()
		WHERE volume_id = $1`, id, l.VMID, l.ConfigKey, l.VolID, l.MoveVMID, l.MoveKey)
	return err
}

// RequestAttach records an attach. The volume stays available until the disk
// is plugged in, as in EC2. Callers hold the row and have checked its state.
func RequestAttach(ctx context.Context, q Querier, id, instanceID, device string) (Volume, error) {
	return scanVolume(q.QueryRow(ctx, `UPDATE volumes AS v SET instance_id = $2, device = $3,
		attachment_state = 'attaching', pending_action = 'attach', state_reason = '',
		attempts = 0, last_error = '', next_attempt_at = now(), updated_at = now()
		WHERE v.volume_id = $1 RETURNING `+volumeColumns, id, instanceID, device))
}

// RequestDetach records a detach; the volume is in-use until the disk is off.
func RequestDetach(ctx context.Context, q Querier, id string) (Volume, error) {
	return scanVolume(q.QueryRow(ctx, `UPDATE volumes AS v SET attachment_state = 'detaching',
		pending_action = 'detach', state_reason = '',
		attempts = 0, last_error = '', next_attempt_at = now(), updated_at = now()
		WHERE v.volume_id = $1 RETURNING `+volumeColumns, id))
}

// RequestResize records a new size. The ledger takes it at once, so quota
// checks made meanwhile already count the larger disk.
func RequestResize(ctx context.Context, q Querier, id string, sizeGiB int) (Volume, error) {
	return scanVolume(q.QueryRow(ctx, `UPDATE volumes AS v SET size_gib = $2, pending_action = 'resize', state_reason = '',
		attempts = 0, last_error = '', next_attempt_at = now(), updated_at = now()
		WHERE v.volume_id = $1 RETURNING `+volumeColumns, id, sizeGiB))
}

func RequestDelete(ctx context.Context, q Querier, id string) (Volume, error) {
	return scanVolume(q.QueryRow(ctx, `UPDATE volumes AS v SET state = 'deleting', pending_action = 'delete', state_reason = '',
		attempts = 0, last_error = '', next_attempt_at = now(), updated_at = now()
		WHERE v.volume_id = $1 RETURNING `+volumeColumns, id))
}

// FinishVolumeAction completes action and moves the volume to the state that
// action ends in. It does nothing when the action was replaced meanwhile, and
// reports whether it applied.
func FinishVolumeAction(ctx context.Context, q Querier, id, action string) (bool, error) {
	tag, err := q.Exec(ctx, `UPDATE volumes SET pending_action = NULL, attempts = 0, last_error = '',
		lease_until = NULL, state_reason = '', updated_at = now(),
		state = CASE $2::text WHEN 'create' THEN 'available' WHEN 'attach' THEN 'in-use'
			WHEN 'detach' THEN 'available' WHEN 'delete' THEN 'deleted' ELSE state END,
		attachment_state = CASE $2::text WHEN 'attach' THEN 'attached' WHEN 'detach' THEN NULL ELSE attachment_state END,
		instance_id = CASE WHEN $2::text = 'detach' THEN NULL ELSE instance_id END,
		device = CASE WHEN $2::text = 'detach' THEN NULL ELSE device END,
		deleted_at = CASE WHEN $2::text = 'delete' THEN now() ELSE deleted_at END
		WHERE volume_id = $1 AND pending_action = $2::text`, id, action)
	if err != nil {
		return false, err
	}
	if tag.RowsAffected() == 0 {
		return false, ReleaseVolumeLease(ctx, q, id)
	}
	return true, nil
}

// RetryVolumeLater records a failed attempt and schedules the next one.
func RetryVolumeLater(ctx context.Context, q Querier, id, action, lastError string, next time.Time) error {
	_, err := q.Exec(ctx, `UPDATE volumes SET attempts = attempts + 1, last_error = $3, next_attempt_at = $4,
		lease_until = NULL, updated_at = now()
		WHERE volume_id = $1 AND pending_action = $2`, id, action, lastError, next)
	return err
}

// GiveUpCreate leaves a volume whose disk could not be made in the error
// state. Deleting it removes whatever the attempts left behind.
func GiveUpCreate(ctx context.Context, q Querier, id, reason string) error {
	_, err := q.Exec(ctx, `UPDATE volumes SET state = 'error', pending_action = NULL, state_reason = $2,
		attempts = 0, lease_until = NULL, updated_at = now()
		WHERE volume_id = $1 AND pending_action = 'create'`, id, reason)
	return err
}

// GiveUpAttach turns an attach that cannot succeed into a detach, which puts
// the disk back on the holder wherever the attempts left it.
func GiveUpAttach(ctx context.Context, q Querier, id, reason string) error {
	_, err := q.Exec(ctx, `UPDATE volumes SET attachment_state = 'detaching', pending_action = 'detach', state_reason = $2,
		attempts = 0, next_attempt_at = now(), lease_until = NULL, updated_at = now()
		WHERE volume_id = $1 AND pending_action = 'attach'`, id, reason)
	return err
}

// GiveUpResize puts the ledger back to the size the disk actually has.
func GiveUpResize(ctx context.Context, q Querier, id string, actualGiB int, reason string) error {
	_, err := q.Exec(ctx, `UPDATE volumes SET size_gib = $2, pending_action = NULL, state_reason = $3,
		attempts = 0, lease_until = NULL, updated_at = now()
		WHERE volume_id = $1 AND pending_action = 'resize'`, id, actualGiB, reason)
	return err
}

// ReturnToHolder records that terminating an instance moved this volume's disk
// back to the holder. An attach or detach in flight is over: the instance is
// gone. A resize stays pending and is carried out on the holder.
func ReturnToHolder(ctx context.Context, q Querier, id string, l Location, reason string) error {
	_, err := q.Exec(ctx, `UPDATE volumes SET instance_id = NULL, device = NULL, attachment_state = NULL,
		state = CASE WHEN state = 'in-use' THEN 'available' ELSE state END,
		pending_action = CASE WHEN pending_action IN ('attach', 'detach') THEN NULL ELSE pending_action END,
		attempts = CASE WHEN pending_action IN ('attach', 'detach') THEN 0 ELSE attempts END,
		vmid = $2, config_key = nullif($3::text, ''), volid = nullif($4::text, ''), move_vmid = NULL, move_key = NULL,
		state_reason = $5, updated_at = now()
		WHERE volume_id = $1`, id, l.VMID, l.ConfigKey, l.VolID, reason)
	return err
}

func ReleaseVolumeLease(ctx context.Context, q Querier, id string) error {
	_, err := q.Exec(ctx, `UPDATE volumes SET lease_until = NULL WHERE volume_id = $1`, id)
	return err
}
