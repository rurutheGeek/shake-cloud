package server

import (
	"crypto/rand"
	"encoding/base64"
	"net/http"
	"strings"
	"testing"
)

// beginPrivateKey is assembled at run time rather than written out, because
// tools/check-publication.py refuses a tracked file containing the literal PEM
// marker — which is the very thing this test pastes in to prove it is refused.
var beginPrivateKey = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"

// publicKeyLine builds a valid ed25519 public key line the way OpenSSH writes
// one, so these tests do not depend on the parser they are exercising.
func publicKeyLine(t *testing.T, comment string) string {
	t.Helper()
	material := make([]byte, 32)
	if _, err := rand.Read(material); err != nil {
		t.Fatal(err)
	}
	blob := []byte{0, 0, 0, 11}
	blob = append(blob, "ssh-ed25519"...)
	blob = append(blob, 0, 0, 0, 32)
	blob = append(blob, material...)
	return "ssh-ed25519 " + base64.StdEncoding.EncodeToString(blob) + " " + comment
}

type keyPairEnvelope struct {
	KeyPair keyPairBody `json:"key_pair"`
}

type keyPairList struct {
	KeyPairs []keyPairBody `json:"key_pairs"`
}

// Key pairs need nothing from Proxmox, so they work on a deployment where
// instances are not configured at all.
func TestKeyPairLifecycle(t *testing.T) {
	s := testServer(t, nil)
	_, cookie := session(t, s, "alice", false)
	cookies := []*http.Cookie{cookie}
	line := publicKeyLine(t, "alice@laptop")

	recorder := do(t, s, req{method: "POST", path: "/v1/key-pairs",
		body: map[string]any{"key_name": "laptop", "public_key": line}, cookies: cookies})
	expectStatus(t, recorder, http.StatusCreated)
	created := decode[keyPairEnvelope](t, recorder).KeyPair
	if created.KeyName != "laptop" || !strings.HasPrefix(created.Fingerprint, "SHA256:") {
		t.Fatalf("created: %+v", created)
	}

	listed := do(t, s, req{method: "GET", path: "/v1/key-pairs", cookies: cookies})
	expectStatus(t, listed, http.StatusOK)
	if keys := decode[keyPairList](t, listed).KeyPairs; len(keys) != 1 || keys[0].Fingerprint != created.Fingerprint {
		t.Fatalf("listed: %+v", keys)
	}
	// The key material is not echoed back by the listing.
	if strings.Contains(listed.Body.String(), strings.Fields(line)[1]) {
		t.Fatal("the listing repeats the public key")
	}

	// The same name twice is a conflict, not a silent replacement.
	again := do(t, s, req{method: "POST", path: "/v1/key-pairs",
		body: map[string]any{"key_name": "laptop", "public_key": publicKeyLine(t, "other")}, cookies: cookies})
	expectStatus(t, again, http.StatusConflict)
	if got := decode[errorBody](t, again).Error.Code; got != "InvalidKeyPair.Duplicate" {
		t.Fatalf("code %q", got)
	}

	expectStatus(t, do(t, s, req{method: "DELETE", path: "/v1/key-pairs/laptop", cookies: cookies}), http.StatusNoContent)
	missing := do(t, s, req{method: "DELETE", path: "/v1/key-pairs/laptop", cookies: cookies})
	expectStatus(t, missing, http.StatusNotFound)
	if got := decode[errorBody](t, missing).Error.Code; got != "InvalidKeyPair.NotFound" {
		t.Fatalf("code %q", got)
	}

	events := events(t, s, req{path: "/v1/audit-events?event_name=ImportKeyPair", cookies: cookies})
	if len(events.Events) != 2 || events.Events[0].ErrorCode != "InvalidKeyPair.Duplicate" {
		t.Fatalf("audit: %+v", events.Events)
	}
}

func TestABadKeyIsExplainedRatherThanStored(t *testing.T) {
	s := testServer(t, nil)
	_, cookie := session(t, s, "alice", false)
	cookies := []*http.Cookie{cookie}
	for name, body := range map[string]map[string]any{
		"a private key": {"key_name": "laptop", "public_key": beginPrivateKey + "\nx\n-----END OPENSSH PRIVATE KEY-----"},
		"not a key":     {"key_name": "laptop", "public_key": "hello"},
		"an empty name": {"key_name": "", "public_key": publicKeyLine(t, "a")},
		"a silly name":  {"key_name": "../../etc/passwd", "public_key": publicKeyLine(t, "a")},
		"an unknown type": {"key_name": "laptop",
			"public_key": "ssh-dss " + strings.Fields(publicKeyLine(t, "a"))[1]},
	} {
		recorder := do(t, s, req{method: "POST", path: "/v1/key-pairs", body: body, cookies: cookies})
		expectStatus(t, recorder, http.StatusBadRequest)
		if got := decode[errorBody](t, recorder).Error.Code; got != "ValidationError" {
			t.Errorf("%s: code %q", name, got)
		}
	}
	// A pasted private key is called out by name, because it is the mistake
	// worth being loud about.
	recorder := do(t, s, req{method: "POST", path: "/v1/key-pairs", cookies: cookies,
		body: map[string]any{"key_name": "laptop", "public_key": beginPrivateKey}})
	if !strings.Contains(decode[errorBody](t, recorder).Error.Message, "private key") {
		t.Fatalf("message: %s", recorder.Body.String())
	}
}

func TestKeyPairsAreNotSharedBetweenAccounts(t *testing.T) {
	s := testServer(t, nil)
	_, aliceCookie := session(t, s, "alice", false)
	_, bobCookie := session(t, s, "bob", false)
	line := publicKeyLine(t, "alice@laptop")

	expectStatus(t, do(t, s, req{method: "POST", path: "/v1/key-pairs", cookies: []*http.Cookie{aliceCookie},
		body: map[string]any{"key_name": "laptop", "public_key": line}}), http.StatusCreated)

	// Bob sees none of Alice's, may use the same name, and cannot delete hers.
	if keys := decode[keyPairList](t, do(t, s, req{method: "GET", path: "/v1/key-pairs", cookies: []*http.Cookie{bobCookie}})).KeyPairs; len(keys) != 0 {
		t.Fatalf("bob sees %+v", keys)
	}
	expectStatus(t, do(t, s, req{method: "DELETE", path: "/v1/key-pairs/laptop", cookies: []*http.Cookie{bobCookie}}), http.StatusNotFound)
	expectStatus(t, do(t, s, req{method: "POST", path: "/v1/key-pairs", cookies: []*http.Cookie{bobCookie},
		body: map[string]any{"key_name": "laptop", "public_key": publicKeyLine(t, "bob@laptop")}}), http.StatusCreated)
}

func TestLaunchingWithAnUnknownKeyIsRefused(t *testing.T) {
	s := testServer(t, nil)
	withInstances(t, s)
	_, cookie := session(t, s, "alice", false)
	recorder := do(t, s, req{method: "POST", path: "/v1/instances", cookies: []*http.Cookie{cookie},
		body: map[string]any{"image_id": "img-debian13", "instance_type": "small", "key_name": "nope"}})
	expectStatus(t, recorder, http.StatusBadRequest)
	if got := decode[errorBody](t, recorder).Error.Code; got != "InvalidKeyPair.NotFound" {
		t.Fatalf("code %q", got)
	}
}
