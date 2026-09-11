package db

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5"
)

// A bucket is an S3 bucket in Garage, owned by one account. Its name is the
// global alias and is unique across the cloud.
type Bucket struct {
	Name          string
	AccountID     string
	OwnerUsername string
	GarageID      string
	CreatedAt     time.Time
}

const bucketColumns = `b.bucket_name, b.account_id,
	coalesce((SELECT a.username FROM accounts a WHERE a.id = b.account_id), ''),
	b.garage_id, b.created_at`

func scanBucket(row pgx.Row) (Bucket, error) {
	var b Bucket
	return b, noRows(row.Scan(&b.Name, &b.AccountID, &b.OwnerUsername, &b.GarageID, &b.CreatedAt))
}

func collectBuckets(rows pgx.Rows, err error) ([]Bucket, error) {
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (Bucket, error) { return scanBucket(row) })
}

func InsertBucket(ctx context.Context, q Querier, name, accountID, garageID string) (Bucket, error) {
	bucket, err := scanBucket(q.QueryRow(ctx, `INSERT INTO buckets AS b (bucket_name, account_id, garage_id)
		VALUES ($1, $2, $3) RETURNING `+bucketColumns, name, accountID, garageID))
	if isUniqueViolation(err, "buckets_pkey") {
		return Bucket{}, ErrDuplicate
	}
	return bucket, err
}

func GetBucket(ctx context.Context, q Querier, name string) (Bucket, error) {
	return scanBucket(q.QueryRow(ctx, `SELECT `+bucketColumns+` FROM buckets b WHERE b.bucket_name = $1`, name))
}

func ListBuckets(ctx context.Context, q Querier, accountID string) ([]Bucket, error) {
	return collectBuckets(q.Query(ctx, `SELECT `+bucketColumns+` FROM buckets b
		WHERE ($1::text = '' OR b.account_id = $1)
		ORDER BY b.created_at DESC, b.bucket_name`, accountID))
}

func DeleteBucket(ctx context.Context, q Querier, name string) error {
	_, err := q.Exec(ctx, `DELETE FROM buckets WHERE bucket_name = $1`, name)
	return err
}

func CountBuckets(ctx context.Context, q Querier, accountID string) (int, error) {
	var count int
	err := q.QueryRow(ctx, `SELECT count(*) FROM buckets WHERE account_id = $1`, accountID).Scan(&count)
	return count, err
}

// An S3 access key. Only the id and name are kept; Garage never shows the
// secret again after creation.
type S3Key struct {
	KeyID     string
	AccountID string
	Name      string
	CreatedAt time.Time
}

const s3KeyColumns = `k.key_id, k.account_id, k.name, k.created_at`

func scanS3Key(row pgx.Row) (S3Key, error) {
	var k S3Key
	return k, noRows(row.Scan(&k.KeyID, &k.AccountID, &k.Name, &k.CreatedAt))
}

func collectS3Keys(rows pgx.Rows, err error) ([]S3Key, error) {
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (S3Key, error) { return scanS3Key(row) })
}

func InsertS3Key(ctx context.Context, q Querier, keyID, accountID, name string) (S3Key, error) {
	key, err := scanS3Key(q.QueryRow(ctx, `INSERT INTO s3_keys AS k (key_id, account_id, name)
		VALUES ($1, $2, $3) RETURNING `+s3KeyColumns, keyID, accountID, name))
	if isUniqueViolation(err, "s3_keys_account_id_name_key") {
		return S3Key{}, ErrDuplicate
	}
	return key, err
}

func GetS3Key(ctx context.Context, q Querier, keyID string) (S3Key, error) {
	return scanS3Key(q.QueryRow(ctx, `SELECT `+s3KeyColumns+` FROM s3_keys k WHERE k.key_id = $1`, keyID))
}

func GetS3KeyByName(ctx context.Context, q Querier, accountID, name string) (S3Key, error) {
	return scanS3Key(q.QueryRow(ctx, `SELECT `+s3KeyColumns+` FROM s3_keys k
		WHERE k.account_id = $1 AND k.name = $2`, accountID, name))
}

func ListS3Keys(ctx context.Context, q Querier, accountID string) ([]S3Key, error) {
	return collectS3Keys(q.Query(ctx, `SELECT `+s3KeyColumns+` FROM s3_keys k
		WHERE ($1::text = '' OR k.account_id = $1)
		ORDER BY k.created_at DESC, k.name`, accountID))
}

func DeleteS3Key(ctx context.Context, q Querier, keyID string) error {
	_, err := q.Exec(ctx, `DELETE FROM s3_keys WHERE key_id = $1`, keyID)
	return err
}

func CountS3Keys(ctx context.Context, q Querier, accountID string) (int, error) {
	var count int
	err := q.QueryRow(ctx, `SELECT count(*) FROM s3_keys WHERE account_id = $1`, accountID).Scan(&count)
	return count, err
}

// BucketPermission is a key's rights on one bucket.
type BucketPermission struct {
	KeyID   string
	KeyName string
	Read    bool
	Write   bool
	Owner   bool
}

func SetBucketPermission(ctx context.Context, q Querier, bucketName, keyID string, read, write, owner bool) error {
	_, err := q.Exec(ctx, `INSERT INTO bucket_keys (bucket_name, key_id, can_read, can_write, is_owner)
		VALUES ($1, $2, $3, $4, $5)
		ON CONFLICT (bucket_name, key_id)
		DO UPDATE SET can_read = $3, can_write = $4, is_owner = $5`,
		bucketName, keyID, read, write, owner)
	return err
}

func DeleteBucketPermission(ctx context.Context, q Querier, bucketName, keyID string) error {
	_, err := q.Exec(ctx, `DELETE FROM bucket_keys WHERE bucket_name = $1 AND key_id = $2`, bucketName, keyID)
	return err
}

func BucketPermissions(ctx context.Context, q Querier, bucketName string) ([]BucketPermission, error) {
	rows, err := q.Query(ctx, `SELECT m.key_id, k.name, m.can_read, m.can_write, m.is_owner
		FROM bucket_keys m JOIN s3_keys k ON k.key_id = m.key_id
		WHERE m.bucket_name = $1 ORDER BY k.name`, bucketName)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (BucketPermission, error) {
		var p BucketPermission
		return p, row.Scan(&p.KeyID, &p.KeyName, &p.Read, &p.Write, &p.Owner)
	})
}
