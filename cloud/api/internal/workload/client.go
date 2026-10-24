// Package workload talks to the Kubernetes API for container services: one
// Deployment, and beside it a Secret, a PersistentVolumeClaim and a
// LoadBalancer Service, all named after the service id.
//
// It mirrors the knative client: REST with a bearer token and the cluster CA,
// so the API keeps its small dependency set. Everything that knows the shape
// of these Kubernetes objects stays in this package.
package workload

import (
	"bytes"
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"sort"
	"strings"
	"time"
)

type Client struct {
	baseURL string
	token   string
	http    *http.Client
	// StorageClass is the class of a service's disk (local-path).
	StorageClass string
}

func New(baseURL, caPEM, token string) (*Client, error) {
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM([]byte(caPEM)) {
		return nil, errors.New("workload: the CA is not a PEM certificate")
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
		StorageClass: "local-path",
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

func notFound(err error) bool {
	var apiErr *Error
	return errors.As(err, &apiErr) && apiErr.NotFound()
}

// Spec is everything a service's objects are built from.
type Spec struct {
	Name      string
	Namespace string
	Image     string
	Port      int
	MemoryMiB int
	Env       map[string]string
	Secrets   map[string]string
	DiskGiB   int
	MountPath string
	Labels    map[string]string
}

// State is the live part of a service.
type State struct {
	Ready bool
	// Address is the LoadBalancer's LAN address, empty until MetalLB gives one.
	Address string
}

// Apply creates or replaces every object of a service. The Deployment carries
// a hash of the secrets so that changing only a secret still replaces the pod.
func (c *Client) Apply(ctx context.Context, spec Spec) error {
	if err := c.put(ctx, c.path("api/v1", spec.Namespace, "secrets", spec.Name), secretObject(spec)); err != nil {
		return err
	}
	if spec.DiskGiB > 0 {
		// A claim's size cannot shrink and its class never changes, so it is
		// only created, never replaced.
		err := c.do(ctx, http.MethodPost, c.path("api/v1", spec.Namespace, "persistentvolumeclaims", ""), claimObject(spec, c.StorageClass), nil)
		if err != nil && !conflict(err) {
			return err
		}
	}
	if spec.Port > 0 {
		if err := c.applyService(ctx, spec); err != nil {
			return err
		}
	}
	return c.put(ctx, c.path("apis/apps/v1", spec.Namespace, "deployments", spec.Name), deploymentObject(spec))
}

// Get reads whether the pod is ready and the address it is reached at.
func (c *Client) Get(ctx context.Context, namespace, name string) (State, error) {
	var deployment struct {
		Status struct {
			ReadyReplicas int `json:"readyReplicas"`
		} `json:"status"`
	}
	if err := c.do(ctx, http.MethodGet, c.path("apis/apps/v1", namespace, "deployments", name), nil, &deployment); err != nil {
		if notFound(err) {
			return State{}, nil
		}
		return State{}, err
	}
	state := State{Ready: deployment.Status.ReadyReplicas > 0}
	var service struct {
		Status struct {
			LoadBalancer struct {
				Ingress []struct {
					IP string `json:"ip"`
				} `json:"ingress"`
			} `json:"loadBalancer"`
		} `json:"status"`
	}
	err := c.do(ctx, http.MethodGet, c.path("api/v1", namespace, "services", name), nil, &service)
	switch {
	case notFound(err):
	case err != nil:
		return State{}, err
	case len(service.Status.LoadBalancer.Ingress) > 0:
		state.Address = service.Status.LoadBalancer.Ingress[0].IP
	}
	return state, nil
}

// Secrets reads back the secret values, so that a change that leaves them out
// keeps them. A missing Secret is an empty map.
func (c *Client) Secrets(ctx context.Context, namespace, name string) (map[string]string, error) {
	var secret struct {
		Data map[string][]byte `json:"data"`
	}
	err := c.do(ctx, http.MethodGet, c.path("api/v1", namespace, "secrets", name), nil, &secret)
	if notFound(err) {
		return map[string]string{}, nil
	}
	if err != nil {
		return nil, err
	}
	values := make(map[string]string, len(secret.Data))
	for key, value := range secret.Data {
		values[key] = string(value)
	}
	return values, nil
}

// Delete removes every object of a service, including its disk. Objects that
// are already gone are not an error.
func (c *Client) Delete(ctx context.Context, namespace, name string) error {
	for _, path := range []string{
		c.path("apis/apps/v1", namespace, "deployments", name),
		c.path("api/v1", namespace, "services", name),
		c.path("api/v1", namespace, "persistentvolumeclaims", name),
		c.path("api/v1", namespace, "secrets", name),
	} {
		if err := c.do(ctx, http.MethodDelete, path, nil, nil); err != nil && !notFound(err) {
			return err
		}
	}
	return nil
}

func (c *Client) applyService(ctx context.Context, spec Spec) error {
	path := c.path("api/v1", spec.Namespace, "services", spec.Name)
	object := serviceObject(spec)
	// A Service keeps its clusterIP; a replace must carry the current
	// resourceVersion, so read it first.
	var current struct {
		Metadata struct {
			ResourceVersion string `json:"resourceVersion"`
		} `json:"metadata"`
		Spec struct {
			ClusterIP string `json:"clusterIP"`
		} `json:"spec"`
	}
	err := c.do(ctx, http.MethodGet, path, nil, &current)
	if notFound(err) {
		return c.do(ctx, http.MethodPost, c.path("api/v1", spec.Namespace, "services", ""), object, nil)
	}
	if err != nil {
		return err
	}
	object["metadata"].(map[string]any)["resourceVersion"] = current.Metadata.ResourceVersion
	object["spec"].(map[string]any)["clusterIP"] = current.Spec.ClusterIP
	return c.do(ctx, http.MethodPut, path, object, nil)
}

// put replaces an object, or creates it when it does not exist yet.
func (c *Client) put(ctx context.Context, path string, object map[string]any) error {
	err := c.do(ctx, http.MethodPut, path, object, nil)
	if notFound(err) {
		collection := path[:strings.LastIndex(path, "/")]
		return c.do(ctx, http.MethodPost, collection, object, nil)
	}
	return err
}

func conflict(err error) bool {
	var apiErr *Error
	return errors.As(err, &apiErr) && apiErr.Status == http.StatusConflict
}

func metadata(spec Spec) map[string]any {
	return map[string]any{"name": spec.Name, "namespace": spec.Namespace, "labels": spec.Labels}
}

func secretObject(spec Spec) map[string]any {
	data := map[string]string{}
	for key, value := range spec.Secrets {
		data[key] = value
	}
	return map[string]any{
		"apiVersion": "v1", "kind": "Secret", "metadata": metadata(spec),
		"type": "Opaque", "stringData": data,
	}
}

func claimObject(spec Spec, class string) map[string]any {
	return map[string]any{
		"apiVersion": "v1", "kind": "PersistentVolumeClaim", "metadata": metadata(spec),
		"spec": map[string]any{
			"accessModes":      []string{"ReadWriteOnce"},
			"storageClassName": class,
			"resources":        map[string]any{"requests": map[string]any{"storage": fmt.Sprintf("%dGi", spec.DiskGiB)}},
		},
	}
}

func serviceObject(spec Spec) map[string]any {
	return map[string]any{
		"apiVersion": "v1", "kind": "Service", "metadata": metadata(spec),
		"spec": map[string]any{
			"type":     "LoadBalancer",
			"selector": map[string]string{"shakecloud.io/service": spec.Name},
			"ports":    []any{map[string]any{"name": "http", "port": spec.Port, "targetPort": spec.Port}},
		},
	}
}

// SecretsHash is a stable digest of the secret values, used to replace the pod
// when only a secret changes.
func SecretsHash(secrets map[string]string) string {
	keys := make([]string, 0, len(secrets))
	for key := range secrets {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	h := sha256.New()
	for _, key := range keys {
		fmt.Fprintf(h, "%s\x00%s\x00", key, secrets[key])
	}
	return hex.EncodeToString(h.Sum(nil))[:16]
}

func deploymentObject(spec Spec) map[string]any {
	keys := make([]string, 0, len(spec.Env))
	for key := range spec.Env {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	env := []any{}
	for _, key := range keys {
		env = append(env, map[string]any{"name": key, "value": spec.Env[key]})
	}
	secretKeys := make([]string, 0, len(spec.Secrets))
	for key := range spec.Secrets {
		secretKeys = append(secretKeys, key)
	}
	sort.Strings(secretKeys)
	for _, key := range secretKeys {
		env = append(env, map[string]any{"name": key, "valueFrom": map[string]any{
			"secretKeyRef": map[string]any{"name": spec.Name, "key": key},
		}})
	}
	memory := fmt.Sprintf("%dMi", spec.MemoryMiB)
	mounts := []any{map[string]any{"name": "tmp", "mountPath": "/tmp"}}
	volumes := []any{map[string]any{"name": "tmp", "emptyDir": map[string]any{"sizeLimit": "64Mi"}}}
	strategy := "RollingUpdate"
	if spec.DiskGiB > 0 {
		mounts = append(mounts, map[string]any{"name": "data", "mountPath": spec.MountPath})
		volumes = append(volumes, map[string]any{"name": "data",
			"persistentVolumeClaim": map[string]any{"claimName": spec.Name}})
		// A ReadWriteOnce disk cannot be held by the old and new pod at once.
		strategy = "Recreate"
	}
	container := map[string]any{
		"name":  "app",
		"image": spec.Image,
		"env":   env,
		"resources": map[string]any{
			"requests": map[string]any{"memory": memory, "cpu": "50m"},
			"limits":   map[string]any{"memory": memory},
		},
		"volumeMounts": mounts,
		"securityContext": map[string]any{
			"allowPrivilegeEscalation": false,
			"readOnlyRootFilesystem":   true,
			"capabilities":             map[string]any{"drop": []string{"ALL"}},
		},
	}
	if spec.Port > 0 {
		container["ports"] = []any{map[string]any{"containerPort": spec.Port}}
		container["readinessProbe"] = map[string]any{"tcpSocket": map[string]any{"port": spec.Port}, "periodSeconds": 10}
	}
	podLabels := map[string]string{}
	for key, value := range spec.Labels {
		podLabels[key] = value
	}
	return map[string]any{
		"apiVersion": "apps/v1", "kind": "Deployment", "metadata": metadata(spec),
		"spec": map[string]any{
			"replicas": 1,
			"strategy": map[string]any{"type": strategy},
			"selector": map[string]any{"matchLabels": map[string]string{"shakecloud.io/service": spec.Name}},
			"template": map[string]any{
				"metadata": map[string]any{
					"labels":      podLabels,
					"annotations": map[string]string{"shakecloud.io/secrets-hash": SecretsHash(spec.Secrets)},
				},
				"spec": map[string]any{
					"automountServiceAccountToken": false,
					"enableServiceLinks":           false,
					"securityContext": map[string]any{
						"runAsNonRoot": true, "runAsUser": 65534, "runAsGroup": 65534, "fsGroup": 65534,
						"seccompProfile": map[string]any{"type": "RuntimeDefault"},
					},
					"containers": []any{container},
					"volumes":    volumes,
				},
			},
		},
	}
}

func (c *Client) path(group, namespace, resource, name string) string {
	path := fmt.Sprintf("/%s/namespaces/%s/%s", group, url.PathEscape(namespace), resource)
	if name != "" {
		path += "/" + url.PathEscape(name)
	}
	return path
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
