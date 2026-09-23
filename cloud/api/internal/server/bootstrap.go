package server

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

// ReconcileBootstrapKey makes the database agree with the bootstrap key file.
//
// The key lets an administrator call the API before the portal is finished and
// while Authentik is down. The file is the switch:
//
//   - a key in the file is registered to the bootstrap-admin account;
//   - a different key replaces it, and the old one is revoked;
//   - an empty or unconfigured file revokes it.
//
// A key deleted through the API stays deleted even if the file still holds it,
// so a restart cannot undo an emergency revocation.
func (s *Server) ReconcileBootstrapKey(ctx context.Context) error {
	token := s.cfg.BootstrapKey
	return pgx.BeginFunc(ctx, s.pool, func(tx pgx.Tx) error {
		if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext('shakecloud.bootstrap'))`); err != nil {
			return err
		}
		var account db.Account
		var err error
		if token == nil {
			account, err = db.BootstrapAccount(ctx, tx)
			if errors.Is(err, db.ErrNotFound) {
				return nil
			}
		} else {
			account, err = db.EnsureBootstrapAccount(ctx, tx)
		}
		if err != nil {
			return err
		}
		record := func(name, keyID, reason string) error {
			return db.RecordAudit(ctx, tx, db.AuditEvent{
				EventName: name, AccountID: account.ID, CredentialType: db.CredentialNone,
				SourceIPAddress: "local", RequestID: "startup", ResourceID: keyID,
				Detail: map[string]any{"reason": reason},
			})
		}

		keep := ""
		if token != nil {
			keep = token.ID
			credential, err := db.LookupAccessKey(ctx, tx, token.ID)
			switch {
			case errors.Is(err, db.ErrNotFound):
				if _, err := db.InsertAccessKey(ctx, tx, account.ID, *token, "bootstrap admin key (SHAKECLOUD_BOOTSTRAP_KEY_FILE)", db.KeyScopeReadWrite, nil); err != nil {
					return err
				}
				if err := record("CreateAccessKey", token.ID, "bootstrap key file"); err != nil {
					return err
				}
				s.log.Info("bootstrap key registered", "access_key_id", token.ID)
			case err != nil:
				return err
			case credential.Account.ID != account.ID || !token.Matches(credential.SecretSHA256):
				return errors.New("the bootstrap key file does not match the stored key with the same ID; refusing to start")
			case credential.Key.RevokedAt != nil:
				s.log.Warn("the bootstrap key was deleted through the API and stays inactive; run manage.py rotate-bootstrap-key for a new one",
					"access_key_id", token.ID)
			}
		}

		reason := "bootstrap key replaced"
		if token == nil {
			reason = "bootstrap key file is empty"
		}
		revoked, err := db.RevokeAccountKeysExcept(ctx, tx, account.ID, keep)
		if err != nil {
			return err
		}
		for _, id := range revoked {
			if err := record("DeleteAccessKey", id, reason); err != nil {
				return err
			}
			s.log.Info("bootstrap key revoked", "access_key_id", id, "reason", reason)
		}
		return nil
	})
}
