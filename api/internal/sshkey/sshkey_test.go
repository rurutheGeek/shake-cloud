package sshkey

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"strings"
	"testing"
)

// beginPrivateKey is assembled at run time rather than written out, because
// tools/check-publication.py refuses a tracked file containing the literal PEM
// marker — which is the very thing these tests feed in to prove it is refused.
var beginPrivateKey = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"

// ed25519Line builds a real public key line without depending on this package,
// so the test agrees with the wire format rather than with the code under test.
func ed25519Line(t *testing.T, comment string) (line string, blob []byte) {
	t.Helper()
	material := make([]byte, 32)
	if _, err := rand.Read(material); err != nil {
		t.Fatal(err)
	}
	blob = append(blob, 0, 0, 0, 11)
	blob = append(blob, "ssh-ed25519"...)
	blob = append(blob, 0, 0, 0, 32)
	blob = append(blob, material...)
	line = "ssh-ed25519 " + base64.StdEncoding.EncodeToString(blob) + " " + comment
	return line, blob
}

func TestParseFingerprintsTheKeyBlobLikeOpenSSH(t *testing.T) {
	line, blob := ed25519Line(t, "alice@laptop")
	key, err := Parse("  " + line + "\n")
	if err != nil {
		t.Fatal(err)
	}
	// OpenSSH hashes the decoded blob, not the line, and prints it unpadded.
	sum := sha256.Sum256(blob)
	want := "SHA256:" + base64.RawStdEncoding.EncodeToString(sum[:])
	if key.Fingerprint != want {
		t.Errorf("fingerprint = %q, want %q", key.Fingerprint, want)
	}
	if strings.Contains(key.Fingerprint, "=") {
		t.Error("the fingerprint is padded; ssh-keygen prints it without padding")
	}
	if key.Type != "ssh-ed25519" || key.Comment != "alice@laptop" || key.Text != line {
		t.Errorf("key = %+v", key)
	}
}

func TestParseRefusesWhatWouldNotWork(t *testing.T) {
	line, _ := ed25519Line(t, "alice")
	encoded := strings.Fields(line)[1]
	for name, input := range map[string]string{
		"empty":              "",
		"no key material":    "ssh-ed25519",
		"a private key":      beginPrivateKey + "\nabc\n-----END OPENSSH PRIVATE KEY-----",
		"an unknown type":    "ssh-dss " + encoded,
		"bad base64":         "ssh-ed25519 not!base64",
		"a type that lies":   "ssh-rsa " + encoded,
		"two keys in one":    line + "\n" + line,
		"a truncated blob":   "ssh-ed25519 " + base64.StdEncoding.EncodeToString([]byte{0, 0}),
		"a length that lies": "ssh-ed25519 " + base64.StdEncoding.EncodeToString([]byte{0, 0, 0, 200, 'x'}),
	} {
		if _, err := Parse(input); err == nil {
			t.Errorf("%s: accepted", name)
		}
	}
}

func TestAPrivateKeyIsNamedAsSuch(t *testing.T) {
	_, err := Parse(beginPrivateKey)
	if err == nil || !strings.Contains(err.Error(), "private key") {
		t.Fatalf("err = %v; the message should say what the user pasted", err)
	}
}
