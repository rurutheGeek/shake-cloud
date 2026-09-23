// Package client is a small, typed client for the shake-cloud JSON API.
//
// It is the shared bottom of the shakecloud CLI and, later, the Terraform
// provider. It speaks exactly what cloud/openapi/shakecloud.yaml documents and
// authenticates with an access key:
//
//	Authorization: Bearer sca_<key-id>.<secret>
//
// The API is not the AWS wire protocol, so this is not the AWS SDK. Field
// names and lifecycle states are deliberately the same as EC2's, though.
package client

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// DefaultEndpoint is the deployment's public address. Override it with the
// --endpoint flag or SHAKECLOUD_ENDPOINT for another deployment.
const DefaultEndpoint = "https://cloud.apextox.dpdns.org"

// Client calls one shake-cloud API. It is safe to use from multiple goroutines.
type Client struct {
	baseURL    string
	accessKey  string
	httpClient *http.Client
	userAgent  string
}

// New builds a client. An empty endpoint means DefaultEndpoint; an empty
// accessKey means unauthenticated requests, which only the public health and
// login endpoints accept.
func New(endpoint, accessKey string) *Client {
	endpoint = strings.TrimRight(endpoint, "/")
	if endpoint == "" {
		endpoint = DefaultEndpoint
	}
	return &Client{
		baseURL:    endpoint,
		accessKey:  accessKey,
		httpClient: &http.Client{Timeout: 10 * time.Minute},
		userAgent:  "shakecloud-cli",
	}
}

// NewWithUserAgent is New with a caller-chosen User-Agent, so the audit log
// can tell which tool made the request. An empty userAgent keeps the default.
func NewWithUserAgent(endpoint, accessKey, userAgent string) *Client {
	c := New(endpoint, accessKey)
	if userAgent != "" {
		c.userAgent = userAgent
	}
	return c
}

// Endpoint is the base URL the client calls.
func (c *Client) Endpoint() string { return c.baseURL }

// APIError is a refusal from the API: a non-2xx response with the error body
// the OpenAPI document describes.
type APIError struct {
	Status    int
	Code      string
	Message   string
	RequestID string
}

func (e *APIError) Error() string {
	return fmt.Sprintf("%s: %s (HTTP %d, request %s)", e.Code, e.Message, e.Status, e.RequestID)
}

// NotFound reports whether the refusal was a 404, so callers can tell "gone"
// from "the request was wrong".
func (e *APIError) NotFound() bool { return e.Status == http.StatusNotFound }

func (c *Client) do(ctx context.Context, method, path string, query url.Values, body, out any) error {
	endpoint := c.baseURL + path
	if len(query) > 0 {
		endpoint += "?" + query.Encode()
	}
	var reader io.Reader
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return err
		}
		reader = bytes.NewReader(encoded)
	}
	request, err := http.NewRequestWithContext(ctx, method, endpoint, reader)
	if err != nil {
		return err
	}
	request.Header.Set("User-Agent", c.userAgent)
	request.Header.Set("Accept", "application/json")
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	if c.accessKey != "" {
		request.Header.Set("Authorization", "Bearer "+c.accessKey)
	}
	response, err := c.httpClient.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	// Large enough for any JSON answer this API gives; images are streamed, not
	// read through here.
	data, err := io.ReadAll(io.LimitReader(response.Body, 16<<20))
	if err != nil {
		return err
	}
	if response.StatusCode >= 400 {
		return parseAPIError(response.StatusCode, data)
	}
	if out != nil && len(bytes.TrimSpace(data)) > 0 {
		if err := json.Unmarshal(data, out); err != nil {
			return fmt.Errorf("decoding %s %s: %w", method, path, err)
		}
	}
	return nil
}

func parseAPIError(status int, data []byte) *APIError {
	var envelope struct {
		Error struct {
			Code    string `json:"code"`
			Message string `json:"message"`
		} `json:"error"`
		RequestID string `json:"request_id"`
	}
	_ = json.Unmarshal(data, &envelope)
	message := envelope.Error.Message
	if message == "" {
		message = strings.TrimSpace(string(data))
	}
	return &APIError{Status: status, Code: envelope.Error.Code, Message: message, RequestID: envelope.RequestID}
}
