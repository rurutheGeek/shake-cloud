package accesskey

import (
	"strings"
	"testing"
)

func TestNewTokensParseBackToThemselves(t *testing.T) {
	token := New()
	parsed, err := Parse(token.String())
	if err != nil {
		t.Fatalf("Parse(New()) failed: %v", err)
	}
	if parsed != token {
		t.Fatalf("round trip changed the token")
	}
	if !ValidID(token.ID) {
		t.Fatalf("New produced an ID that ValidID rejects: %q", token.ID)
	}
}

func TestTokensAreNotRepeated(t *testing.T) {
	seen := map[string]bool{}
	for range 1000 {
		token := New()
		if seen[token.ID] || seen[token.Secret] {
			t.Fatal("random source repeated a value")
		}
		seen[token.ID], seen[token.Secret] = true, true
	}
}

func TestParseRejectsAnythingButTheExactFormat(t *testing.T) {
	good := New().String()
	for name, value := range map[string]string{
		"empty":            "",
		"no prefix":        strings.TrimPrefix(good, Prefix),
		"other prefix":     "sk_" + strings.TrimPrefix(good, Prefix),
		"uppercase id":     Prefix + strings.ToUpper(good[4:24]) + good[24:],
		"missing dot":      strings.Replace(good, ".", "", 1),
		"short secret":     good[:len(good)-1],
		"trailing newline": good + "\n",
		"leading space":    " " + good,
		"padding":          good + "=",
	} {
		if _, err := Parse(value); err == nil {
			t.Errorf("%s: Parse accepted %q", name, value)
		}
	}
}

func TestMatchesOnlyTheSameSecret(t *testing.T) {
	token := New()
	stored := token.Hash()
	if !token.Matches(stored) {
		t.Fatal("token does not match its own hash")
	}
	other := token
	other.Secret = New().Secret
	if other.Matches(stored) {
		t.Fatal("a different secret matched")
	}
	if token.Matches(nil) {
		t.Fatal("an empty stored hash matched")
	}
}
