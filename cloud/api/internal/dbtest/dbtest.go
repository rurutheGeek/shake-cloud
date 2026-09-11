// Package dbtest gives tests a migrated PostgreSQL database of their own.
//
// Set SHAKECLOUD_TEST_DATABASE_URL to a server where the user may create
// databases. Each call creates one and drops it when the test ends. Without the
// variable the test is skipped, so `go test ./...` still runs offline.
package dbtest

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"os"
	"testing"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

func Pool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	dsn := os.Getenv("SHAKECLOUD_TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("SHAKECLOUD_TEST_DATABASE_URL is not set")
	}
	ctx := context.Background()
	admin, err := pgx.Connect(ctx, dsn)
	if err != nil {
		t.Fatal(err)
	}
	suffix := make([]byte, 6)
	rand.Read(suffix)
	name := "shakecloud_test_" + hex.EncodeToString(suffix)
	if _, err := admin.Exec(ctx, "CREATE DATABASE "+name); err != nil {
		t.Fatal(err)
	}
	config, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		t.Fatal(err)
	}
	config.ConnConfig.Database = name
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		pool.Close()
		_, _ = admin.Exec(ctx, "DROP DATABASE "+name+" WITH (FORCE)")
		_ = admin.Close(ctx)
	})
	if _, err := db.Migrate(ctx, pool); err != nil {
		t.Fatal(err)
	}
	return pool
}
