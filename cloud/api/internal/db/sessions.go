package db

import (
	"context"
	"time"
)

func CreateSession(ctx context.Context, q Querier, accountID string, tokenSHA256 []byte, expiresAt time.Time) error {
	_, err := q.Exec(ctx, `INSERT INTO sessions (token_sha256, account_id, expires_at) VALUES ($1, $2, $3)`,
		tokenSHA256, accountID, expiresAt)
	return err
}

// LookupSession returns the account behind a live session.
func LookupSession(ctx context.Context, q Querier, tokenSHA256 []byte) (Account, error) {
	return scanAccount(q.QueryRow(ctx, `SELECT `+accountColumns+`
		FROM sessions s JOIN accounts a ON a.id = s.account_id
		WHERE s.token_sha256 = $1 AND s.expires_at > now()`, tokenSHA256))
}

func DeleteSession(ctx context.Context, q Querier, tokenSHA256 []byte) error {
	_, err := q.Exec(ctx, `DELETE FROM sessions WHERE token_sha256 = $1`, tokenSHA256)
	return err
}

func CreateLoginAttempt(ctx context.Context, q Querier, stateSHA256 []byte, nonce, codeVerifier string, expiresAt time.Time) error {
	_, err := q.Exec(ctx, `INSERT INTO login_attempts (state_sha256, nonce, code_verifier, expires_at)
		VALUES ($1, $2, $3, $4)`, stateSHA256, nonce, codeVerifier, expiresAt)
	return err
}

// TakeLoginAttempt consumes a login attempt, so a state value works only once.
func TakeLoginAttempt(ctx context.Context, q Querier, stateSHA256 []byte) (nonce, codeVerifier string, err error) {
	err = q.QueryRow(ctx, `DELETE FROM login_attempts WHERE state_sha256 = $1 AND expires_at > now()
		RETURNING nonce, code_verifier`, stateSHA256).Scan(&nonce, &codeVerifier)
	return nonce, codeVerifier, noRows(err)
}

// DeleteExpired removes sessions and login attempts past their expiry.
func DeleteExpired(ctx context.Context, q Querier) error {
	if _, err := q.Exec(ctx, `DELETE FROM sessions WHERE expires_at <= now()`); err != nil {
		return err
	}
	_, err := q.Exec(ctx, `DELETE FROM login_attempts WHERE expires_at <= now()`)
	return err
}
