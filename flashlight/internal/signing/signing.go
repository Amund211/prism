// Package signing holds the HMAC primitives shared by the auth signing
// schemes: key-list parsing, key generation, signing and verifying a body.
//
// What deliberately does not live here: any key list, any "find the right
// key yourself" convenience, and any envelope format. Domain separation
// between the schemes rests on each holding its own key list and signing
// its own prefixed body, and a helper here that knew about either is the
// one refactor that would make a challenge blob verify as a session.
package signing

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"fmt"
	"strings"
)

// MinKeyLength matches the SHA-256 block output. Shorter keys are almost
// always a truncated or misconfigured secret.
const MinKeyLength = 32

// ErrInvalidConfig covers key material only, at construction time. A
// scheme's own wiring errors stay in its own package.
var ErrInvalidConfig = errors.New("invalid signing key configuration")

// ParseKeys decodes base64 signing keys from config. The first key signs
// and all of them are accepted, so rotation is: prepend the new key,
// deploy, drop the old one once nothing signed with it can still be
// presented. Blank entries are skipped — the config format is
// newline-delimited and gets edited by hand.
func ParseKeys(encoded []string) ([][]byte, error) {
	keys := make([][]byte, 0, len(encoded))
	for i, raw := range encoded {
		raw = strings.TrimSpace(raw)
		if raw == "" {
			continue
		}
		key, err := base64.StdEncoding.DecodeString(raw)
		if err != nil {
			// Deliberately not wrapping the decode error: it quotes the
			// input, and the input is key material.
			return nil, fmt.Errorf("%w: signing key %d is not valid base64", ErrInvalidConfig, i)
		}
		if len(key) < MinKeyLength {
			return nil, fmt.Errorf("%w: signing key %d is %d bytes, want at least %d", ErrInvalidConfig, i, len(key), MinKeyLength)
		}
		keys = append(keys, key)
	}
	if len(keys) == 0 {
		return nil, fmt.Errorf("%w: no signing keys", ErrInvalidConfig)
	}
	return keys, nil
}

// GenerateKey returns a fresh base64-encoded signing key. Development
// only: a key generated at startup dies with the process, invalidating
// everything signed with it — fine for a 60-second challenge a local
// client retries through, not for production, where the key is a secret so
// that it survives a revision rollout.
func GenerateKey() (string, error) {
	var key [MinKeyLength]byte
	if _, err := rand.Read(key[:]); err != nil {
		return "", fmt.Errorf("failed to generate signing key: %w", err)
	}
	return base64.StdEncoding.EncodeToString(key[:]), nil
}

// SignedByAnyKey reports whether signature is a valid HMAC over body under
// any key in keys. Constant-time comparison.
func SignedByAnyKey(keys [][]byte, body string, signature []byte) bool {
	for _, key := range keys {
		if hmac.Equal(Sign(key, body), signature) {
			return true
		}
	}
	return false
}

// Sign returns the HMAC-SHA256 of body under key. Callers must sign the
// encoded body exactly as it arrived, never a re-encode of a parsed
// struct.
func Sign(key []byte, body string) []byte {
	mac := hmac.New(sha256.New, key)
	// hash.Hash.Write never returns an error.
	_, _ = mac.Write([]byte(body))
	return mac.Sum(nil)
}
