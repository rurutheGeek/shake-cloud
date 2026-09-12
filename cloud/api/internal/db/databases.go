package db

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5"
)

// A database appliance is one CloudNativePG Cluster, owned by one account.
// The id is also the cluster name, so it stays a DNS-safe label.
type Database struct {
	ID            string
	AccountID     string
	OwnerUsername string
	Name          string
	Namespace     string
	Engine        string
	EngineVersion string
	StorageGiB    int
	CreatedAt     time.Time
}

const databaseColumns = `d.database_id, d.account_id,
	coalesce((SELECT a.username FROM accounts a WHERE a.id = d.account_id), ''),
	d.name, d.namespace, d.engine, d.engine_version, d.storage_gib, d.created_at`

func scanDatabase(row pgx.Row) (Database, error) {
	var d Database
	return d, noRows(row.Scan(&d.ID, &d.AccountID, &d.OwnerUsername, &d.Name, &d.Namespace,
		&d.Engine, &d.EngineVersion, &d.StorageGiB, &d.CreatedAt))
}

func collectDatabases(rows pgx.Rows, err error) ([]Database, error) {
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (Database, error) { return scanDatabase(row) })
}

func InsertDatabase(ctx context.Context, q Querier, id, accountID, name, namespace, engine, engineVersion string, storageGiB int) (Database, error) {
	database, err := scanDatabase(q.QueryRow(ctx, `INSERT INTO databases AS d
		(database_id, account_id, name, namespace, engine, engine_version, storage_gib)
		VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING `+databaseColumns,
		id, accountID, name, namespace, engine, engineVersion, storageGiB))
	if isUniqueViolation(err, "databases_account_id_name_key") {
		return Database{}, ErrDuplicate
	}
	if isUniqueViolation(err, "databases_pkey") {
		return Database{}, ErrDuplicate
	}
	return database, err
}

func GetDatabase(ctx context.Context, q Querier, id string) (Database, error) {
	return scanDatabase(q.QueryRow(ctx, `SELECT `+databaseColumns+` FROM databases d WHERE d.database_id = $1`, id))
}

func GetDatabaseByName(ctx context.Context, q Querier, accountID, name string) (Database, error) {
	return scanDatabase(q.QueryRow(ctx, `SELECT `+databaseColumns+` FROM databases d
		WHERE d.account_id = $1 AND d.name = $2`, accountID, name))
}

func ListDatabases(ctx context.Context, q Querier, accountID string) ([]Database, error) {
	return collectDatabases(q.Query(ctx, `SELECT `+databaseColumns+` FROM databases d
		WHERE ($1::text = '' OR d.account_id = $1)
		ORDER BY d.created_at DESC, d.name`, accountID))
}

func DeleteDatabase(ctx context.Context, q Querier, id string) error {
	_, err := q.Exec(ctx, `DELETE FROM databases WHERE database_id = $1`, id)
	return err
}

func CountDatabases(ctx context.Context, q Querier, accountID string) (int, error) {
	var count int
	err := q.QueryRow(ctx, `SELECT count(*) FROM databases WHERE account_id = $1`, accountID).Scan(&count)
	return count, err
}
