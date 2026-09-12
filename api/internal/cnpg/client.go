// Package cnpg talks to the Kubernetes API for CloudNativePG clusters.
//
// It uses the REST API directly with a bearer token and the cluster CA, so the
// API keeps its small dependency set. The token comes from a ServiceAccount
// scoped to the databases namespace (cluster create/read/delete and secrets).
package cnpg

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// Client is a minimal Kubernetes client for the CloudNativePG resources.
type Client struct {
	baseURL string
	token   string
	http    *http.Client
}

// New builds a client. caPEM is the cluster CA certificate.
func New(baseURL, caPEM, token string) (*Client, error) {
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM([]byte(caPEM)) {
		return nil, errors.New("cnpg: the CA is not a PEM certificate")
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

// NotFound reports whether the object is gone.
func (e *Error) NotFound() bool { return e.Status == http.StatusNotFound }

// AlreadyExists reports whether the object is already there.
func (e *Error) AlreadyExists() bool { return e.Status == http.StatusConflict }

// Cluster is the slice of a CloudNativePG Cluster that the cloud cares about.
type Cluster struct {
	Name           string
	Namespace      string
	Phase          string
	Instances      int
	ReadyInstances int
	StorageGiB     int
	CreatedAt      time.Time
}

type clusterObject struct {
	Metadata struct {
		Name              string    `json:"name"`
		CreationTimestamp time.Time `json:"creationTimestamp"`
	} `json:"metadata"`
	Spec struct {
		Instances int `json:"instances"`
		Storage   struct {
			Size string `json:"size"`
		} `json:"storage"`
	} `json:"spec"`
	Status struct {
		Phase          string `json:"phase"`
		Instances      int    `json:"instances"`
		ReadyInstances int    `json:"readyInstances"`
	} `json:"status"`
}

func (o clusterObject) cluster() Cluster {
	return Cluster{
		Name:           o.Metadata.Name,
		Phase:          o.Status.Phase,
		Instances:      o.Spec.Instances,
		ReadyInstances: o.Status.ReadyInstances,
		StorageGiB:     parseGiB(o.Spec.Storage.Size),
		CreatedAt:      o.Metadata.CreationTimestamp,
	}
}

// ClusterSpec is what a new database needs.
type ClusterSpec struct {
	Name         string
	Namespace    string
	Instances    int
	StorageClass string
	StorageGiB   int
	Labels       map[string]string
}

// CreateCluster creates a one-primary CloudNativePG cluster.
func (c *Client) CreateCluster(ctx context.Context, spec ClusterSpec) (Cluster, error) {
	body := map[string]any{
		"apiVersion": "postgresql.cnpg.io/v1",
		"kind":       "Cluster",
		"metadata": map[string]any{
			"name":      spec.Name,
			"namespace": spec.Namespace,
			"labels":    spec.Labels,
		},
		"spec": map[string]any{
			"instances": spec.Instances,
			"storage": map[string]any{
				"storageClass": spec.StorageClass,
				"size":         fmt.Sprintf("%dGi", spec.StorageGiB),
			},
			"resources": map[string]any{
				"requests": map[string]any{"cpu": "100m", "memory": "256Mi"},
			},
		},
	}
	var created clusterObject
	if err := c.do(ctx, http.MethodPost, c.clustersPath(spec.Namespace), body, &created); err != nil {
		return Cluster{}, err
	}
	return created.cluster(), nil
}

// GetCluster reads one cluster. A missing cluster is *Error with NotFound().
func (c *Client) GetCluster(ctx context.Context, namespace, name string) (Cluster, error) {
	var got clusterObject
	if err := c.do(ctx, http.MethodGet, c.clusterPath(namespace, name), nil, &got); err != nil {
		return Cluster{}, err
	}
	return got.cluster(), nil
}

// ListClusters lists clusters in a namespace, optionally filtered by labels
// expressed as a Kubernetes label selector.
func (c *Client) ListClusters(ctx context.Context, namespace, labelSelector string) ([]Cluster, error) {
	path := c.clustersPath(namespace)
	if labelSelector != "" {
		path += "?labelSelector=" + url.QueryEscape(labelSelector)
	}
	var list struct {
		Items []clusterObject `json:"items"`
	}
	if err := c.do(ctx, http.MethodGet, path, nil, &list); err != nil {
		return nil, err
	}
	clusters := make([]Cluster, 0, len(list.Items))
	for _, item := range list.Items {
		clusters = append(clusters, item.cluster())
	}
	return clusters, nil
}

// DeleteCluster removes a cluster and everything the operator made for it.
func (c *Client) DeleteCluster(ctx context.Context, namespace, name string) error {
	return c.do(ctx, http.MethodDelete, c.clusterPath(namespace, name), nil, nil)
}

// Credentials are the connection fields from a CNPG-managed app secret.
type Credentials struct {
	Username string
	Password string
	Host     string
	Port     string
	Database string
}

// GetCredentials reads the Secret the operator creates for the app user.
func (c *Client) GetCredentials(ctx context.Context, namespace, secretName string) (Credentials, error) {
	var secret struct {
		Data map[string]string `json:"data"`
	}
	path := fmt.Sprintf("/api/v1/namespaces/%s/secrets/%s", url.PathEscape(namespace), url.PathEscape(secretName))
	if err := c.do(ctx, http.MethodGet, path, nil, &secret); err != nil {
		return Credentials{}, err
	}
	decode := func(key string) string {
		value, err := base64.StdEncoding.DecodeString(secret.Data[key])
		if err != nil {
			return ""
		}
		return string(value)
	}
	return Credentials{
		Username: decode("username"),
		Password: decode("password"),
		Host:     decode("host"),
		Port:     decode("port"),
		Database: decode("dbname"),
	}, nil
}

func (c *Client) clustersPath(namespace string) string {
	return fmt.Sprintf("/apis/postgresql.cnpg.io/v1/namespaces/%s/clusters", url.PathEscape(namespace))
}

func (c *Client) clusterPath(namespace, name string) string {
	return c.clustersPath(namespace) + "/" + url.PathEscape(name)
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

// parseGiB reads sizes like "5Gi" into whole GiB. Anything else becomes 0.
func parseGiB(size string) int {
	if !strings.HasSuffix(size, "Gi") {
		return 0
	}
	var value int
	if _, err := fmt.Sscanf(strings.TrimSuffix(size, "Gi"), "%d", &value); err != nil {
		return 0
	}
	return value
}
