package compute

import (
	"context"
	"errors"
	"net/http"
	"regexp"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/garage"
)

// Buckets and S3 access keys. Garage is the object store; the cloud API keeps
// the account that owns each bucket and key, and enforces who may touch them.
// The S3 data itself never passes through the API.

// An S3 bucket name: 3-63 characters, lower case, digits, dots and hyphens.
var bucketName = regexp.MustCompile(`^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$`)

// Limits kept in code, like the security group limits. 0 in limits.yaml is not
// used for these: they protect Garage from one account making unlimited keys.
const (
	maxBucketsPerAccount = 20
	maxS3KeysPerAccount  = 10
)

// BucketStore is Garage's administration API as the service uses it.
type BucketStore interface {
	CreateBucket(ctx context.Context, name string) (garage.BucketInfo, error)
	ListBuckets(ctx context.Context) ([]garage.Bucket, error)
	BucketInfo(ctx context.Context, globalAlias string) (garage.BucketInfo, error)
	DeleteBucket(ctx context.Context, id string) error
	CreateKey(ctx context.Context, name string) (garage.KeyInfo, error)
	ListKeys(ctx context.Context) ([]garage.KeyListItem, error)
	GetKeyInfo(ctx context.Context, id string) (garage.KeyInfo, error)
	DeleteKey(ctx context.Context, id string) error
	AllowBucketKey(ctx context.Context, bucketID, keyID string, permissions garage.Permissions) error
	DenyBucketKey(ctx context.Context, bucketID, keyID string, permissions garage.Permissions) error
}

// BucketStatus is a bucket with the keys allowed on it, ready for the handler.
type BucketStatus struct {
	Bucket db.Bucket
	Keys   []db.BucketPermission
	// Objects and Bytes come from Garage; they are best-effort, so a Garage
	// that does not answer does not stop the bucket from being listed.
	Objects int64
	Bytes   int64
}

func bucketNotFound(name string) error {
	return refuse(http.StatusNotFound, "NoSuchBucket", "bucket %s does not exist", name)
}

func keyNotFound(id string) error {
	return refuse(http.StatusNotFound, "NoSuchKey", "S3 key %s does not exist", id)
}

// storageReady refuses when Garage is not configured on this deployment.
func (s *Service) storageReady() error {
	if s.Garage == nil {
		return refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "object storage is not configured on this deployment")
	}
	return nil
}

// CreateBucket creates an S3 bucket owned by accountID. Repeating it with the
// same name returns the existing bucket, as S3 does for the owner.
func (s *Service) CreateBucket(ctx context.Context, accountID, name string, audit func(pgx.Tx, db.Bucket) error) (db.Bucket, bool, error) {
	bad := func(format string, args ...any) error {
		return refuse(http.StatusBadRequest, "InvalidBucketName", format, args...)
	}
	switch {
	case len(name) < 3 || len(name) > 63:
		return db.Bucket{}, false, bad("a bucket name is 3-63 characters")
	case !bucketName.MatchString(name):
		return db.Bucket{}, false, bad("a bucket name uses lower case letters, digits, dots and hyphens, and starts and ends with a letter or digit")
	case strings.Contains(name, ".."):
		return db.Bucket{}, false, bad("a bucket name must not contain two dots in a row")
	}
	if err := s.storageReady(); err != nil {
		return db.Bucket{}, false, err
	}

	var bucket db.Bucket
	created := false
	err := pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		if existing, err := db.GetBucket(ctx, tx, name); err == nil {
			if existing.AccountID != accountID {
				return refuse(http.StatusConflict, "BucketAlreadyExists", "bucket %s already belongs to another account", name)
			}
			bucket = existing
			return nil
		} else if !errors.Is(err, db.ErrNotFound) {
			return err
		}
		count, err := db.CountBuckets(ctx, tx, accountID)
		if err != nil {
			return err
		}
		if count >= maxBucketsPerAccount {
			return refuse(http.StatusConflict, "BucketLimitExceeded", "an account may hold %d buckets", maxBucketsPerAccount)
		}
		info, err := s.Garage.CreateBucket(ctx, name)
		if err != nil {
			return refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "the object store could not create the bucket: %v", err)
		}
		bucket, err = db.InsertBucket(ctx, tx, name, accountID, info.ID)
		if errors.Is(err, db.ErrDuplicate) {
			// Another request won the race; remove ours and use theirs.
			_ = s.Garage.DeleteBucket(ctx, info.ID)
			existing, getErr := db.GetBucket(ctx, tx, name)
			if getErr != nil {
				return getErr
			}
			if existing.AccountID != accountID {
				return refuse(http.StatusConflict, "BucketAlreadyExists", "bucket %s already belongs to another account", name)
			}
			bucket = existing
			return nil
		}
		if err != nil {
			_ = s.Garage.DeleteBucket(ctx, info.ID)
			return err
		}
		created = true
		if audit != nil {
			return audit(tx, bucket)
		}
		return nil
	})
	return bucket, created, err
}

