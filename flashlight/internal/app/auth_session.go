package app

import (
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"time"
)

// Tier-agnostic tunables that govern session issuance and refresh.
// Each session row carries the lifetime_ends_at value derived from
// authMaxSessionAge at issue time, so changing this constant won't
// retroactively extend already-issued sessions.
const (
	// authSessionTTL is how long after creation an issued session can
	// be used on regular endpoints. Past expires_at the session is
	// still refreshable up to authRefreshWindow.
	authSessionTTL = 1 * time.Hour

	// authRefreshWindow is the total window after creation during
	// which a session can be refreshed. Past it, refresh fails and the
	// client must re-auth.
	authRefreshWindow = 2 * time.Hour

	// authMaxSessionAge is the absolute lifetime cap on a session.
	// Stamped onto each row as lifetime_ends_at at issue time, then
	// used to clamp refresh extensions; never re-evaluated.
	authMaxSessionAge = 24 * time.Hour
)

// sessionIDPrefix tags every server-issued session ID so logs and
// scraping tools can recognize them at a glance, and so the format can
// evolve later without breaking comparisons. Tier-agnostic — both
// anonymous and (future) Microsoft sessions share the prefix.
const sessionIDPrefix = "flsess_"

// GenerateAuthSessionID returns a 32-byte URL-safe base64 session id
// with sessionIDPrefix applied. Total length is len(prefix) + 43
// chars (base64 of 32 bytes without padding).
func GenerateAuthSessionID() (string, error) {
	var b [32]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", fmt.Errorf("failed to generate session id: %w", err)
	}
	return sessionIDPrefix + base64.RawURLEncoding.EncodeToString(b[:]), nil
}
