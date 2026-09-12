package knative

import (
	"context"
	"crypto/x509"
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

func TestCreateService(t *testing.T) {
	var gotMethod, gotPath, gotAuth, gotBody string
	client := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		gotMethod, gotPath, gotAuth, gotBody = r.Method, r.URL.Path, r.Header.Get("Authorization"), string(body)
		_, _ = io.WriteString(w, `{"metadata":{"name":"fn-abc"},"spec":{"template":{"spec":{"containers":[{"image":"example/greeter:v1"}]}}},"status":{"url":"http://fn-abc.functions.example","conditions":[{"type":"Ready","status":"True"}]}}`)
	})
	service, err := client.CreateService(context.Background(), ServiceSpec{
		Name: "fn-abc", Namespace: "functions", Image: "example/greeter:v1",
		Labels: map[string]string{"shakecloud.io/account": "4856"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if gotMethod != http.MethodPost || gotPath != "/apis/serving.knative.dev/v1/namespaces/functions/services" {
		t.Fatalf("%s %s", gotMethod, gotPath)
	}
	if gotAuth != "Bearer tok" {
		t.Fatalf("auth = %q", gotAuth)
	}
	for _, want := range []string{`"image":"example/greeter:v1"`, `"shakecloud.io/account":"4856"`} {
		if !strings.Contains(gotBody, want) {
			t.Fatalf("body missing %s: %s", want, gotBody)
		}
	}
	if service.Name != "fn-abc" || !service.Ready || service.URL != "http://fn-abc.functions.example" {
		t.Fatalf("service = %+v", service)
	}
}

func TestGetAndListServices(t *testing.T) {
	client := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.URL.Path, "/services/fn-1") {
			_, _ = io.WriteString(w, `{"metadata":{"name":"fn-1"},"status":{"url":"http://fn-1.functions.example","conditions":[{"type":"Ready","status":"True"}]}}`)
			return
		}
		_, _ = io.WriteString(w, `{"items":[{"metadata":{"name":"fn-1"},"status":{"url":"http://fn-1.functions.example","conditions":[{"type":"Ready","status":"True"}]}}]}`)
	})
	list, err := client.ListServices(context.Background(), "functions", "shakecloud.io/account=4856")
	if err != nil || len(list) != 1 || !list[0].Ready {
		t.Fatalf("list = %+v, %v", list, err)
	}
	one, err := client.GetService(context.Background(), "functions", "fn-1")
	if err != nil || one.URL == "" {
		t.Fatalf("get = %+v, %v", one, err)
	}
}

func TestGetServiceNotFound(t *testing.T) {
	client := testClient(t, func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		_, _ = io.WriteString(w, `{"message":"not found"}`)
	})
	_, err := client.GetService(context.Background(), "functions", "fn-missing")
	var apiErr *Error
	if !errors.As(err, &apiErr) || !apiErr.NotFound() {
		t.Fatalf("expected NotFound, got %v", err)
	}
}
