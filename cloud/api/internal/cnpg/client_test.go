package cnpg

import (
	"context"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func testClient(t *testing.T, handler http.HandlerFunc) *Client {
	t.Helper()
	server := httptest.NewTLSServer(handler)
	t.Cleanup(server.Close)
	certificate, err := x509.ParseCertificate(server.TLS.Certificates[0].Certificate[0])
	if err != nil {
		t.Fatal(err)
	}
	caPEM := string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: certificate.Raw}))
	client, err := New(server.URL, caPEM, "tok")
	if err != nil {
		t.Fatal(err)
	}
	return client
}

func TestCreateCluster(t *testing.T) {
	var gotMethod, gotPath, gotAuth, gotBody string
	client := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		gotMethod, gotPath, gotAuth, gotBody = r.Method, r.URL.Path, r.Header.Get("Authorization"), string(body)
		_, _ = io.WriteString(w, `{"metadata":{"name":"db-abc"},"spec":{"instances":1,"storage":{"size":"5Gi"}},"status":{"phase":"Setting up primary","instances":1,"readyInstances":0}}`)
	})
	cluster, err := client.CreateCluster(context.Background(), ClusterSpec{
		Name: "db-abc", Namespace: "databases", Instances: 1, StorageClass: "local-path", StorageGiB: 5,
		Labels: map[string]string{"shakecloud.io/account": "4856"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if gotMethod != http.MethodPost || gotPath != "/apis/postgresql.cnpg.io/v1/namespaces/databases/clusters" {
		t.Fatalf("%s %s", gotMethod, gotPath)
	}
	if gotAuth != "Bearer tok" {
		t.Fatalf("auth = %q", gotAuth)
	}
	for _, want := range []string{`"instances":1`, `"size":"5Gi"`, `"storageClass":"local-path"`, `"shakecloud.io/account":"4856"`} {
		if !strings.Contains(gotBody, want) {
			t.Fatalf("body missing %s: %s", want, gotBody)
		}
	}
	if cluster.Name != "db-abc" || cluster.Instances != 1 || cluster.StorageGiB != 5 || cluster.Phase != "Setting up primary" {
		t.Fatalf("cluster = %+v", cluster)
	}
}

func TestGetAndListClusters(t *testing.T) {
	client := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("labelSelector") == "shakecloud.io/account=4856" {
			_, _ = io.WriteString(w, `{"items":[{"metadata":{"name":"db-1"},"spec":{"instances":1,"storage":{"size":"5Gi"}},"status":{"phase":"Cluster in healthy state","instances":1,"readyInstances":1}}]}`)
			return
		}
		_, _ = io.WriteString(w, `{"metadata":{"name":"db-1"},"spec":{"instances":1,"storage":{"size":"5Gi"}},"status":{"phase":"Cluster in healthy state","instances":1,"readyInstances":1}}`)
	})
	list, err := client.ListClusters(context.Background(), "databases", "shakecloud.io/account=4856")
	if err != nil || len(list) != 1 || list[0].ReadyInstances != 1 {
		t.Fatalf("list = %+v, %v", list, err)
	}
	one, err := client.GetCluster(context.Background(), "databases", "db-1")
	if err != nil || one.Phase != "Cluster in healthy state" {
		t.Fatalf("get = %+v, %v", one, err)
	}
}

func TestGetClusterNotFound(t *testing.T) {
	client := testClient(t, func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		_, _ = io.WriteString(w, `{"message":"not found"}`)
	})
	_, err := client.GetCluster(context.Background(), "databases", "db-missing")
	var apiErr *Error
	if !errors.As(err, &apiErr) || !apiErr.NotFound() {
		t.Fatalf("expected NotFound, got %v", err)
	}
}

func TestGetCredentials(t *testing.T) {
	client := testClient(t, func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"data": map[string]string{
			"username": "YXBw", "password": "czNjcmV0", "host": "ZHotYXBwLXJ3", "port": "NTQzMg==", "dbname": "YXBw",
		}})
	})
	credentials, err := client.GetCredentials(context.Background(), "databases", "db-1-app")
	if err != nil {
		t.Fatal(err)
	}
	if credentials.Username != "app" || credentials.Password != "s3cret" || credentials.Port != "5432" {
		t.Fatalf("credentials = %+v", credentials)
	}
}
