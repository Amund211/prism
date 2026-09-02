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

// IsKnown reports whether this revision implements the tier. A tier we
// cannot evaluate is refused rather than defaulted, by the sealer on the
// way in and by the lifetime policy that has no answer for it. Once the
// Microsoft tier ships, rolling back past it logs out its sessions.
func (t AuthSessionIdentityType) IsKnown() bool {
	return t == AuthSessionIdentityAnonymous
}

// AuthSession is a server-side bearer session, regardless of tier. The
// discriminator is IdentityType. It is the app layer's view, not a storage
// shape — today a row in auth_sessions, under the stateless backing what a
// signed handle unseals to. Fields the two backings don't share say so.
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
	// CreatedAt is *this handle's* mint instant — a reseal re-stamps it.
	// The 24h cap is not computed from it; see LineageIssuedAt.
	CreatedAt    time.Time
	ExpiresAt    time.Time
	RefreshUntil time.Time
	// LifetimeEndsAt is the absolute deadline past which this session
	// can no longer be refreshed, regardless of how many refreshes have
	// happened. Fixed at issue, never extended.
	LifetimeEndsAt time.Time
	LastUsedAt     time.Time
	RevokedAt      *time.Time

	// LineageIssuedAt is the refresh chain's origin, and the only thing
	// bounding a chain to 24h: the cap is LineageIssuedAt + maxAge. A
	// reseal copies it untouched while re-stamping CreatedAt. Compute the
	// cap from CreatedAt instead and every refresh moves the bound —
	// silently, and it looks like nothing until a session lives a week.
	// Zero on a row-backed session, which stamps LifetimeEndsAt instead.
	LineageIssuedAt time.Time
	// Lineage identifies the refresh chain: "fllineage_" + a UUIDv7,
	// minted at login and copied by every reseal. Nothing reads it today;
	// it is in the payload so a future events table needs no format bump.
	Lineage string
	// Generation is 0 at login and +1 per refresh. Recorded, never
	// enforced — re-login is free, so a ceiling stops no attacker.
	Generation int
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
