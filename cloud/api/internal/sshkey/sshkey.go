// Package sshkey parses SSH public keys and fingerprints them.
//
// It does this by hand rather than through golang.org/x/crypto/ssh: the only
// things needed are "is this really a public key of a type we accept" and "what
// is its OpenSSH fingerprint", and both are a few lines against the wire
// format. A private key pasted into the public key box must be refused, which
// is the one mistake worth catching loudly.
package sshkey

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/binary"
	"errors"
	"fmt"
	"strings"
)

// Accepted key types. Anything else is refused rather than stored and later
// found not to work; DSA is left out because OpenSSH no longer accepts it.
var accepted = map[string]bool{
	"ssh-ed25519":                        true,
	"sk-ssh-ed25519@openssh.com":         true,
	"ecdsa-sha2-nistp256":                true,
	"ecdsa-sha2-nistp384":                true,
	"ecdsa-sha2-nistp521":                true,
	"sk-ecdsa-sha2-nistp256@openssh.com": true,
	"ssh-rsa":                            true,
	"rsa-sha2-256":                       true,
	"rsa-sha2-512":                       true,
}

// Key is a parsed public key.
type Key struct {
	// Type is the algorithm name, e.g. "ssh-ed25519".
	Type string
	// Text is the normalised "type base64 comment" line, which is what goes into
	// an instance's cloud-init configuration.
	Text string
	// Fingerprint is OpenSSH's SHA256:… form, the same string `ssh-keygen -lf`
	// prints, so a user can compare it against their own key.
	Fingerprint string
	Comment     string
}

// Parse reads one public key line.
func Parse(line string) (Key, error) {
	line = strings.TrimSpace(strings.ReplaceAll(line, "\r", ""))
	if strings.Contains(line, "PRIVATE KEY") {
		return Key{}, errors.New("that is a private key; paste the public one (the .pub file)")
	}
	if i := strings.IndexAny(line, "\n"); i >= 0 {
		return Key{}, errors.New("give one key on one line")
	}
	fields := strings.Fields(line)
	if len(fields) < 2 {
		return Key{}, errors.New(`a public key looks like "ssh-ed25519 AAAA… comment"`)
	}
	keyType, encoded := fields[0], fields[1]
	if !accepted[keyType] {
		return Key{}, fmt.Errorf("unsupported key type %q", keyType)
	}
	blob, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil {
		return Key{}, errors.New("the key's base64 part is not valid")
	}
	// The blob starts with its own algorithm name. A line claiming one type
	// while carrying another would fingerprint as something the user did not
	// paste, so the two have to agree.
	embedded, err := firstString(blob)
	if err != nil {
		return Key{}, err
	}
	if embedded != keyType {
		return Key{}, fmt.Errorf("the key says %q but contains %q", keyType, embedded)
	}
	sum := sha256.Sum256(blob)
	key := Key{
		Type:        keyType,
		Comment:     strings.Join(fields[2:], " "),
		Fingerprint: "SHA256:" + base64.RawStdEncoding.EncodeToString(sum[:]),
	}
	key.Text = strings.TrimSpace(keyType + " " + encoded + " " + key.Comment)
	return key, nil
}

// firstString reads the length-prefixed algorithm name at the start of a key blob.
func firstString(blob []byte) (string, error) {
	if len(blob) < 4 {
		return "", errors.New("the key is too short to be a public key")
	}
	length := binary.BigEndian.Uint32(blob[:4])
	if length == 0 || uint64(length) > uint64(len(blob)-4) {
		return "", errors.New("the key's contents are malformed")
	}
	return string(blob[4 : 4+length]), nil
}
