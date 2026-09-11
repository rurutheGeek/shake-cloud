package compute

import (
	"context"
	"fmt"
	"testing"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/garage"
)

// fakeGarage is Garage's admin API in memory, enough for the bucket tests.
type fakeGarage struct {
	buckets map[string]garage.BucketInfo // by global alias
	keys    map[string]garage.KeyInfo
	n       int
}

func newFakeGarage() *fakeGarage {
	return &fakeGarage{buckets: map[string]garage.BucketInfo{}, keys: map[string]garage.KeyInfo{}}
}

func (f *fakeGarage) CreateBucket(_ context.Context, name string) (garage.BucketInfo, error) {
	f.n++
	info := garage.BucketInfo{ID: fmt.Sprintf("bucket-%d", f.n), GlobalAliases: []string{name}}
	f.buckets[name] = info
	return info, nil
}

func (f *fakeGarage) ListBuckets(context.Context) ([]garage.Bucket, error) {
	out := []garage.Bucket{}
	for _, info := range f.buckets {
		out = append(out, garage.Bucket{ID: info.ID, GlobalAliases: info.GlobalAliases})
	}
	return out, nil
}

func (f *fakeGarage) BucketInfo(_ context.Context, globalAlias string) (garage.BucketInfo, error) {
	info, ok := f.buckets[globalAlias]
	if !ok {
		return garage.BucketInfo{}, &garage.Error{Status: 404, Body: "NoSuchBucket"}
	}
	return info, nil
}

func (f *fakeGarage) DeleteBucket(_ context.Context, id string) error {
	for alias, info := range f.buckets {
		if info.ID == id {
			delete(f.buckets, alias)
			return nil
		}
	}
	return &garage.Error{Status: 404, Body: "NoSuchBucket"}
}

func (f *fakeGarage) CreateKey(_ context.Context, name string) (garage.KeyInfo, error) {
	f.n++
	info := garage.KeyInfo{AccessKeyID: fmt.Sprintf("GK%024d", f.n), Name: name, SecretAccessKey: "secret-" + name}
	f.keys[info.AccessKeyID] = info
	return info, nil
}

func (f *fakeGarage) ListKeys(context.Context) ([]garage.KeyListItem, error) {
	out := []garage.KeyListItem{}
	for id, info := range f.keys {
		out = append(out, garage.KeyListItem{ID: id, Name: info.Name})
	}
	return out, nil
}

func (f *fakeGarage) GetKeyInfo(_ context.Context, id string) (garage.KeyInfo, error) {
	info, ok := f.keys[id]
	if !ok {
		return garage.KeyInfo{}, &garage.Error{Status: 404, Body: "NoSuchKey"}
	}
	return info, nil
}

func (f *fakeGarage) DeleteKey(_ context.Context, id string) error {
	delete(f.keys, id)
	return nil
}

func (f *fakeGarage) AllowBucketKey(context.Context, string, string, garage.Permissions) error {
	return nil
}

func (f *fakeGarage) DenyBucketKey(context.Context, string, string, garage.Permissions) error {
	return nil
}

func TestCreateBucketCreatesItInGarageAndTheLedger(t *testing.T) {
	s, _, _ := testService(t)
	store := newFakeGarage()
	s.Garage = store
	alice := newAccount(t, s, "alice")

	bucket, created, err := s.CreateBucket(context.Background(), alice, "photos", nil)
	if err != nil {
		t.Fatal(err)
	}
	if !created || bucket.Name != "photos" || bucket.GarageID != "bucket-1" {
		t.Fatalf("bucket = %+v created=%v", bucket, created)
	}
	if _, ok := store.buckets["photos"]; !ok {
		t.Fatal("Garage has no photos bucket")
	}

	// Repeating it returns the same bucket, not a second one.
	again, created, err := s.CreateBucket(context.Background(), alice, "photos", nil)
	if err != nil {
		t.Fatal(err)
	}
	if created || again.GarageID != bucket.GarageID {
		t.Fatalf("repeat created=%v again=%+v", created, again)
	}
	if len(store.buckets) != 1 {
		t.Fatalf("Garage has %d buckets", len(store.buckets))
	}
}

