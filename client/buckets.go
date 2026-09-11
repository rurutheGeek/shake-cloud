package client

import (
	"context"
	"net/http"
	"net/url"
	"time"
)

// Buckets and S3 keys. The S3 data itself is transferred directly between the
// client and Garage; these calls only manage the bucket and its credentials.

type BucketKey struct {
	KeyID   string `json:"key_id"`
	KeyName string `json:"key_name"`
	Read    bool   `json:"read"`
	Write   bool   `json:"write"`
	Owner   bool   `json:"owner"`
}

type Bucket struct {
	BucketName    string      `json:"bucket_name"`
	AccountID     string      `json:"account_id"`
	OwnerUsername string      `json:"owner_username,omitempty"`
	S3Endpoint    string      `json:"s3_endpoint"`
	S3Region      string      `json:"s3_region"`
	Objects       int64       `json:"objects"`
	Bytes         int64       `json:"bytes"`
	Keys          []BucketKey `json:"keys"`
	CreatedAt     time.Time   `json:"created_at"`
}

type S3Key struct {
	KeyID           string    `json:"key_id"`
	Name            string    `json:"name"`
	AccountID       string    `json:"account_id"`
	OwnerUsername   string    `json:"owner_username,omitempty"`
	CreatedAt       time.Time `json:"created_at"`
	SecretAccessKey string    `json:"secret_access_key,omitempty"`
}

func (c *Client) DescribeBuckets(ctx context.Context) ([]Bucket, error) {
	var out struct {
		Buckets []Bucket `json:"buckets"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/buckets", nil, nil, &out)
	return out.Buckets, err
}

func (c *Client) CreateBucket(ctx context.Context, name string) (Bucket, error) {
	var out struct {
		Bucket Bucket `json:"bucket"`
	}
	err := c.do(ctx, http.MethodPost, "/v1/buckets", nil, map[string]string{"bucket_name": name}, &out)
	return out.Bucket, err
}

func (c *Client) DescribeBucket(ctx context.Context, name string) (Bucket, error) {
	var out struct {
		Bucket Bucket `json:"bucket"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/buckets/"+url.PathEscape(name), nil, nil, &out)
	return out.Bucket, err
}

func (c *Client) DeleteBucket(ctx context.Context, name string) error {
	return c.do(ctx, http.MethodDelete, "/v1/buckets/"+url.PathEscape(name), nil, nil, nil)
}

// PutBucketKey grants a key permissions on a bucket.
func (c *Client) PutBucketKey(ctx context.Context, name, keyID string, read, write, owner bool) (Bucket, error) {
	var out struct {
		Bucket Bucket `json:"bucket"`
	}
	path := "/v1/buckets/" + url.PathEscape(name) + "/keys/" + url.PathEscape(keyID)
	body := map[string]bool{"read": read, "write": write, "owner": owner}
	err := c.do(ctx, http.MethodPut, path, nil, body, &out)
	return out.Bucket, err
}

func (c *Client) DeleteBucketKey(ctx context.Context, name, keyID string) (Bucket, error) {
	var out struct {
		Bucket Bucket `json:"bucket"`
	}
	path := "/v1/buckets/" + url.PathEscape(name) + "/keys/" + url.PathEscape(keyID)
	err := c.do(ctx, http.MethodDelete, path, nil, nil, &out)
	return out.Bucket, err
}

func (c *Client) ListS3Keys(ctx context.Context) ([]S3Key, error) {
	var out struct {
		S3Keys []S3Key `json:"s3_keys"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/s3-keys", nil, nil, &out)
	return out.S3Keys, err
}

// CreateS3Key returns the key with its secret set, which is the only time the
// secret is available.
func (c *Client) CreateS3Key(ctx context.Context, name string) (S3Key, error) {
	var out struct {
		S3Key S3Key `json:"s3_key"`
	}
	err := c.do(ctx, http.MethodPost, "/v1/s3-keys", nil, map[string]string{"name": name}, &out)
	return out.S3Key, err
}

func (c *Client) DeleteS3Key(ctx context.Context, keyID string) error {
	return c.do(ctx, http.MethodDelete, "/v1/s3-keys/"+url.PathEscape(keyID), nil, nil, nil)
}
