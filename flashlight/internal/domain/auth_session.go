package domain

import (
	"errors"
	"time"
)

// AuthSessionIdentityType discriminates the tier the session represents.
// Only the anonymous tier is implemented today; the Microsoft tier will
// add a value here when it lands.
type AuthSessionIdentityType string

const AuthSessionIdentityAnonymous AuthSessionIdentityType = "anonymous"

// AuthSession is one row in the auth_sessions table — a server-side
// bearer session, regardless of tier. The discriminator is IdentityType.
//
// RevokedAt is nil iff the session is still active (which is to say:
// not explicitly ended; natural expiry past refresh_until is a
// separate concept and doesn't set this field). The reason a session
// was revoked is recorded in the DB but not exposed on the typed
// model — it's audit data, not load-bearing logic.
type AuthSession struct {
	ID           string
	IdentityType AuthSessionIdentityType
	IdentityKey  string
	IPHash       string
	CreatedAt    time.Time
	ExpiresAt    time.Time
	RefreshUntil time.Time
	// LifetimeEndsAt is the absolute deadline past which this session
	// can no longer be refreshed, regardless of how many refreshes have
	// happened. Fixed at issue, never extended.
	LifetimeEndsAt time.Time
	LastUsedAt     time.Time
	RevokedAt      *time.Time
}

// ErrAuthSessionNotFound is returned when a session id is unknown to the repo.
var ErrAuthSessionNotFound = errors.New("auth session not found")

// ErrAuthSessionRevoked is returned when an operation is attempted on
// a session that has been explicitly ended (replaced, evicted, etc.).
var ErrAuthSessionRevoked = errors.New("auth session revoked")

// ErrAuthSessionExpired is returned by app-layer validation when the
// session is past its expiry (still potentially refreshable).
var ErrAuthSessionExpired = errors.New("auth session expired")

// ErrAuthSessionRefreshExpired is returned when the session is past the
// refresh window or its 24h hard max-age.
var ErrAuthSessionRefreshExpired = errors.New("auth session refresh window expired")