func TestBucketNamesAreValidatedAndOwnersAreSeparated(t *testing.T) {
	s, _, _ := testService(t)
	s.Garage = newFakeGarage()
	alice, bob := newAccount(t, s, "alice"), newAccount(t, s, "bob")

	for _, name := range []string{"ab", "BadName", "no_underscores", "-leading"} {
		if _, _, err := s.CreateBucket(context.Background(), alice, name, nil); code(err) != "InvalidBucketName" {
			t.Fatalf("%q: %v", name, err)
		}
	}
	if _, _, err := s.CreateBucket(context.Background(), alice, "shared", nil); err != nil {
		t.Fatal(err)
	}
	if _, _, err := s.CreateBucket(context.Background(), bob, "shared", nil); code(err) != "BucketAlreadyExists" {
		t.Fatalf("another account took it: %v", err)
	}
}

func TestCreateS3KeyReturnsTheSecretOnce(t *testing.T) {
	s, _, _ := testService(t)
	s.Garage = newFakeGarage()
	alice := newAccount(t, s, "alice")

	key, secret, err := s.CreateS3Key(context.Background(), alice, "laptop", nil)
	if err != nil {
		t.Fatal(err)
	}
	if secret != "secret-laptop" || key.Name != "laptop" || key.KeyID == "" {
		t.Fatalf("key=%+v secret=%q", key, secret)
	}
	// The secret is not stored; listing cannot return it.
	keys, err := s.ListS3Keys(context.Background(), alice)
	if err != nil || len(keys) != 1 {
		t.Fatalf("keys=%v err=%v", keys, err)
	}

	// Creating the same name again returns the same key without a secret.
	again, secret2, err := s.CreateS3Key(context.Background(), alice, "laptop", nil)
	if err != nil {
		t.Fatal(err)
	}
	if secret2 != "" || again.KeyID != key.KeyID {
		t.Fatalf("repeat secret=%q key=%+v", secret2, again)
	}
}

func TestBucketPermissionsMustBeSameAccount(t *testing.T) {
	s, _, _ := testService(t)
	s.Garage = newFakeGarage()
	alice, bob := newAccount(t, s, "alice"), newAccount(t, s, "bob")
	if _, _, err := s.CreateBucket(context.Background(), alice, "photos", nil); err != nil {
		t.Fatal(err)
	}
	aliceKey, _, err := s.CreateS3Key(context.Background(), alice, "alice-key", nil)
	if err != nil {
		t.Fatal(err)
	}
	bobKey, _, err := s.CreateS3Key(context.Background(), bob, "bob-key", nil)
	if err != nil {
		t.Fatal(err)
	}

	status, err := s.SetBucketPermission(context.Background(), "photos", aliceKey.KeyID, true, true, true,
		func(db.Bucket) bool { return true },
		func(_ pgx.Tx, _ db.Bucket, _ db.S3Key) error { return nil })
	if err != nil {
		t.Fatal(err)
	}
	if len(status.Keys) != 1 || !status.Keys[0].Owner {
		t.Fatalf("keys = %+v", status.Keys)
	}

	// Bob's key cannot be granted on Alice's bucket.
	if _, err := s.SetBucketPermission(context.Background(), "photos", bobKey.KeyID, true, false, false,
		func(db.Bucket) bool { return true }, nil); code(err) != "NoSuchKey" {
		t.Fatalf("another account's key: %v", err)
	}
}

func TestDeleteBucketRemovesItFromGarageAndTheLedger(t *testing.T) {
	s, _, _ := testService(t)
	store := newFakeGarage()
	s.Garage = store
	alice := newAccount(t, s, "alice")
	if _, _, err := s.CreateBucket(context.Background(), alice, "photos", nil); err != nil {
		t.Fatal(err)
	}
	if err := s.DeleteBucket(context.Background(), "photos", func(db.Bucket) bool { return true }, nil); err != nil {
		t.Fatal(err)
	}
	if len(store.buckets) != 0 {
		t.Fatalf("Garage still has %v", store.buckets)
	}
	if _, err := db.GetBucket(context.Background(), s.Pool, "photos"); err == nil {
		t.Fatal("the ledger still has the bucket")
	}
}
