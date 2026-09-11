// Package garage is a small client for Garage's administration API (v2).
//
// The cloud API uses it to manage buckets and S3 access keys on behalf of
// accounts. It is deliberately thin: the admin API's shapes are the contract,
// and cloud/openapi/shakecloud.yaml describes what the cloud API exposes.
package garage

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

// Client talks to one Garage node's admin API.
type Client struct {
	baseURL string
	token   string
	http    *http.Client
}

func New(baseURL, token string) *Client {
	return &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		token:   token,
		http:    &http.Client{Timeout: 30 * time.Second},
	}
}

// Error is a non-2xx answer from Garage.
type Error struct {
	Status int
	Body   string
}

func (e *Error) Error() string {
	return fmt.Sprintf("garage admin API returned HTTP %d: %s", e.Status, e.Body)
}

// NotFound reports a 404, so a deleted bucket or key is not treated as a failure.
func (e *Error) NotFound() bool { return e.Status == http.StatusNotFound }

// Permissions are what a key may do with a bucket.
type Permissions struct {
	Read  bool `json:"read"`
	Write bool `json:"write"`
	Owner bool `json:"owner"`
}

// Bucket is one entry of ListBuckets.
type Bucket struct {
	ID            string    `json:"id"`
	Created       time.Time `json:"created"`
	GlobalAliases []string  `json:"globalAliases"`
}

// BucketKey is an access key with its permissions on a bucket.
type BucketKey struct {
	AccessKeyID string      `json:"accessKeyId"`
	Name        string      `json:"name"`
	Permissions Permissions `json:"permissions"`
}

// BucketInfo is GetBucketInfo's answer.
type BucketInfo struct {
	ID            string      `json:"id"`
	Created       time.Time   `json:"created"`
	GlobalAliases []string    `json:"globalAliases"`
	Keys          []BucketKey `json:"keys"`
	Objects       int64       `json:"objects"`
	Bytes         int64       `json:"bytes"`
}

// KeyListItem is one entry of ListKeys.
type KeyListItem struct {
	ID      string `json:"id"`
	Name    string `json:"name"`
	Expired bool   `json:"expired"`
}

// KeyInfo is GetKeyInfo's (and CreateKey's) answer. SecretAccessKey is only set
// by CreateKey; Garage never shows it again.
type KeyInfo struct {
	AccessKeyID     string `json:"accessKeyId"`
	Name            string `json:"name"`
	SecretAccessKey string `json:"secretAccessKey,omitempty"`
}

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
		return &Error{Status: response.StatusCode, Body: strings.TrimSpace(string(data))}
	}
	if out != nil && len(bytes.TrimSpace(data)) > 0 {
		if err := json.Unmarshal(data, out); err != nil {
			return fmt.Errorf("decoding %s %s: %w", method, path, err)
		}
	}
	return nil
}

// CreateBucket creates a bucket with a global alias and returns its info.
func (c *Client) CreateBucket(ctx context.Context, name string) (BucketInfo, error) {
	var info BucketInfo
	err := c.do(ctx, http.MethodPost, "/v2/CreateBucket", nil, map[string]string{"globalAlias": name}, &info)
	return info, err
}

func (c *Client) ListBuckets(ctx context.Context) ([]Bucket, error) {
	var buckets []Bucket
	err := c.do(ctx, http.MethodGet, "/v2/ListBuckets", nil, nil, &buckets)
	return buckets, err
}

// BucketInfo looks a bucket up by its global alias.
func (c *Client) BucketInfo(ctx context.Context, globalAlias string) (BucketInfo, error) {
	var info BucketInfo
	query := url.Values{"globalAlias": {globalAlias}}
	err := c.do(ctx, http.MethodGet, "/v2/GetBucketInfo", query, nil, &info)
	return info, err
}

func (c *Client) DeleteBucket(ctx context.Context, id string) error {
	return c.do(ctx, http.MethodPost, "/v2/DeleteBucket", url.Values{"id": {id}}, nil, nil)
}

// CreateKey makes an S3 access key and returns its secret, which is shown once.
func (c *Client) CreateKey(ctx context.Context, name string) (KeyInfo, error) {
	var info KeyInfo
	body := map[string]any{"name": name, "allow": map[string]bool{"createBucket": false}}
	err := c.do(ctx, http.MethodPost, "/v2/CreateKey", nil, body, &info)
	return info, err
}

func (c *Client) ListKeys(ctx context.Context) ([]KeyListItem, error) {
	var keys []KeyListItem
	err := c.do(ctx, http.MethodGet, "/v2/ListKeys", nil, nil, &keys)
	return keys, err
}

func (c *Client) GetKeyInfo(ctx context.Context, id string) (KeyInfo, error) {
	var info KeyInfo
	err := c.do(ctx, http.MethodGet, "/v2/GetKeyInfo", url.Values{"id": {id}}, nil, &info)
	return info, err
}

func (c *Client) DeleteKey(ctx context.Context, id string) error {
	return c.do(ctx, http.MethodPost, "/v2/DeleteKey", url.Values{"id": {id}}, nil, nil)
}

// AllowBucketKey grants permissions to a key on a bucket.
func (c *Client) AllowBucketKey(ctx context.Context, bucketID, keyID string, permissions Permissions) error {
	body := map[string]any{"bucketId": bucketID, "accessKeyId": keyID, "permissions": permissions}
	return c.do(ctx, http.MethodPost, "/v2/AllowBucketKey", nil, body, nil)
}

// DenyBucketKey removes permissions from a key on a bucket.
func (c *Client) DenyBucketKey(ctx context.Context, bucketID, keyID string, permissions Permissions) error {
	body := map[string]any{"bucketId": bucketID, "accessKeyId": keyID, "permissions": permissions}
	return c.do(ctx, http.MethodPost, "/v2/DenyBucketKey", nil, body, nil)
}
