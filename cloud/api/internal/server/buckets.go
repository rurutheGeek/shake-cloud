package server

import (
	"errors"
	"net/http"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/compute"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

// Buckets and S3 keys. Like security groups they are private to their account:
// a bucket's keys and contents are the owner's business. admins see and
// may change every account's.

type bucketKeyBody struct {
	KeyID   string `json:"key_id"`
	KeyName string `json:"key_name"`
	Read    bool   `json:"read"`
	Write   bool   `json:"write"`
	Owner   bool   `json:"owner"`
}

type bucketBody struct {
	BucketName    string          `json:"bucket_name"`
	AccountID     string          `json:"account_id"`
	OwnerUsername string          `json:"owner_username,omitempty"`
	S3Endpoint    string          `json:"s3_endpoint"`
	S3Region      string          `json:"s3_region"`
	Objects       int64           `json:"objects"`
	Bytes         int64           `json:"bytes"`
	Keys          []bucketKeyBody `json:"keys"`
	CreatedAt     time.Time       `json:"created_at"`
}

type s3KeyBody struct {
	KeyID           string    `json:"key_id"`
	Name            string    `json:"name"`
	AccountID       string    `json:"account_id"`
	OwnerUsername   string    `json:"owner_username,omitempty"`
	CreatedAt       time.Time `json:"created_at"`
	SecretAccessKey string    `json:"secret_access_key,omitempty"`
}

func (c *call) mayTouchBucket(b db.Bucket) bool {
	return c.principal.account.IsAdmin || b.AccountID == c.principal.account.ID
}

func (c *call) mayTouchS3Key(k db.S3Key) bool {
	return c.principal.account.IsAdmin || k.AccountID == c.principal.account.ID
}

func bucketJSON(service *compute.Service, status compute.BucketStatus) bucketBody {
	body := bucketBody{
		BucketName: status.Bucket.Name, AccountID: status.Bucket.AccountID,
		OwnerUsername: status.Bucket.OwnerUsername, S3Endpoint: service.S3Endpoint,
		S3Region: service.S3Region, Objects: status.Objects, Bytes: status.Bytes,
		Keys: []bucketKeyBody{}, CreatedAt: status.Bucket.CreatedAt.UTC(),
	}
	for _, key := range status.Keys {
		body.Keys = append(body.Keys, bucketKeyBody{
			KeyID: key.KeyID, KeyName: key.KeyName, Read: key.Read, Write: key.Write, Owner: key.Owner,
		})
	}
	return body
}

func s3KeyJSON(k db.S3Key) s3KeyBody {
	return s3KeyBody{
		KeyID: k.KeyID, Name: k.Name, AccountID: k.AccountID,
		OwnerUsername: "", CreatedAt: k.CreatedAt.UTC(),
	}
}

func (s *Server) bucketRefused(w http.ResponseWriter, r *http.Request, c *call, id string, err error) {
	if refusal := (*compute.Error)(nil); errors.As(err, &refusal) {
		event := c.event(refusal.Code, nil)
		event.ResourceID = id
		s.recordDenied(r.Context(), event)
	}
	s.computeError(w, r, err)
}

func bucketAudit(r *http.Request, c *call, tx pgx.Tx, bucket db.Bucket, detail map[string]any) error {
	if detail == nil {
		detail = map[string]any{}
	}
	detail["owner_account_id"] = bucket.AccountID
	detail["bucket_name"] = bucket.Name
	event := c.event("", detail)
	event.ResourceID = bucket.Name
	return db.RecordAudit(r.Context(), tx, event)
}

func (s *Server) describeBuckets(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	scope := ""
	if !c.principal.account.IsAdmin {
		scope = c.principal.account.ID
	}
	statuses, err := service.ListBuckets(r.Context(), scope)
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	body := make([]bucketBody, 0, len(statuses))
	for _, status := range statuses {
		if !c.mayTouchBucket(status.Bucket) {
			continue
		}
		body = append(body, bucketJSON(service, status))
	}
	writeJSON(w, http.StatusOK, map[string]any{"buckets": body})
}

func (s *Server) createBucket(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	var request struct {
		BucketName string `json:"bucket_name"`
	}
	if !decodeJSON(w, r, &request) {
		return
	}
	bucket, created, err := service.CreateBucket(r.Context(), c.principal.account.ID, request.BucketName,
		func(tx pgx.Tx, b db.Bucket) error { return bucketAudit(r, c, tx, b, nil) })
	if err != nil {
		s.bucketRefused(w, r, c, request.BucketName, err)
		return
	}
	status, err := service.GetBucket(r.Context(), bucket.Name, c.mayTouchBucket)
	if err != nil {
		s.computeError(w, r, err)
		return
	}
	statusCode := http.StatusOK
	if created {
		statusCode = http.StatusCreated
	}
	writeJSON(w, statusCode, map[string]any{"bucket": bucketJSON(service, status)})
}

func (s *Server) describeBucket(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	name := r.PathValue("bucket_name")
	status, err := service.GetBucket(r.Context(), name, c.mayTouchBucket)
	if err != nil {
		s.bucketRefused(w, r, c, name, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"bucket": bucketJSON(service, status)})
}

func (s *Server) deleteBucket(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	name := r.PathValue("bucket_name")
	err := service.DeleteBucket(r.Context(), name, c.mayTouchBucket,
		func(tx pgx.Tx, b db.Bucket) error { return bucketAudit(r, c, tx, b, nil) })
	if err != nil {
		s.bucketRefused(w, r, c, name, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) listS3Keys(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	scope := ""
	if !c.principal.account.IsAdmin {
		scope = c.principal.account.ID
	}
	keys, err := service.ListS3Keys(r.Context(), scope)
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	body := make([]s3KeyBody, 0, len(keys))
	for _, key := range keys {
		if c.mayTouchS3Key(key) {
			body = append(body, s3KeyJSON(key))
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"s3_keys": body})
}

func (s *Server) createS3Key(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	var request struct {
		Name string `json:"name"`
	}
	if !decodeJSON(w, r, &request) {
		return
	}
	key, secret, err := service.CreateS3Key(r.Context(), c.principal.account.ID, request.Name,
		func(tx pgx.Tx, k db.S3Key) error {
			detail := map[string]any{"owner_account_id": k.AccountID, "name": k.Name}
			event := c.event("", detail)
			event.ResourceID = k.KeyID
			return db.RecordAudit(r.Context(), tx, event)
		})
	if err != nil {
		s.bucketRefused(w, r, c, request.Name, err)
		return
	}
	body := s3KeyJSON(key)
	body.SecretAccessKey = secret
	writeJSON(w, http.StatusCreated, map[string]any{"s3_key": body})
}

func (s *Server) deleteS3Key(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	keyID := r.PathValue("key_id")
	err := service.DeleteS3Key(r.Context(), keyID, c.mayTouchS3Key,
		func(tx pgx.Tx, k db.S3Key) error {
			event := c.event("", map[string]any{"owner_account_id": k.AccountID, "name": k.Name})
			event.ResourceID = k.KeyID
			return db.RecordAudit(r.Context(), tx, event)
		})
	if err != nil {
		s.bucketRefused(w, r, c, keyID, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) setBucketPermission(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	name, keyID := r.PathValue("bucket_name"), r.PathValue("key_id")
	var request struct {
		Read  bool `json:"read"`
		Write bool `json:"write"`
		Owner bool `json:"owner"`
	}
	if !decodeJSON(w, r, &request) {
		return
	}
	status, err := service.SetBucketPermission(r.Context(), name, keyID, request.Read, request.Write, request.Owner,
		c.mayTouchBucket, func(tx pgx.Tx, b db.Bucket, k db.S3Key) error {
			return bucketAudit(r, c, tx, b, map[string]any{"key_id": k.KeyID, "read": request.Read, "write": request.Write, "owner": request.Owner})
		})
	if err != nil {
		s.bucketRefused(w, r, c, name, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"bucket": bucketJSON(service, status)})
}

func (s *Server) revokeBucketPermission(w http.ResponseWriter, r *http.Request, c *call) {
	service := s.computeService(w, r)
	if service == nil {
		return
	}
	name, keyID := r.PathValue("bucket_name"), r.PathValue("key_id")
	status, err := service.RevokeBucketPermission(r.Context(), name, keyID, c.mayTouchBucket,
		func(tx pgx.Tx, b db.Bucket, k db.S3Key) error {
			return bucketAudit(r, c, tx, b, map[string]any{"key_id": k.KeyID, "revoked": true})
		})
	if err != nil {
		s.bucketRefused(w, r, c, name, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"bucket": bucketJSON(service, status)})
}
