package db

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5"
)

// ISO is installation media a user uploaded. It is attached as a CD-ROM, never
// copied to the root disk the way an image is.
type ISO struct {
	ID        string
	AccountID string
	// OwnerUsername comes from the account row, so a listing can name the
	// uploader without a second query.
	OwnerUsername string
	Name          string
	Volume        string
	SizeBytes     int64
	// OS is "windows" for a Windows installer and "" for a Linux one.
	OS        string
	CreatedAt time.Time
}

const isoColumns = `iso.iso_id, iso.account_id,
	coalesce((SELECT a.username FROM accounts a WHERE a.id = iso.account_id), ''),
	iso.name, iso.volume, iso.size_bytes, iso.os, iso.created_at`

func scanISO(row pgx.Row) (ISO, error) {
	var i ISO
	return i, noRows(row.Scan(&i.ID, &i.AccountID, &i.OwnerUsername, &i.Name, &i.Volume, &i.SizeBytes, &i.OS, &i.CreatedAt))
}

// InsertISO records an ISO whose file the store has already accepted.
func InsertISO(ctx context.Context, q Querier, i ISO) (ISO, error) {
	return scanISO(q.QueryRow(ctx, `INSERT INTO isos AS iso
		(iso_id, account_id, name, volume, size_bytes, os) VALUES ($1, $2, $3, $4, $5, $6)
		RETURNING `+isoColumns, i.ID, i.AccountID, i.Name, i.Volume, i.SizeBytes, i.OS))
}

// ListISOs returns every account's ISOs, newest first, as with images.
func ListISOs(ctx context.Context, q Querier) ([]ISO, error) {
	rows, err := q.Query(ctx, `SELECT `+isoColumns+` FROM isos iso ORDER BY iso.created_at DESC, iso.iso_id`)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (ISO, error) { return scanISO(row) })
}

func GetISO(ctx context.Context, q Querier, id string) (ISO, error) {
	return scanISO(q.QueryRow(ctx, `SELECT `+isoColumns+` FROM isos iso WHERE iso.iso_id = $1`, id))
}

func DeleteISO(ctx context.Context, q Querier, id string) error {
	tag, err := q.Exec(ctx, `DELETE FROM isos WHERE iso_id = $1`, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

// ISOInUse counts live instances that would lose their installation media if
// this ISO were deleted. A terminated instance no longer needs it.
func ISOInUse(ctx context.Context, q Querier, id string) (int, error) {
	var count int
	err := q.QueryRow(ctx, `SELECT count(*) FROM instances
		WHERE state <> 'terminated' AND (install_iso_id = $1 OR driver_iso_id = $1)`, id).Scan(&count)
	return count, err
}
