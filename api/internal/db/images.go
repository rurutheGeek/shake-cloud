package db

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5"
)

// Image is an image a user uploaded. The deployment's shared images live in
// site.json instead, so nothing here duplicates them.
type Image struct {
	ID        string
	AccountID string
	// OwnerUsername comes from the account row, so a listing can name the
	// uploader without a second query.
	OwnerUsername string
	Name          string
	Volume        string
	Format        string
	SizeBytes     int64
	CreatedAt     time.Time
}

const imageColumns = `im.image_id, im.account_id,
	coalesce((SELECT a.username FROM accounts a WHERE a.id = im.account_id), ''),
	im.name, im.volume, im.format, im.size_bytes, im.created_at`

func scanImage(row pgx.Row) (Image, error) {
	var i Image
	return i, noRows(row.Scan(&i.ID, &i.AccountID, &i.OwnerUsername, &i.Name, &i.Volume, &i.Format, &i.SizeBytes, &i.CreatedAt))
}

// InsertImage records an image whose file the store has already accepted.
func InsertImage(ctx context.Context, q Querier, i Image) (Image, error) {
	return scanImage(q.QueryRow(ctx, `INSERT INTO images AS im
		(image_id, account_id, name, volume, format, size_bytes) VALUES ($1, $2, $3, $4, $5, $6)
		RETURNING `+imageColumns, i.ID, i.AccountID, i.Name, i.Volume, i.Format, i.SizeBytes))
}

// ListImages returns every account's uploaded images, newest first. Everyone
// sees them, as with instances: people sharing a host need to see what is
// taking up the image store.
func ListImages(ctx context.Context, q Querier) ([]Image, error) {
	rows, err := q.Query(ctx, `SELECT `+imageColumns+` FROM images im ORDER BY im.created_at DESC, im.image_id`)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (Image, error) { return scanImage(row) })
}

func GetImage(ctx context.Context, q Querier, id string) (Image, error) {
	return scanImage(q.QueryRow(ctx, `SELECT `+imageColumns+` FROM images im WHERE im.image_id = $1`, id))
}

func DeleteImage(ctx context.Context, q Querier, id string) error {
	tag, err := q.Exec(ctx, `DELETE FROM images WHERE image_id = $1`, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

// CountImagesOf is how many images an account holds, for a quota check.
func CountImagesOf(ctx context.Context, q Querier, accountID string) (int, error) {
	var count int
	err := q.QueryRow(ctx, `SELECT count(*) FROM images WHERE account_id = $1`, accountID).Scan(&count)
	return count, err
}

// LaunchingFromImage counts instances still being created from an image. Their
// disk is copied from it, so deleting the image mid-launch would break them,
// while deleting it afterwards is harmless.
func LaunchingFromImage(ctx context.Context, q Querier, imageID string) (int, error) {
	var count int
	err := q.QueryRow(ctx, `SELECT count(*) FROM instances
		WHERE image_id = $1 AND state <> 'terminated' AND pending_action = 'launch'`, imageID).Scan(&count)
	return count, err
}
