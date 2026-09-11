package db

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
)

// ErrKeyNameTaken means the account already has a key pair under that name.
var ErrKeyNameTaken = errors.New("key name already in use")

type KeyPair struct {
	AccountID   string
	KeyName     string
	PublicKey   string
	Fingerprint string
	CreatedAt   time.Time
}

const keyPairColumns = `account_id, key_name, public_key, fingerprint, created_at`

func scanKeyPair(row pgx.Row) (KeyPair, error) {
	var k KeyPair
	return k, noRows(row.Scan(&k.AccountID, &k.KeyName, &k.PublicKey, &k.Fingerprint, &k.CreatedAt))
}

func InsertKeyPair(ctx context.Context, q Querier, k KeyPair) (KeyPair, error) {
	inserted, err := scanKeyPair(q.QueryRow(ctx, `INSERT INTO key_pairs
		(account_id, key_name, public_key, fingerprint) VALUES ($1, $2, $3, $4)
		RETURNING `+keyPairColumns, k.AccountID, k.KeyName, k.PublicKey, k.Fingerprint))
	if isUniqueViolation(err, "key_pairs_pkey") {
		return KeyPair{}, ErrKeyNameTaken
	}
	return inserted, err
}

// ListKeyPairs returns one account's keys, oldest first.
func ListKeyPairs(ctx context.Context, q Querier, accountID string) ([]KeyPair, error) {
	rows, err := q.Query(ctx, `SELECT `+keyPairColumns+` FROM key_pairs
		WHERE account_id = $1 ORDER BY created_at, key_name`, accountID)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (KeyPair, error) { return scanKeyPair(row) })
}

func GetKeyPair(ctx context.Context, q Querier, accountID, keyName string) (KeyPair, error) {
	return scanKeyPair(q.QueryRow(ctx, `SELECT `+keyPairColumns+` FROM key_pairs
		WHERE account_id = $1 AND key_name = $2`, accountID, keyName))
}

// DeleteKeyPair removes one of an account's keys, or reports ErrNotFound.
// Instances launched with it keep working: the key was copied into their seed
// image, not looked up at boot.
func DeleteKeyPair(ctx context.Context, q Querier, accountID, keyName string) error {
	tag, err := q.Exec(ctx, `DELETE FROM key_pairs WHERE account_id = $1 AND key_name = $2`, accountID, keyName)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}
