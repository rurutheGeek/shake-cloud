package db

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"math/big"
	"time"

	"github.com/jackc/pgx/v5"
)

const (
	KindUser      = "user"
	KindBootstrap = "bootstrap"
)

type Account struct {
	ID          string
	Kind        string
	Username    string
	Email       string
	IsAdmin     bool
	CreatedAt   time.Time
	LastLoginAt *time.Time
}

// ErrEmailConflict means an unknown Authentik subject carried the email of an
// existing account.
var ErrEmailConflict = errors.New("the email address already belongs to another account")

const accountColumns = `a.id, a.kind, a.username, a.email, a.is_admin, a.created_at, a.last_login_at`

func accountFields(a *Account) []any {
	return []any{&a.ID, &a.Kind, &a.Username, &a.Email, &a.IsAdmin, &a.CreatedAt, &a.LastLoginAt}
}

func scanAccount(row pgx.Row) (Account, error) {
	var a Account
	return a, noRows(row.Scan(accountFields(&a)...))
}

// GetAccount reads one account by ID, for a caller that must name an owner,
// such as an administrator adopting a VM for someone.
func GetAccount(ctx context.Context, q Querier, id string) (Account, error) {
	return scanAccount(q.QueryRow(ctx, `SELECT `+accountColumns+` FROM accounts a WHERE a.id = $1`, id))
}

// RecordLogin creates or refreshes the account for an Authentik subject and
// reports whether it was created. Group membership is re-read on every login,
// so removing someone from cloud-admins takes effect at their next login.
//
// A subject never seen before that carries a known email address is refused
// rather than given a second account. It usually means the Authentik user was
// deleted and recreated; silently splitting their resources across two
// accounts is worse than making an administrator look.
func RecordLogin(ctx context.Context, q Querier, subject, username, email string, isAdmin bool) (Account, bool, error) {
	account, err := scanAccount(q.QueryRow(ctx, `UPDATE accounts AS a
		SET username = $2, email = $3, is_admin = $4, last_login_at = now()
		WHERE a.subject = $1 RETURNING `+accountColumns, subject, username, email, isAdmin))
	switch {
	case err == nil:
		return account, false, nil
	case isUniqueViolation(err, "accounts_user_email"):
		return Account{}, false, ErrEmailConflict
	case !errors.Is(err, ErrNotFound):
		return Account{}, false, err
	}
	for range 5 {
		account, err = scanAccount(q.QueryRow(ctx, `INSERT INTO accounts AS a
			(id, kind, subject, username, email, is_admin, last_login_at)
			VALUES ($1, 'user', $2, $3, $4, $5, now())
			ON CONFLICT (id) DO NOTHING RETURNING `+accountColumns,
			newAccountID(), subject, username, email, isAdmin))
		switch {
		case err == nil:
			return account, true, nil
		case isUniqueViolation(err, "accounts_user_email"):
			return Account{}, false, ErrEmailConflict
		case !errors.Is(err, ErrNotFound):
			return Account{}, false, err
		}
		// The random ID collided; draw again.
	}
	return Account{}, false, errors.New("could not allocate an account ID")
}

// BootstrapAccount returns the account that owns the bootstrap key, or ErrNotFound.
func BootstrapAccount(ctx context.Context, q Querier) (Account, error) {
	return scanAccount(q.QueryRow(ctx, `SELECT `+accountColumns+` FROM accounts a WHERE a.kind = 'bootstrap'`))
}

// EnsureBootstrapAccount returns the bootstrap account, creating it on first use.
func EnsureBootstrapAccount(ctx context.Context, q Querier) (Account, error) {
	for range 5 {
		account, err := BootstrapAccount(ctx, q)
		if !errors.Is(err, ErrNotFound) {
			return account, err
		}
		if _, err := q.Exec(ctx, `INSERT INTO accounts (id, kind, username, is_admin)
			VALUES ($1, 'bootstrap', 'bootstrap-admin', true) ON CONFLICT DO NOTHING`, newAccountID()); err != nil {
			return Account{}, err
		}
	}
	return Account{}, errors.New("could not create the bootstrap account")
}

// LockAccount serialises changes that depend on counting an account's rows.
func LockAccount(ctx context.Context, q Querier, id string) error {
	var locked string
	return noRows(q.QueryRow(ctx, `SELECT id FROM accounts WHERE id = $1 FOR UPDATE`, id).Scan(&locked))
}

func newAccountID() string {
	n, err := rand.Int(rand.Reader, big.NewInt(1_000_000_000_000))
	if err != nil {
		panic(err)
	}
	return fmt.Sprintf("%012d", n)
}
