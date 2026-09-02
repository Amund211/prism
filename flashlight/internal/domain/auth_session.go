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
// discriminator is IdentityType. It is what a signed handle unseals to,
// plus the deadlines the app layer derives; there is no storage behind it.
//
// The three deadline fields are derived, never stored — deadlinesFor is
// the only thing that computes them, so a lifetime change reaches sessions
// already issued.
type AuthSession struct {
	ID           string
	IdentityType AuthSessionIdentityType
	IdentityKey  string
	// CreatedAt is *this handle's* mint instant — a reseal re-stamps it.
	// The 24h cap is not computed from it; see LineageIssuedAt.
	CreatedAt    time.Time
	ExpiresAt    time.Time
	RefreshUntil time.Time
	// LifetimeEndsAt is the absolute deadline past which this session
	// can no longer be refreshed, regardless of how many refreshes have
	// happened. Derived from LineageIssuedAt, so it is identical at every
	// link of a chain.
	LifetimeEndsAt time.Time

	// LineageIssuedAt is the refresh chain's origin, and the only thing
	// bounding a chain to 24h: the cap is LineageIssuedAt + maxAge. A
	// reseal copies it untouched while re-stamping CreatedAt. Compute the
	// cap from CreatedAt instead and every refresh moves the bound —
	// silently, and it looks like nothing until a session lives a week.
	LineageIssuedAt time.Time
	// Lineage identifies the refresh chain: "fllineage_" + a UUIDv7,
	// minted at login and copied by every reseal. Nothing reads it today;
	// it is in the payload so a future events table needs no format bump.
	Lineage string
	// Generation is 0 at login and +1 per refresh. Recorded, never
	// enforced — re-login is free, so a ceiling stops no attacker.
	Generation int
}

// ErrAuthSessionNotFound is every refusal a handle can earn from the
// sealer: unparseable, unsigned, tampered with, or of a format or tier
// this revision does not know. They collapse into one error because they
// are all "a handle we never issued", and that mapping is what keeps the
// 401 contract in internal/ports untouched.
var ErrAuthSessionNotFound = errors.New("auth session not found")

// ErrAuthSessionRevoked is returned when an operation is attempted on
// a session that has been explicitly ended.
//
// Nothing produces it any more: a signature cannot be deleted, so
// revocation is the BLOCKED_USER_IDS blocklist on the verified identity,
// plus dropping a signing key as the "revoke everything" lever. Kept
// because internal/ports still maps it to a 401 and that arm is part of
// the contract — Microsoft-tier logout is the case that would need it.
var ErrAuthSessionRevoked = errors.New("auth session revoked")

// ErrAuthSessionExpired is returned by app-layer validation when the
// session is past its expiry (still potentially refreshable).
var ErrAuthSessionExpired = errors.New("auth session expired")

// ErrAuthSessionRefreshExpired is returned when the session is past the
// refresh window or its 24h hard max-age.
var ErrAuthSessionRefreshExpired = errors.New("auth session refresh window expired")

// ErrAuthSessionIssuanceRefused is how an issuance guard says "not this
// one" rather than "something broke". Wrap it, or the refusal reaches
// internal/ports as an unclassifiable failure and every rate-limited
// client gets a 500 and a Sentry alert instead of a 429.
var ErrAuthSessionIssuanceRefused = errors.New("auth session issuance refused")
