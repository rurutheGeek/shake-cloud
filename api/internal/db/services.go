package db

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5"
)

// A service is one always-on Deployment, owned by one account. The id is also
// the name of its Kubernetes objects, so it stays a DNS-safe label.
type Service struct {
	ID            string
	AccountID     string
	OwnerUsername string
	Name          string
	Namespace     string
	Image         string
	Port          int
	MemoryMiB     int
	Env           map[string]string
	SecretNames   []string
	DiskGiB       int
	MountPath     string
	CreatedAt     time.Time
}

const serviceColumns = `s.service_id, s.account_id,
	coalesce((SELECT a.username FROM accounts a WHERE a.id = s.account_id), ''),
	s.name, s.namespace, s.image, s.port, s.memory_mib, s.env, s.secret_names,
	s.disk_gib, s.mount_path, s.created_at`

func scanService(row pgx.Row) (Service, error) {
	var s Service
	err := row.Scan(&s.ID, &s.AccountID, &s.OwnerUsername, &s.Name, &s.Namespace, &s.Image,
		&s.Port, &s.MemoryMiB, &s.Env, &s.SecretNames, &s.DiskGiB, &s.MountPath, &s.CreatedAt)
	return s, noRows(err)
}

func collectServices(rows pgx.Rows, err error) ([]Service, error) {
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (Service, error) { return scanService(row) })
}

func InsertService(ctx context.Context, q Querier, s Service) (Service, error) {
	if s.Env == nil {
		s.Env = map[string]string{}
	}
	if s.SecretNames == nil {
		s.SecretNames = []string{}
	}
	service, err := scanService(q.QueryRow(ctx, `INSERT INTO services AS s
		(service_id, account_id, name, namespace, image, port, memory_mib, env, secret_names, disk_gib, mount_path)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) RETURNING `+serviceColumns,
		s.ID, s.AccountID, s.Name, s.Namespace, s.Image, s.Port, s.MemoryMiB, s.Env, s.SecretNames, s.DiskGiB, s.MountPath))
	if isUniqueViolation(err, "services_account_id_name_key") || isUniqueViolation(err, "services_pkey") {
		return Service{}, ErrDuplicate
	}
	return service, err
}

// UpdateService writes the fields a modify may change.
func UpdateService(ctx context.Context, q Querier, s Service) (Service, error) {
	return scanService(q.QueryRow(ctx, `UPDATE services AS s
		SET image = $2, memory_mib = $3, env = $4, secret_names = $5
		WHERE s.service_id = $1 RETURNING `+serviceColumns,
		s.ID, s.Image, s.MemoryMiB, s.Env, s.SecretNames))
}

func GetService(ctx context.Context, q Querier, id string) (Service, error) {
	return scanService(q.QueryRow(ctx, `SELECT `+serviceColumns+` FROM services s WHERE s.service_id = $1`, id))
}

// GetServiceForUpdate locks the row so that two modifies do not interleave.
func GetServiceForUpdate(ctx context.Context, q Querier, id string) (Service, error) {
	return scanService(q.QueryRow(ctx, `SELECT `+serviceColumns+` FROM services s WHERE s.service_id = $1 FOR UPDATE`, id))
}

func GetServiceByName(ctx context.Context, q Querier, accountID, name string) (Service, error) {
	return scanService(q.QueryRow(ctx, `SELECT `+serviceColumns+` FROM services s
		WHERE s.account_id = $1 AND s.name = $2`, accountID, name))
}

func ListServices(ctx context.Context, q Querier, accountID string) ([]Service, error) {
	return collectServices(q.Query(ctx, `SELECT `+serviceColumns+` FROM services s
		WHERE ($1::text = '' OR s.account_id = $1)
		ORDER BY s.created_at DESC, s.name`, accountID))
}

func DeleteService(ctx context.Context, q Querier, id string) error {
	_, err := q.Exec(ctx, `DELETE FROM services WHERE service_id = $1`, id)
	return err
}

func CountServices(ctx context.Context, q Querier, accountID string) (int, error) {
	var count int
	err := q.QueryRow(ctx, `SELECT count(*) FROM services WHERE account_id = $1`, accountID).Scan(&count)
	return count, err
}
