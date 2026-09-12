package compute

import (
	"context"
	"fmt"
	"strings"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/cnpg"
)

// fakeCNPG is the CloudNativePG API in memory, enough for the database tests.
type fakeCNPG struct {
	clusters map[string]cnpg.Cluster
	creds    map[string]cnpg.Credentials
}

func newFakeCNPG() *fakeCNPG {
	return &fakeCNPG{clusters: map[string]cnpg.Cluster{}, creds: map[string]cnpg.Credentials{}}
}

func (f *fakeCNPG) CreateCluster(_ context.Context, spec cnpg.ClusterSpec) (cnpg.Cluster, error) {
	cluster := cnpg.Cluster{
		Name: spec.Name, Namespace: spec.Namespace, Phase: "Cluster in healthy state",
		Instances: spec.Instances, ReadyInstances: spec.Instances, StorageGiB: spec.StorageGiB,
	}
	f.clusters[spec.Name] = cluster
	f.creds[spec.Name] = cnpg.Credentials{Username: "app", Password: "s3cret", Host: spec.Name + "-rw", Port: "5432", Database: "app"}
	return cluster, nil
}

func (f *fakeCNPG) GetCluster(_ context.Context, _, name string) (cnpg.Cluster, error) {
	cluster, ok := f.clusters[name]
	if !ok {
		return cnpg.Cluster{}, &cnpg.Error{Status: 404}
	}
	return cluster, nil
}

func (f *fakeCNPG) ListClusters(context.Context, string, string) ([]cnpg.Cluster, error) {
	out := make([]cnpg.Cluster, 0, len(f.clusters))
	for _, cluster := range f.clusters {
		out = append(out, cluster)
	}
	return out, nil
}

func (f *fakeCNPG) DeleteCluster(_ context.Context, _, name string) error {
	delete(f.clusters, name)
	return nil
}

func (f *fakeCNPG) GetCredentials(_ context.Context, _, secretName string) (cnpg.Credentials, error) {
	credentials, ok := f.creds[strings.TrimSuffix(secretName, "-app")]
	if !ok {
		return cnpg.Credentials{}, &cnpg.Error{Status: 404}
	}
	return credentials, nil
}

func databaseService(t *testing.T) (*Service, *fakeCNPG, string) {
	t.Helper()
	s, _, _ := testService(t)
	fake := newFakeCNPG()
	s.Databases = fake
	s.DatabaseNamespace = "databases"
	s.DatabaseStorageClass = "local-path"
	return s, fake, newAccount(t, s, "db-owner")
}

func TestCreateDatabase(t *testing.T) {
	s, fake, account := databaseService(t)
	record, created, err := s.CreateDatabase(context.Background(), account, "shop", 5, nil)
	if err != nil {
		t.Fatal(err)
	}
	if !created || record.Name != "shop" || record.StorageGiB != 5 || record.EngineVersion == "" {
		t.Fatalf("unexpected record %+v", record)
	}
	if _, ok := fake.clusters[record.ID]; !ok {
		t.Fatalf("cluster %s was not created", record.ID)
	}
	again, createdAgain, err := s.CreateDatabase(context.Background(), account, "shop", 5, nil)
	if err != nil {
		t.Fatal(err)
	}
	if createdAgain || again.ID != record.ID {
		t.Fatalf("repeating the name must return the existing database, got %+v", again)
	}
}

func TestCreateDatabaseValidation(t *testing.T) {
	s, _, account := databaseService(t)
	for _, test := range []struct {
		name    string
		storage int
	}{
		{"Shop", 5}, {"a", 5}, {"x y", 5}, {"-bad", 5}, {"shop", 0}, {"shop", 99},
	} {
		if _, _, err := s.CreateDatabase(context.Background(), account, test.name, test.storage, nil); code(err) != "InvalidParameterValue" {
			t.Fatalf("%q/%d: expected InvalidParameterValue, got %v", test.name, test.storage, err)
		}
	}
}

func TestDatabaseLifecycleAndCredentials(t *testing.T) {
	s, _, account := databaseService(t)
	record, _, err := s.CreateDatabase(context.Background(), account, "shop", 5, nil)
	if err != nil {
		t.Fatal(err)
	}
	list, err := s.ListDatabases(context.Background(), account)
	if err != nil || len(list) != 1 || list[0].Ready != 1 {
		t.Fatalf("list = %+v, %v", list, err)
	}
	record2, credentials, err := s.DatabaseCredentials(context.Background(), record.ID)
	if err != nil || credentials.Username != "app" || record2.ID != record.ID {
		t.Fatalf("credentials = %+v, %v", credentials, err)
	}
	if err := s.DeleteDatabase(context.Background(), record.ID, nil); err != nil {
		t.Fatal(err)
	}
	if _, err := s.GetDatabase(context.Background(), record.ID); code(err) != "NoSuchDatabase" {
		t.Fatalf("expected NoSuchDatabase after delete, got %v", err)
	}
}

func TestDatabaseLimit(t *testing.T) {
	s, _, account := databaseService(t)
	for i := 0; i < maxDatabasesPerAccount; i++ {
		if _, _, err := s.CreateDatabase(context.Background(), account, fmt.Sprintf("db%d", i), 1, nil); err != nil {
			t.Fatal(err)
		}
	}
	if _, _, err := s.CreateDatabase(context.Background(), account, "toomany", 1, nil); code(err) != "DatabaseLimitExceeded" {
		t.Fatalf("expected DatabaseLimitExceeded, got %v", err)
	}
}
