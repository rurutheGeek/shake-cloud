package db

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5"
)

// Credential types recorded with each audit event.
const (
	CredentialNone      = "none"
	CredentialSession   = "session"
	CredentialAccessKey = "access_key"
)

// AuditEvent mirrors a row of audit_events. Empty strings are stored as NULL.
type AuditEvent struct {
	EventID         int64
	EventTime       time.Time
	EventName       string
	AccountID       string
	AccessKeyID     string
	CredentialType  string
	SourceIPAddress string
	UserAgent       string
	RequestID       string
	ResourceID      string
	ErrorCode       string
	Detail          map[string]any
}

const maxUserAgent = 512

func RecordAudit(ctx context.Context, q Querier, e AuditEvent) error {
	if e.Detail == nil {
		e.Detail = map[string]any{}
	}
	if len(e.UserAgent) > maxUserAgent {
		e.UserAgent = e.UserAgent[:maxUserAgent]
	}
	_, err := q.Exec(ctx, `INSERT INTO audit_events
		(event_name, account_id, access_key_id, credential_type, source_ip_address,
		 user_agent, request_id, resource_id, error_code, detail)
		VALUES ($1, nullif($2::text, ''), nullif($3::text, ''), $4, $5, $6, $7,
		        nullif($8::text, ''), nullif($9::text, ''), $10)`,
		e.EventName, e.AccountID, e.AccessKeyID, e.CredentialType, e.SourceIPAddress,
		e.UserAgent, e.RequestID, e.ResourceID, e.ErrorCode, e.Detail)
	return err
}

// AuditFilter narrows LookupAuditEvents. Zero values match everything.
// BeforeID pages backwards: pass the last EventID of the previous page.
type AuditFilter struct {
	AccountID   string
	AccessKeyID string
	EventName   string
	BeforeID    int64
	Limit       int
}

// LookupAuditEvents returns matching events, newest first.
func LookupAuditEvents(ctx context.Context, q Querier, f AuditFilter) ([]AuditEvent, error) {
	rows, err := q.Query(ctx, `SELECT event_id, event_time, event_name, coalesce(account_id, ''),
			coalesce(access_key_id, ''), credential_type, source_ip_address, user_agent, request_id,
			coalesce(resource_id, ''), coalesce(error_code, ''), detail
		FROM audit_events
		WHERE ($1::text = '' OR account_id = $1)
		  AND ($2::text = '' OR access_key_id = $2)
		  AND ($3::text = '' OR event_name = $3)
		  AND ($4::bigint = 0 OR event_id < $4)
		ORDER BY event_id DESC
		LIMIT $5`, f.AccountID, f.AccessKeyID, f.EventName, f.BeforeID, f.Limit)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (AuditEvent, error) {
		var e AuditEvent
		err := row.Scan(&e.EventID, &e.EventTime, &e.EventName, &e.AccountID, &e.AccessKeyID,
			&e.CredentialType, &e.SourceIPAddress, &e.UserAgent, &e.RequestID, &e.ResourceID,
			&e.ErrorCode, &e.Detail)
		return e, err
	})
}