// ListBuckets returns an account's buckets (every account's when accountID is
// empty), with the keys allowed on each.
func (s *Service) ListBuckets(ctx context.Context, accountID string) ([]BucketStatus, error) {
	buckets, err := db.ListBuckets(ctx, s.Pool, accountID)
	if err != nil {
		return nil, err
	}
	statuses := make([]BucketStatus, 0, len(buckets))
	for _, bucket := range buckets {
		keys, err := db.BucketPermissions(ctx, s.Pool, bucket.Name)
		if err != nil {
			return nil, err
		}
		status := BucketStatus{Bucket: bucket, Keys: keys}
		if s.Garage != nil {
			if info, err := s.Garage.BucketInfo(ctx, bucket.Name); err == nil {
				status.Objects, status.Bytes = info.Objects, info.Bytes
			}
		}
		statuses = append(statuses, status)
	}
	return statuses, nil
}

// GetBucket reads one bucket and its keys.
func (s *Service) GetBucket(ctx context.Context, name string, authorize func(db.Bucket) bool) (BucketStatus, error) {
	bucket, err := db.GetBucket(ctx, s.Pool, name)
	if errors.Is(err, db.ErrNotFound) || (err == nil && !authorize(bucket)) {
		return BucketStatus{}, bucketNotFound(name)
	}
	if err != nil {
		return BucketStatus{}, err
	}
	keys, err := db.BucketPermissions(ctx, s.Pool, name)
	if err != nil {
		return BucketStatus{}, err
	}
	status := BucketStatus{Bucket: bucket, Keys: keys}
	if s.Garage != nil {
		if info, err := s.Garage.BucketInfo(ctx, name); err == nil {
			status.Objects, status.Bytes = info.Objects, info.Bytes
		}
	}
	return status, nil
}

// DeleteBucket deletes an empty bucket. Garage refuses a bucket that still has
// objects, and that refusal is passed through.
func (s *Service) DeleteBucket(ctx context.Context, name string, authorize func(db.Bucket) bool, audit func(pgx.Tx, db.Bucket) error) error {
	if err := s.storageReady(); err != nil {
		return err
	}
	return pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		bucket, err := db.GetBucket(ctx, tx, name)
		if errors.Is(err, db.ErrNotFound) || (err == nil && !authorize(bucket)) {
			return bucketNotFound(name)
		}
		if err != nil {
			return err
		}
		if err := s.Garage.DeleteBucket(ctx, bucket.GarageID); err != nil {
			var garageErr *garage.Error
			if errors.As(err, &garageErr) && garageErr.NotFound() {
				// Already gone in Garage; finish the clean-up here.
			} else {
				return refuse(http.StatusConflict, "BucketNotEmpty", "the object store would not delete bucket %s (it may still hold objects): %v", name, err)
			}
		}
		if err := db.DeleteBucket(ctx, tx, name); err != nil {
			return err
		}
		if audit != nil {
			return audit(tx, bucket)
		}
		return nil
	})
}

// CreateS3Key makes an S3 access key for an account and returns the secret,
// which Garage shows only this once.
func (s *Service) CreateS3Key(ctx context.Context, accountID, name string, audit func(pgx.Tx, db.S3Key) error) (db.S3Key, string, error) {
	bad := func(format string, args ...any) error {
		return refuse(http.StatusBadRequest, "InvalidParameterValue", format, args...)
	}
	switch {
	case name == "":
		return db.S3Key{}, "", bad("a key name is required")
	case !groupName.MatchString(name):
		return db.S3Key{}, "", bad("a key name is 1-64 characters of letters, digits, space or . _ : @ -")
	}
	if err := s.storageReady(); err != nil {
		return db.S3Key{}, "", err
	}
	var key db.S3Key
	var secret string
	err := pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		if existing, err := db.GetS3KeyByName(ctx, tx, accountID, name); err == nil {
			key = existing
			return nil
		} else if !errors.Is(err, db.ErrNotFound) {
			return err
		}
		count, err := db.CountS3Keys(ctx, tx, accountID)
		if err != nil {
			return err
		}
		if count >= maxS3KeysPerAccount {
			return refuse(http.StatusConflict, "S3KeyLimitExceeded", "an account may hold %d S3 keys", maxS3KeysPerAccount)
		}
		info, err := s.Garage.CreateKey(ctx, name)
		if err != nil {
			return refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "the object store could not create the key: %v", err)
		}
		key, err = db.InsertS3Key(ctx, tx, info.AccessKeyID, accountID, name)
		if err != nil {
			_ = s.Garage.DeleteKey(ctx, info.AccessKeyID)
			return err
		}
		secret = info.SecretAccessKey
		if audit != nil {
			return audit(tx, key)
		}
		return nil
	})
	return key, secret, err
}

