package wsrelay

import (
	"bytes"
	"io"
	"net"
	"testing"
	"time"
)

func TestAcceptKeyMatchesTheRFCExample(t *testing.T) {
	// RFC 6455 section 1.3.
	if got := AcceptKey("dGhlIHNhbXBsZSBub25jZQ=="); got != "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=" {
		t.Fatalf("AcceptKey = %q", got)
	}
}

func TestValidKey(t *testing.T) {
	for key, want := range map[string]bool{
		"dGhlIHNhbXBsZSBub25jZQ==": true,  // 16 bytes
		"":                         false, // missing
		"c2hvcnQ=":                 false, // too short
		"not base64!!":             false,
	} {
		if got := ValidKey(key); got != want {
			t.Errorf("ValidKey(%q) = %v, want %v", key, got, want)
		}
	}
}

func TestRelayCopiesBothWaysAndStopsWhenEitherSideCloses(t *testing.T) {
	browser, clientSide := net.Pipe()
	node, upstreamSide := net.Pipe()
	finished := make(chan struct{})
	// Bytes the HTTP server had already buffered must arrive first.
	buffered := io.MultiReader(bytes.NewReader([]byte("early")), clientSide)
	go func() {
		Relay(clientSide, buffered, upstreamSide)
		close(finished)
	}()

	got := make([]byte, 5)
	if _, err := io.ReadFull(node, got); err != nil || string(got) != "early" {
		t.Fatalf("node got %q (%v)", got, err)
	}
	go browser.Write([]byte("hello"))
	if _, err := io.ReadFull(node, got); err != nil || string(got) != "hello" {
		t.Fatalf("node got %q (%v)", got, err)
	}
	go node.Write([]byte("RFB 0"))
	if _, err := io.ReadFull(browser, got); err != nil || string(got) != "RFB 0" {
		t.Fatalf("browser got %q (%v)", got, err)
	}

	// The node hanging up must end the browser's side too, not leave it open.
	node.Close()
	select {
	case <-finished:
	case <-time.After(2 * time.Second):
		t.Fatal("Relay did not return after one side closed")
	}
	if _, err := browser.Read(got); err == nil {
		t.Fatal("the browser side was left open")
	}
}
