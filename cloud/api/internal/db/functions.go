package db

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5"
)

// A function is one Knative Service, owned by one account. The id is also the
// service name, so it stays a DNS-safe label.
type Function struct {
	ID            string
	AccountID     string
	OwnerUsername string
	Name          string
	Namespace     string
	Image         string
	CreatedAt     time.Time
}

const functionColumns = `f.function_id, f.account_id,
	coalesce((SELECT a.username FROM accounts a WHERE a.id = f.account_id), ''),
	f.name, f.namespace, f.image, f.created_at`

func scanFunction(row pgx.Row) (Function, error) {
	var f Function
	return f, noRows(row.Scan(&f.ID, &f.AccountID, &f.OwnerUsername, &f.Name, &f.Namespace, &f.Image, &f.CreatedAt))
}

func collectFunctions(rows pgx.Rows, err error) ([]Function, error) {
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (Function, error) { return scanFunction(row) })
}

func InsertFunction(ctx context.Context, q Querier, id, accountID, name, namespace, image string) (Function, error) {
	function, err := scanFunction(q.QueryRow(ctx, `INSERT INTO functions AS f
		(function_id, account_id, name, namespace, image)
		VALUES ($1, $2, $3, $4, $5) RETURNING `+functionColumns,
		id, accountID, name, namespace, image))
	if isUniqueViolation(err, "functions_account_id_name_key") || isUniqueViolation(err, "functions_pkey") {
		return Function{}, ErrDuplicate
	}
	return function, err
}

func GetFunction(ctx context.Context, q Querier, id string) (Function, error) {
	return scanFunction(q.QueryRow(ctx, `SELECT `+functionColumns+` FROM functions f WHERE f.function_id = $1`, id))
}

func GetFunctionByName(ctx context.Context, q Querier, accountID, name string) (Function, error) {
	return scanFunction(q.QueryRow(ctx, `SELECT `+functionColumns+` FROM functions f
		WHERE f.account_id = $1 AND f.name = $2`, accountID, name))
}

func ListFunctions(ctx context.Context, q Querier, accountID string) ([]Function, error) {
	return collectFunctions(q.Query(ctx, `SELECT `+functionColumns+` FROM functions f
		WHERE ($1::text = '' OR f.account_id = $1)
		ORDER BY f.created_at DESC, f.name`, accountID))
}

func DeleteFunction(ctx context.Context, q Querier, id string) error {
	_, err := q.Exec(ctx, `DELETE FROM functions WHERE function_id = $1`, id)
	return err
}

func CountFunctions(ctx context.Context, q Querier, accountID string) (int, error) {
	var count int
	err := q.QueryRow(ctx, `SELECT count(*) FROM functions WHERE account_id = $1`, accountID).Scan(&count)
	return count, err
}
