package workload

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
)

func TestDeploymentObject(t *testing.T) {
	spec := Spec{
		Name: "svc-1", Namespace: "services", Image: "example/app:v1", Port: 8080, MemoryMiB: 128,
		Env: map[string]string{"B": "2", "A": "1"}, Secrets: map[string]string{"TOKEN": "x"},
		DiskGiB: 4, MountPath: "/data",
	}
	encoded, _ := json.Marshal(deploymentObject(spec))
	text := string(encoded)
	for _, want := range []string{
		`"type":"Recreate"`, `"claimName":"svc-1"`, `"mountPath":"/data"`,
		`"secretKeyRef":{"key":"TOKEN","name":"svc-1"}`, `"memory":"128Mi"`,
		`"readOnlyRootFilesystem":true`, `"replicas":1`,
	} {
		if !strings.Contains(text, want) {
			t.Errorf("deployment lacks %s:\n%s", want, text)
		}
	}
	if strings.Contains(text, `"x"`) {
		t.Errorf("a secret value leaked into the deployment: %s", text)
	}
	if strings.Index(text, `"name":"A"`) > strings.Index(text, `"name":"B"`) {
		t.Errorf("environment is not sorted: %s", text)
	}
	spec.DiskGiB, spec.MountPath = 0, ""
	encoded, _ = json.Marshal(deploymentObject(spec))
	if !strings.Contains(string(encoded), `"type":"RollingUpdate"`) {
		t.Errorf("a service without a disk should roll: %s", encoded)
	}
}

func TestSecretsHashChangesWithValues(t *testing.T) {
	a := SecretsHash(map[string]string{"K": "1"})
	if a == SecretsHash(map[string]string{"K": "2"}) || a != SecretsHash(map[string]string{"K": "1"}) {
		t.Fatal("the hash must follow the values and be stable")
	}
}

func TestApplyCreatesMissingObjects(t *testing.T) {
	var mu sync.Mutex
	var calls []string
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		calls = append(calls, r.Method+" "+r.URL.Path)
		mu.Unlock()
		_, _ = io.Copy(io.Discard, r.Body)
		if r.Method == http.MethodPut || r.Method == http.MethodGet {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		_, _ = io.WriteString(w, `{}`)
	}))
	defer server.Close()
	c := &Client{baseURL: server.URL, token: "t", http: server.Client(), StorageClass: "local-path"}
	err := c.Apply(context.Background(), Spec{Name: "svc-1", Namespace: "services", Image: "i", Port: 80, MemoryMiB: 64, DiskGiB: 1, MountPath: "/data"})
	if err != nil {
		t.Fatal(err)
	}
	want := []string{
		"PUT /api/v1/namespaces/services/secrets/svc-1",
		"POST /api/v1/namespaces/services/secrets",
		"POST /api/v1/namespaces/services/persistentvolumeclaims",
		"GET /api/v1/namespaces/services/services/svc-1",
		"POST /api/v1/namespaces/services/services",
		"PUT /apis/apps/v1/namespaces/services/deployments/svc-1",
		"POST /apis/apps/v1/namespaces/services/deployments",
	}
	if strings.Join(calls, "\n") != strings.Join(want, "\n") {
		t.Fatalf("calls:\n%s", strings.Join(calls, "\n"))
	}
}
