package compute

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"net/http"
	"regexp"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/cnpg"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

// Databases are PostgreSQL appliances backed by CloudNativePG. The cloud API
// keeps the account that owns each one and talks to Kubernetes to create or
// remove the Cluster. The database's own data never passes through the API.

// A database name: 2-30 characters, lower case, starts with a letter.
var databaseName = regexp.MustCompile(`^[a-z][a-z0-9-]{1,29}$`)

const (
	maxDatabasesPerAccount = 5
	databaseMinGiB         = 1
	databaseMaxGiB         = 50
	databaseEngineVersion  = "18"
)

// DatabaseStore is the Kubernetes API for CloudNativePG as the service uses it.
type DatabaseStore interface {
	CreateCluster(ctx context.Context, spec cnpg.ClusterSpec) (cnpg.Cluster, error)
	GetCluster(ctx context.Context, namespace, name string) (cnpg.Cluster, error)
	ListClusters(ctx context.Context, namespace, selector string) ([]cnpg.Cluster, error)
	DeleteCluster(ctx context.Context, namespace, name string) error
	GetCredentials(ctx context.Context, namespace, secretName string) (cnpg.Credentials, error)
}

// DatabaseStatus is a database with the live state of its cluster.
type DatabaseStatus struct {
	Database  db.Database
	Phase     string
	Ready     int
	Instances int
}

func databaseNotFound(id string) error {
	return refuse(http.StatusNotFound, "NoSuchDatabase", "database %s does not exist", id)
}

// databaseReady refuses when Kubernetes is not configured on this deployment.
func (s *Service) databaseReady() error {
	if s.Databases == nil {
		return refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "Kubernetes is not configured on this deployment")
	}
	return nil
}

func newDatabaseID() string {
	b := make([]byte, 9)
	_, _ = rand.Read(b)
	return "db-" + hex.EncodeToString(b)[:17]
}

// CreateDatabase makes one PostgreSQL appliance. Repeating with the same name
// returns the existing one.
func (s *Service) CreateDatabase(ctx context.Context, accountID, name string, storageGiB int, audit func(pgx.Tx, db.Database) error) (db.Database, bool, error) {
	bad := func(format string, args ...any) error {
		return refuse(http.StatusBadRequest, "InvalidParameterValue", format, args...)
	}
	name = strings.TrimSpace(name)
	switch {
	case !databaseName.MatchString(name):
		return db.Database{}, false, bad("a database name is 2-30 characters of lower case letters, digits and hyphens, and starts with a letter")
	case storageGiB < databaseMinGiB || storageGiB > databaseMaxGiB:
		return db.Database{}, false, bad("storage is between %d and %d GiB", databaseMinGiB, databaseMaxGiB)
	}
	if err := s.databaseReady(); err != nil {
		return db.Database{}, false, err
	}

	var database db.Database
	created := false
	err := pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		if existing, err := db.GetDatabaseByName(ctx, tx, accountID, name); err == nil {
			database = existing
			return nil
		} else if !errors.Is(err, db.ErrNotFound) {
			return err
		}
		count, err := db.CountDatabases(ctx, tx, accountID)
		if err != nil {
			return err
		}
		if count >= maxDatabasesPerAccount {
			return refuse(http.StatusConflict, "DatabaseLimitExceeded", "an account may hold %d databases", maxDatabasesPerAccount)
		}
		id := newDatabaseID()
		if _, err := s.Databases.CreateCluster(ctx, cnpg.ClusterSpec{
			Name:         id,
			Namespace:    s.DatabaseNamespace,
			Instances:    1,
			StorageClass: s.DatabaseStorageClass,
			StorageGiB:   storageGiB,
			Labels: map[string]string{
				"shakecloud.io/account":  accountID,
				"shakecloud.io/database": id,
			},
		}); err != nil {
			return refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "Kubernetes could not create the cluster: %v", err)
		}
		database, err = db.InsertDatabase(ctx, tx, id, accountID, name, s.DatabaseNamespace, "postgres", databaseEngineVersion, storageGiB)
		if err != nil {
			// Do not leak a cluster the ledger does not know about.
			_ = s.Databases.DeleteCluster(ctx, s.DatabaseNamespace, id)
			if errors.Is(err, db.ErrDuplicate) {
				return refuse(http.StatusConflict, "ResourceAlreadyExists", "database %s already exists", name)
			}
			return err
		}
		created = true
		if audit != nil {
			return audit(tx, database)
		}
		return nil
	})
	return database, created, err
}

