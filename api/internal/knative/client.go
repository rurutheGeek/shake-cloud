// Package knative talks to the Kubernetes API for Knative Services.
//
// It mirrors the cnpg client: REST with a bearer token and the cluster CA, so
// the API keeps its small dependency set. The token belongs to the same
// ServiceAccount (databases/cloud-api) that also owns the database clusters.
package knative

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type Client struct {
	baseURL string
	token   string
	http    *http.Client
}

func New(baseURL, caPEM, token string) (*Client, error) {
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM([]byte(caPEM)) {
		return nil, errors.New("knative: the CA is not a PEM certificate")
	}
	return &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		token:   token,
		http: &http.Client{
			Timeout: 30 * time.Second,
			Transport: &http.Transport{TLSClientConfig: &tls.Config{
				RootCAs: pool, MinVersion: tls.VersionTLS12,
			}},
		},
	}, nil
}

// Error is a non-2xx answer from the API server.
type Error struct {
	Status int
	Body   string
}

func (e *Error) Error() string {
	return fmt.Sprintf("kubernetes returned %d: %s", e.Status, strings.TrimSpace(e.Body))
}

func (e *Error) NotFound() bool { return e.Status == http.StatusNotFound }

// Service is the slice of a Knative Service the cloud cares about.
type Service struct {
	Name      string
	Namespace string
	Image     string
	URL       string
	Ready     bool
	CreatedAt time.Time
}

type serviceObject struct {
	Metadata struct {
		Name              string    `json:"name"`
		CreationTimestamp time.Time `json:"creationTimestamp"`
	} `json:"metadata"`
	Spec struct {
		Template struct {
			Spec struct {
				Containers []struct {
					Image string `json:"image"`
				} `json:"containers"`
			} `json:"spec"`
		} `json:"template"`
	} `json:"spec"`
	Status struct {
		URL        string `json:"url"`
		Conditions []struct {
			Type   string `json:"type"`
			Status string `json:"status"`
		} `json:"conditions"`
	} `json:"status"`
}

func (o serviceObject) service() Service {
	image := ""
	if len(o.Spec.Template.Spec.Containers) > 0 {
		image = o.Spec.Template.Spec.Containers[0].Image
	}
	ready := false
	for _, condition := range o.Status.Conditions {
		if condition.Type == "Ready" && condition.Status == "True" {
			ready = true
		}
	}
	return Service{
		Name: o.Metadata.Name, URL: o.Status.URL, Image: image,
		Ready: ready, CreatedAt: o.Metadata.CreationTimestamp,
	}
}

// ServiceSpec is what a new function needs.
type ServiceSpec struct {
	Name      string
	Namespace string
	Image     string
	Labels    map[string]string
}

// CreateService creates a Knative Service with one container.
func (c *Client) CreateService(ctx context.Context, spec ServiceSpec) (Service, error) {
	body := map[string]any{
		"apiVersion": "serving.knative.dev/v1",
		"kind":       "Service",
		"metadata": map[string]any{
			"name":      spec.Name,
			"namespace": spec.Namespace,
			"labels":    spec.Labels,
		},
		"spec": map[string]any{
			"template": map[string]any{
				"spec": map[string]any{
					"containers": []any{map[string]any{"image": spec.Image}},
				},
			},
		},
	}
	var created serviceObject
	if err := c.do(ctx, http.MethodPost, c.servicesPath(spec.Namespace), body, &created); err != nil {
		return Service{}, err
	}
	return created.service(), nil
}

func (c *Client) GetService(ctx context.Context, namespace, name string) (Service, error) {
	var got serviceObject
	if err := c.do(ctx, http.MethodGet, c.servicePath(namespace, name), nil, &got); err != nil {
		return Service{}, err
	}
	return got.service(), nil
}

func (c *Client) ListServices(ctx context.Context, namespace, labelSelector string) ([]Service, error) {
	path := c.servicesPath(namespace)
	if labelSelector != "" {
		path += "?labelSelector=" + url.QueryEscape(labelSelector)
	}
	var list struct {
		Items []serviceObject `json:"items"`
	}
	if err := c.do(ctx, http.MethodGet, path, nil, &list); err != nil {
		return nil, err
	}
	services := make([]Service, 0, len(list.Items))
	for _, item := range list.Items {
		services = append(services, item.service())
	}
	return services, nil
}

func (c *Client) DeleteService(ctx context.Context, namespace, name string) error {
	return c.do(ctx, http.MethodDelete, c.servicePath(namespace, name), nil, nil)
}

func (c *Client) servicesPath(namespace string) string {
	return fmt.Sprintf("/apis/serving.knative.dev/v1/namespaces/%s/services", url.PathEscape(namespace))
}

func (c *Client) servicePath(namespace, name string) string {
	return c.servicesPath(namespace) + "/" + url.PathEscape(name)
}

func (c *Client) do(ctx context.Context, method, path string, body any, out any) error {
	var payload io.Reader
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return err
		}
		payload = bytes.NewReader(encoded)
	}
	request, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, payload)
	if err != nil {
		return err
	}
	request.Header.Set("Authorization", "Bearer "+c.token)
	request.Header.Set("Accept", "application/json")
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	response, err := c.http.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	data, err := io.ReadAll(io.LimitReader(response.Body, 4<<20))
	if err != nil {
		return err
	}
	if response.StatusCode >= 400 {
		return &Error{Status: response.StatusCode, Body: string(data)}
	}
	if out == nil || len(data) == 0 {
		return nil
	}
	return json.Unmarshal(data, out)
}
