// Package accesskey mints and checks the bearer credentials that Terraform and
// the CLI send as "Authorization: Bearer sca_<id>.<secret>".
//
// Only the ID and a SHA-256 of the secret are stored. The secret is 256 random
// bits, so a fast hash is enough: slow hashes exist to protect guessable
// passwords, and nothing here can be guessed.
package accesskey

import (
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base32"
	"encoding/base64"
	"errors"
	"regexp"
)

// Prefix marks a shake-cloud access key, so secret scanners and people can
// tell it apart from S3 keys and database passwords.
const Prefix = "sca_"

var (
	idEncoding = base32.NewEncoding("abcdefghijklmnopqrstuvwxyz234567").WithPadding(base32.NoPadding)
	// cloud/manage.py mints the bootstrap key in this format; keep the two in step.
	tokenPattern = regexp.MustCompile(`^sca_([a-z2-7]{20})\.([A-Za-z0-9_-]{43})$`)
	idPattern    = regexp.MustCompile(`^[a-z2-7]{20}$`)

	ErrMalformed = errors.New("malformed access key")
)

// Token is a complete credential. Its secret exists only in memory and in the
// one response that hands it to the user.
type Token struct {
	ID     string
	Secret string
}

// New returns a fresh credential: 96 bits of ID and 256 bits of secret.
func New() Token {
	id := make([]byte, 12)
	secret := make([]byte, 32)
	rand.Read(id)
	rand.Read(secret)
	return Token{ID: idEncoding.EncodeToString(id), Secret: base64.RawURLEncoding.EncodeToString(secret)}
}

// Parse accepts exactly the format New produces.
func Parse(s string) (Token, error) {
	m := tokenPattern.FindStringSubmatch(s)
	if m == nil {
		return Token{}, ErrMalformed
	}
	return Token{ID: m[1], Secret: m[2]}, nil
}

// ValidID reports whether s could be an access key ID. Handlers use it to
// reject junk before it reaches the database or the audit log.
func ValidID(s string) bool { return idPattern.MatchString(s) }

func (t Token) String() string { return Prefix + t.ID + "." + t.Secret }

// Hash is the value stored in access_keys.secret_sha256.
func (t Token) Hash() []byte {
	sum := sha256.Sum256([]byte(t.Secret))
	return sum[:]
}

// Matches compares in constant time so response timing does not leak how much
// of a guessed secret was right.
func (t Token) Matches(stored []byte) bool {
	return subtle.ConstantTimeCompare(t.Hash(), stored) == 1
}
