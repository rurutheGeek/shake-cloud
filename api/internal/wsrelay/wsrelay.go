// Package wsrelay is the part of RFC 6455 needed to pass a websocket through
// the API untouched: the handshake's accept value, and copying frames both ways
// until either side stops.
//
// Frames are never parsed. A browser sends masked frames, which is what a
// server expects from a client; Proxmox sends unmasked ones, which is what a
// browser expects from a server. So each side's bytes are already correct for
// the side they are copied to, as long as neither handshake negotiated an
// extension (such as compression) that the other side did not.
package wsrelay

import (
	"crypto/sha1"
	"encoding/base64"
	"io"
	"sync"
)

// guid is fixed by RFC 6455 section 1.3.
const guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

// AcceptKey is the Sec-WebSocket-Accept value that answers a Sec-WebSocket-Key.
func AcceptKey(key string) string {
	sum := sha1.Sum([]byte(key + guid))
	return base64.StdEncoding.EncodeToString(sum[:])
}

// ValidKey reports whether a Sec-WebSocket-Key is what the RFC requires: 16
// random bytes, base64 encoded. A malformed one is refused rather than echoed.
func ValidKey(key string) bool {
	raw, err := base64.StdEncoding.DecodeString(key)
	return err == nil && len(raw) == 16
}

// Relay copies clientReader to upstream and upstream to client until either
// direction ends, then closes both connections so the other copy ends too.
//
// clientReader is separate from client because the HTTP server may already
// have buffered bytes the browser sent right after its handshake; they have to
// reach Proxmox before anything read from the connection afterwards.
func Relay(client io.WriteCloser, clientReader io.Reader, upstream io.ReadWriteCloser) {
	var once sync.Once
	closeBoth := func() {
		once.Do(func() {
			client.Close()
			upstream.Close()
		})
	}
	done := make(chan struct{}, 2)
	go func() {
		_, _ = io.Copy(upstream, clientReader)
		closeBoth()
		done <- struct{}{}
	}()
	go func() {
		_, _ = io.Copy(client, upstream)
		closeBoth()
		done <- struct{}{}
	}()
	<-done
	<-done
}
