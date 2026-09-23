package db

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/accesskey"
)

// Key statuses. Active and Inactive are IAM's words; IAM keys never expire,
// so Expired is ours.
const (
	KeyActive   = "Active"
	KeyInactive = "Inactive"
	KeyExpired  = "Expired"
)

// Key scopes. A ReadOnly key may call only operations that do not change
// state; a ReadWrite key may call all of them.
const (
	KeyScopeReadOnly  = "ReadOnly"
	KeyScopeReadWrite = "ReadWrite"
)

type AccessKey struct {
	ID          string
	AccountID   string
	Description string
	Scope       string
	CreatedAt   time.Time
	ExpiresAt   *time.Time
	RevokedAt   *time.Time
	LastUsedAt  *time.Time
}

func (k AccessKey) Status(now time.Time) string {
	switch {
	case k.RevokedAt != nil:
		return KeyInactive
	case k.ExpiresAt != nil && !now.Before(*k.ExpiresAt):
		return KeyExpired
	default:
		return KeyActive
	}
}

// Credential is what authentication needs: the key, its stored hash and owner.
type Credential struct {
	Key          AccessKey
	SecretSHA256 []byte
	Account      Account
}

const keyColumns = `k.access_key_id, k.account_id, k.description, k.scope, k.created_at, k.expires_at, k.revoked_at, k.last_used_at`

func keyFields(k *AccessKey) []any {
	return []any{&k.ID, &k.AccountID, &k.Description, &k.Scope, &k.CreatedAt, &k.ExpiresAt, &k.RevokedAt, &k.LastUsedAt}
}

func scanKey(row pgx.Row) (AccessKey, error) {
	var k AccessKey
	return k, noRows(row.Scan(keyFields(&k)...))
}

func InsertAccessKey(ctx context.Context, q Querier, accountID string, token accesskey.Token, description, scope string, expiresAt *time.Time) (AccessKey, error) {
	return scanKey(q.QueryRow(ctx, `INSERT INTO access_keys AS k
		(access_key_id, account_id, secret_sha256, description, scope, expires_at)
		VALUES ($1, $2, $3, $4, $5, $6) RETURNING `+keyColumns,
		token.ID, accountID, token.Hash(), description, scope, expiresAt))
}

func LookupAccessKey(ctx context.Context, q Querier, id string) (Credential, error) {
	var c Credential
	fields := append(keyFields(&c.Key), &c.SecretSHA256)
	fields = append(fields, accountFields(&c.Account)...)
	err := q.QueryRow(ctx, `SELECT `+keyColumns+`, k.secret_sha256, `+accountColumns+`
		FROM access_keys k JOIN accounts a ON a.id = k.account_id
		WHERE k.access_key_id = $1`, id).Scan(fields...)
	return c, noRows(err)
}

// TouchAccessKey records use at most once a minute, so a busy Terraform run
// does not write a row per request.
func TouchAccessKey(ctx context.Context, q Querier, id string) error {
	_, err := q.Exec(ctx, `UPDATE access_keys SET last_used_at = now()
		WHERE access_key_id = $1 AND (last_used_at IS NULL OR last_used_at < now() - interval '1 minute')`, id)
	return err
}

// ListAccessKeys returns the account's keys that have not been deleted,
// including expired ones so their owner can see why a key stopped working.
func ListAccessKeys(ctx context.Context, q Querier, accountID string) ([]AccessKey, error) {
	rows, err := q.Query(ctx, `SELECT `+keyColumns+` FROM access_keys k
		WHERE k.account_id = $1 AND k.revoked_at IS NULL
		ORDER BY k.created_at, k.access_key_id`, accountID)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (AccessKey, error) { return scanKey(row) })
}

func CountActiveAccessKeys(ctx context.Context, q Querier, accountID string) (int, error) {
	var n int
	err := q.QueryRow(ctx, `SELECT count(*) FROM access_keys
		WHERE account_id = $1 AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now())`, accountID).Scan(&n)
	return n, err
}

// RevokeAccessKey returns ErrNotFound when the key does not exist or is already revoked.
func RevokeAccessKey(ctx context.Context, q Querier, id string) (AccessKey, error) {
	return scanKey(q.QueryRow(ctx, `UPDATE access_keys AS k SET revoked_at = now()
		WHERE k.access_key_id = $1 AND k.revoked_at IS NULL RETURNING `+keyColumns, id))
}

// RevokeAccountKeysExcept revokes every live key of the account but keep, and
// returns the revoked IDs. keep may be empty.
func RevokeAccountKeysExcept(ctx context.Context, q Querier, accountID, keep string) ([]string, error) {
	rows, err := q.Query(ctx, `UPDATE access_keys SET revoked_at = now()
		WHERE account_id = $1 AND access_key_id <> $2 AND revoked_at IS NULL
		RETURNING access_key_id`, accountID, keep)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, pgx.RowTo[string])
}
