package app

import (
	"context"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
)

// Read through lifetimePolicyFor, never directly, so per-tier lifetimes
// stay a table entry rather than a refactor.
const (
	authSessionTTL    = 1 * time.Hour
	authRefreshWindow = 2 * time.Hour
	// authMaxSessionAge is measured from the chain's origin, never from a
	// refreshed handle's own mint instant.
	authMaxSessionAge = 24 * time.Hour
)

type lifetimePolicy struct {
	ttl           time.Duration
	refreshWindow time.Duration
	maxAge        time.Duration
}

// lifetimePolicyFor refuses a tier this revision cannot evaluate rather
// than defaulting it, which is what keeps deadlinesFor total.
func lifetimePolicyFor(tier domain.AuthSessionIdentityType) (lifetimePolicy, error) {
	if !tier.IsKnown() {
		return lifetimePolicy{}, fmt.Errorf("%w: unknown tier %q", domain.ErrAuthSessionNotFound, tier)
	}
	return lifetimePolicy{
		ttl:           authSessionTTL,
		refreshWindow: authRefreshWindow,
		maxAge:        authMaxSessionAge,
	}, nil
}

type sessionDeadlines struct {
	expiresAt      time.Time
	refreshUntil   time.Time
	lifetimeEndsAt time.Time
}

// deadlinesFor is the one function that answers "when does this session
// end", for validate and refreshed both. Two implementations of this
// arithmetic is the same bug as computing the cap from the wrong field, so
// `now` is deliberately not an input.
//
//	lifetimeEndsAt = lineageIssuedAt + maxAge(tier)
//	expiresAt      = min(issuedAt + ttl(tier),           lifetimeEndsAt)
//	refreshUntil   = min(issuedAt + refreshWindow(tier), lifetimeEndsAt)
//
// Deriving rather than stamping means a lifetime change reaches sessions
// already issued — the point — but also that *lengthening* one resurrects
// dead handles. A lifetime reduction is not a revocation; dropping a
// signing key is the only irreversible lever.
//
// Both windows are clamped, because the client schedules off expiresAt:
// ports derives refreshInSeconds and the X-Auth-Refresh hint from
// expiresAt - refreshAtOffset, so an expiresAt past the cap would put the
// proactive re-login *after* the session is already dead — the last ~25
// minutes of a chain spent 401ing. The cap is still checked on every path;
// clamping is about what the client is told, not about enforcement.
func deadlinesFor(sess domain.AuthSession) (sessionDeadlines, error) {
	policy, err := lifetimePolicyFor(sess.IdentityType)
	if err != nil {
		return sessionDeadlines{}, err
	}
	// A zero origin fails closed anyway, via a 1970 deadline. Refusing
	// makes it a log line instead of a clock bug three levels away.
	if sess.CreatedAt.IsZero() {
		return sessionDeadlines{}, fmt.Errorf("%w: no issued-at", domain.ErrAuthSessionNotFound)
	}
	if sess.LineageIssuedAt.IsZero() {
		return sessionDeadlines{}, fmt.Errorf("%w: no lineage issued-at", domain.ErrAuthSessionNotFound)
	}

	lifetimeEndsAt := sess.LineageIssuedAt.Add(policy.maxAge)
	return sessionDeadlines{
		expiresAt:      earlier(sess.CreatedAt.Add(policy.ttl), lifetimeEndsAt),
		refreshUntil:   earlier(sess.CreatedAt.Add(policy.refreshWindow), lifetimeEndsAt),
		lifetimeEndsAt: lifetimeEndsAt,
	}, nil
}

func earlier(a, b time.Time) time.Time {
	if a.After(b) {
		return b
	}
	return a
}

// withDeadlines fills in the deadline fields Unseal leaves zero.
func withDeadlines(sess domain.AuthSession) (domain.AuthSession, error) {
	d, err := deadlinesFor(sess)
	if err != nil {
		return domain.AuthSession{}, err
	}
	sess.ExpiresAt = d.expiresAt
	sess.RefreshUntil = d.refreshUntil
	sess.LifetimeEndsAt = d.lifetimeEndsAt
	return sess, nil
}

// refreshed returns the next session in the chain, ready to be sealed. The
// only writer of a refreshed session, so the chain origin cannot be
// re-stamped by accident. Tolerates expiry, refuses a closed refresh
// window or the cap, which is exclusive.
//
// A minimum-refresh-interval rule would go here, reading now.Sub(CreatedAt)
// — this handle's age, never the lineage's, which only grows and would go
// vacuous within one interval. It would catch a client refreshing on every
// call; an adversary re-presenting a retained older handle sails through.
func refreshed(sess domain.AuthSession, now time.Time) (domain.AuthSession, error) {
	current, err := deadlinesFor(sess)
	if err != nil {
		return domain.AuthSession{}, err
	}
	if now.After(current.refreshUntil) || !now.Before(current.lifetimeEndsAt) {
		return domain.AuthSession{}, domain.ErrAuthSessionRefreshExpired
	}

	next := sess
	// Copy every lineage field, re-stamp everything else, bump generation.
	next.CreatedAt = now
	next.Generation++
	next.ID = "" // Seal mints the handle.

	return withDeadlines(next)
}

// sessionSealer converts a session to the opaque handle a client presents,
// and back. Not a strategy pattern — there is only ever one
// implementation; the interface is here so tests can substitute a fake.
type sessionSealer interface {
	// Seal returns sess with ID set to the handle, every other field
	// untouched.
	Seal(ctx context.Context, sess domain.AuthSession) (domain.AuthSession, error)

	// Unseal never checks the clock: freshness is policy and lives here,
	// so validate (which refuses expiry) and refresh (which tolerates it)
	// share one path. The derived deadline fields come back zero.
	Unseal(ctx context.Context, handle string) (domain.AuthSession, error)
}

// The handle's prefix and format belong to the sealer that mints them —
// authsessiontoken.Signed — not here. Nothing in this package generates a
// session id any more.