// ListDatabases returns an account's databases (every account's when accountID
// is empty) with the live cluster state.
func (s *Service) ListDatabases(ctx context.Context, accountID string) ([]DatabaseStatus, error) {
	if err := s.databaseReady(); err != nil {
		return nil, err
	}
	databases, err := db.ListDatabases(ctx, s.Pool, accountID)
	if err != nil {
		return nil, err
	}
	selector := ""
	if accountID != "" {
		selector = "shakecloud.io/account=" + accountID
	}
	clusters, err := s.Databases.ListClusters(ctx, s.DatabaseNamespace, selector)
	if err != nil {
		return nil, refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "Kubernetes could not list clusters: %v", err)
	}
	byName := make(map[string]cnpg.Cluster, len(clusters))
	for _, cluster := range clusters {
		byName[cluster.Name] = cluster
	}
	statuses := make([]DatabaseStatus, 0, len(databases))
	for _, record := range databases {
		statuses = append(statuses, statusOf(record, byName[record.ID]))
	}
	return statuses, nil
}

// GetDatabase returns one database with its live state.
func (s *Service) GetDatabase(ctx context.Context, id string) (DatabaseStatus, error) {
	if err := s.databaseReady(); err != nil {
		return DatabaseStatus{}, err
	}
	record, err := db.GetDatabase(ctx, s.Pool, id)
	if errors.Is(err, db.ErrNotFound) {
		return DatabaseStatus{}, databaseNotFound(id)
	}
	if err != nil {
		return DatabaseStatus{}, err
	}
	cluster, err := s.Databases.GetCluster(ctx, record.Namespace, record.ID)
	if err != nil {
		return DatabaseStatus{}, refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "Kubernetes could not read the cluster: %v", err)
	}
	return statusOf(record, cluster), nil
}

// DeleteDatabase removes the Cluster and the ledger row.
func (s *Service) DeleteDatabase(ctx context.Context, id string, audit func(pgx.Tx, db.Database) error) error {
	if err := s.databaseReady(); err != nil {
		return err
	}
	return pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		record, err := db.GetDatabase(ctx, tx, id)
		if errors.Is(err, db.ErrNotFound) {
			return databaseNotFound(id)
		}
		if err != nil {
			return err
		}
		if err := s.Databases.DeleteCluster(ctx, record.Namespace, record.ID); err != nil {
			var apiErr *cnpg.Error
			if !errors.As(err, &apiErr) || !apiErr.NotFound() {
				return refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "Kubernetes could not delete the cluster: %v", err)
			}
		}
		if err := db.DeleteDatabase(ctx, tx, id); err != nil {
			return err
		}
		if audit != nil {
			return audit(tx, record)
		}
		return nil
	})
}

// DatabaseCredentials reads the operator's app secret for a database.
func (s *Service) DatabaseCredentials(ctx context.Context, id string) (db.Database, cnpg.Credentials, error) {
	if err := s.databaseReady(); err != nil {
		return db.Database{}, cnpg.Credentials{}, err
	}
	record, err := db.GetDatabase(ctx, s.Pool, id)
	if errors.Is(err, db.ErrNotFound) {
		return db.Database{}, cnpg.Credentials{}, databaseNotFound(id)
	}
	if err != nil {
		return db.Database{}, cnpg.Credentials{}, err
	}
	credentials, err := s.Databases.GetCredentials(ctx, record.Namespace, record.ID+"-app")
	if err != nil {
		return db.Database{}, cnpg.Credentials{}, refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "the database credentials are not ready yet")
	}
	return record, credentials, nil
}

func statusOf(record db.Database, cluster cnpg.Cluster) DatabaseStatus {
	return DatabaseStatus{
		Database:  record,
		Phase:     cluster.Phase,
		Ready:     cluster.ReadyInstances,
		Instances: cluster.Instances,
	}
}