func (s *Service) ListS3Keys(ctx context.Context, accountID string) ([]db.S3Key, error) {
	return db.ListS3Keys(ctx, s.Pool, accountID)
}

func (s *Service) GetS3Key(ctx context.Context, keyID string, authorize func(db.S3Key) bool) (db.S3Key, error) {
	key, err := db.GetS3Key(ctx, s.Pool, keyID)
	if errors.Is(err, db.ErrNotFound) || (err == nil && !authorize(key)) {
		return db.S3Key{}, keyNotFound(keyID)
	}
	return key, err
}

// DeleteS3Key revokes a key. Garage removes its permissions on every bucket;
// the ledger rows go with it.
func (s *Service) DeleteS3Key(ctx context.Context, keyID string, authorize func(db.S3Key) bool, audit func(pgx.Tx, db.S3Key) error) error {
	if err := s.storageReady(); err != nil {
		return err
	}
	return pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		key, err := db.GetS3Key(ctx, tx, keyID)
		if errors.Is(err, db.ErrNotFound) || (err == nil && !authorize(key)) {
			return keyNotFound(keyID)
		}
		if err != nil {
			return err
		}
		if err := s.Garage.DeleteKey(ctx, keyID); err != nil {
			var garageErr *garage.Error
			if !errors.As(err, &garageErr) || !garageErr.NotFound() {
				return refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "the object store could not delete the key: %v", err)
			}
		}
		if err := db.DeleteS3Key(ctx, tx, keyID); err != nil {
			return err
		}
		if audit != nil {
			return audit(tx, key)
		}
		return nil
	})
}

// SetBucketPermission grants a key read/write/owner on a bucket. The key must
// belong to the same account as the bucket.
func (s *Service) SetBucketPermission(ctx context.Context, name, keyID string, read, write, owner bool, authorize func(db.Bucket) bool, audit func(pgx.Tx, db.Bucket, db.S3Key) error) (BucketStatus, error) {
	if err := s.storageReady(); err != nil {
		return BucketStatus{}, err
	}
	var status BucketStatus
	err := pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		bucket, err := db.GetBucket(ctx, tx, name)
		if errors.Is(err, db.ErrNotFound) || (err == nil && !authorize(bucket)) {
			return bucketNotFound(name)
		}
		if err != nil {
			return err
		}
		key, err := db.GetS3Key(ctx, tx, keyID)
		if errors.Is(err, db.ErrNotFound) || (err == nil && key.AccountID != bucket.AccountID) {
			return keyNotFound(keyID)
		}
		if err != nil {
			return err
		}
		if err := s.Garage.AllowBucketKey(ctx, bucket.GarageID, keyID, garage.Permissions{Read: read, Write: write, Owner: owner}); err != nil {
			return refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "the object store could not grant the permission: %v", err)
		}
		if err := db.SetBucketPermission(ctx, tx, name, keyID, read, write, owner); err != nil {
			return err
		}
		keys, err := db.BucketPermissions(ctx, tx, name)
		if err != nil {
			return err
		}
		status = BucketStatus{Bucket: bucket, Keys: keys}
		if audit != nil {
			return audit(tx, bucket, key)
		}
		return nil
	})
	return status, err
}

// RevokeBucketPermission removes a key's rights on a bucket.
func (s *Service) RevokeBucketPermission(ctx context.Context, name, keyID string, authorize func(db.Bucket) bool, audit func(pgx.Tx, db.Bucket, db.S3Key) error) (BucketStatus, error) {
	if err := s.storageReady(); err != nil {
		return BucketStatus{}, err
	}
	var status BucketStatus
	err := pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		bucket, err := db.GetBucket(ctx, tx, name)
		if errors.Is(err, db.ErrNotFound) || (err == nil && !authorize(bucket)) {
			return bucketNotFound(name)
		}
		if err != nil {
			return err
		}
		key, err := db.GetS3Key(ctx, tx, keyID)
		if err != nil && !errors.Is(err, db.ErrNotFound) {
			return err
		}
		// Deny all three, so a permission set outside the ledger is cleared too.
		if err := s.Garage.DenyBucketKey(ctx, bucket.GarageID, keyID, garage.Permissions{Read: true, Write: true, Owner: true}); err != nil {
			var garageErr *garage.Error
			if !errors.As(err, &garageErr) || !garageErr.NotFound() {
				return refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "the object store could not revoke the permission: %v", err)
			}
		}
		if err := db.DeleteBucketPermission(ctx, tx, name, keyID); err != nil {
			return err
		}
		keys, err := db.BucketPermissions(ctx, tx, name)
		if err != nil {
			return err
		}
		status = BucketStatus{Bucket: bucket, Keys: keys}
		if audit != nil {
			return audit(tx, bucket, key)
		}
		return nil
	})
	return status, err
}
