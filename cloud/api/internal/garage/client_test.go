package garage

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestCreateBucketSendsTheTokenAndDecodesTheAnswer(t *testing.T) {
	var gotAuth, gotPath, gotBody string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth, gotPath = r.Header.Get("Authorization"), r.URL.Path
		body, _ := io.ReadAll(r.Body)
		gotBody = string(body)
		io.WriteString(w, `{"id":"abc123","created":"2026-09-11T00:00:00Z","globalAliases":["photos"],"keys":[]}`)
	}))
	defer server.Close()

	info, err := New(server.URL, "s3cr3t").CreateBucket(context.Background(), "photos")
	if err != nil {
		t.Fatal(err)
	}
	if gotAuth != "Bearer s3cr3t" || gotPath != "/v2/CreateBucket" {
		t.Fatalf("auth=%q path=%q", gotAuth, gotPath)
	}
	if !strings.Contains(gotBody, `"globalAlias":"photos"`) {
		t.Fatalf("body = %s", gotBody)
	}
	if info.ID != "abc123" {
		t.Fatalf("id = %q", info.ID)
	}
}

func TestCreateKeyReturnsTheSecret(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v2/CreateKey" {
			t.Errorf("path = %s", r.URL.Path)
		}
		io.WriteString(w, `{"accessKeyId":"GK0123456789abcdef01234567","name":"app","secretAccessKey":"secret-value"}`)
	}))
	defer server.Close()

	info, err := New(server.URL, "t").CreateKey(context.Background(), "app")
	if err != nil {
		t.Fatal(err)
	}
	if info.AccessKeyID != "GK0123456789abcdef01234567" || info.SecretAccessKey != "secret-value" {
		t.Fatalf("key = %+v", info)
	}
}

func TestAllowBucketKeySendsPermissions(t *testing.T) {
	var gotBody string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		gotBody = string(body)
		io.WriteString(w, `{"id":"abc","created":"2026-09-11T00:00:00Z","globalAliases":["photos"],"keys":[]}`)
	}))
	defer server.Close()

	err := New(server.URL, "t").AllowBucketKey(context.Background(), "bucket-id", "GKkey", Permissions{Read: true, Write: true, Owner: true})
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{`"bucketId":"bucket-id"`, `"accessKeyId":"GKkey"`, `"read":true`, `"write":true`, `"owner":true`} {
		if !strings.Contains(gotBody, want) {
			t.Fatalf("body %s missing %s", gotBody, want)
		}
	}
}

func TestANotFoundIsATypedError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		io.WriteString(w, `{"error":"NoSuchBucket"}`)
	}))
	defer server.Close()

	err := New(server.URL, "t").DeleteBucket(context.Background(), "gone")
	var garageErr *Error
	if !errors.As(err, &garageErr) {
		t.Fatalf("err = %v, want *Error", err)
	}
	if garageErr.Status != http.StatusNotFound || !garageErr.NotFound() {
		t.Fatalf("error = %+v", garageErr)
	}
}
