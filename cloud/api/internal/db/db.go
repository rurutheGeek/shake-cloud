// Package db holds the management database: connection, schema migrations and
// every query. Functions take a Querier so callers choose whether a call joins
// a transaction.
package db

import (
	"context"
	"embed"
	"errors"
	"fmt"
	"io/fs"
	"path"
	"sort"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed migrations/*.sql
var migrationFiles embed.FS

// ErrNotFound is returned when a lookup matches no row.
var ErrNotFound = errors.New("not found")

// Querier is satisfied by *pgxpool.Pool and pgx.Tx.
type Querier interface {
	Exec(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error)
	Query(ctx context.Context, sql string, args ...any) (pgx.Rows, error)
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
}

// Open connects without putting the password in the URL, where it would end up
// in error messages.
func Open(ctx context.Context, url, password string) (*pgxpool.Pool, error) {
	cfg, err := pgxpool.ParseConfig(url)
	if err != nil {
		return nil, fmt.Errorf("parse database URL: %w", err)
	}
	if password != "" {
		cfg.ConnConfig.Password = password
	}
	return pgxpool.NewWithConfig(ctx, cfg)
}

// Migrate applies the embedded migrations in name order, once each. Pending
// files run in one transaction under an advisory lock: two API processes
// starting together cannot apply a file twice, and a failing file leaves the
// schema untouched.
func Migrate(ctx context.Context, pool *pgxpool.Pool) ([]string, error) {
	names, err := fs.Glob(migrationFiles, "migrations/*.sql")
	if err != nil {
		return nil, err
	}
	sort.Strings(names)
	var applied []string
	err = pgx.BeginFunc(ctx, pool, func(tx pgx.Tx) error {
		if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext('shakecloud.migrate'))`); err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, `CREATE TABLE IF NOT EXISTS schema_migrations (
			version text PRIMARY KEY,
			applied_at timestamptz NOT NULL DEFAULT now())`); err != nil {
			return err
		}
		for _, name := range names {
			version := strings.TrimSuffix(path.Base(name), ".sql")
			var done bool
			if err := tx.QueryRow(ctx, `SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version = $1)`, version).Scan(&done); err != nil {
				return err
			}
			if done {
				continue
			}
			body, err := migrationFiles.ReadFile(name)
			if err != nil {
				return err
			}
			// Without arguments pgx uses the simple protocol, which accepts
			// several statements in one call.
			if _, err := tx.Exec(ctx, string(body)); err != nil {
				return fmt.Errorf("migration %s: %w", version, err)
			}
			if _, err := tx.Exec(ctx, `INSERT INTO schema_migrations (version) VALUES ($1)`, version); err != nil {
				return err
			}
			applied = append(applied, version)
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	return applied, nil
}

func isUniqueViolation(err error, constraint string) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && pgErr.Code == "23505" && pgErr.ConstraintName == constraint
}

func noRows(err error) error {
	if errors.Is(err, pgx.ErrNoRows) {
		return ErrNotFound
	}
	return err
}
