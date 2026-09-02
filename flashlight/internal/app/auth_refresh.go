package app

import (
	"context"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/domain"
)

// refreshRepository is the subset of the auth-session repository that
// BuildRefreshSessionFromRepository depends on.
type refreshRepository interface {
	Update(ctx context.Context, id string, update func(domain.AuthSession) (domain.AuthSession, error)) (domain.AuthSession, error)
}

// RefreshSession extends the lifetime of an existing session given its
// bearer handle. Accepts handles that are past expiry but still within
// the refresh window and the max-age cap.
type RefreshSession func(ctx context.Context, sessionID string, ipHash string) (domain.AuthSession, error)

// BuildRefreshSession refreshes against a sessionSealer: unseal, apply
// refreshed(), seal a *new* handle. Nothing mutates, so there is no cache
// entry to invalidate.
//
// ipHash is ignored — it is not in the signed payload, since a copy baked
// into a token is stale by definition and roaming clients make it wrong
// rather than merely old. The parameter stays so the wire contract and
// ports are untouched.
//
// Not wired yet — the cutover flips main.go from
// BuildRefreshSessionFromRepository to this.
func BuildRefreshSession(sealer sessionSealer, nowFunc func() time.Time) RefreshSession {
	return func(ctx context.Context, handle string, _ string) (domain.AuthSession, error) {
		sess, err := sealer.Unseal(ctx, handle)
		if err != nil {
			return domain.AuthSession{}, fmt.Errorf("failed to refresh session: %w", err)
		}

		next, err := refreshed(sess, nowFunc())
		if err != nil {
			return domain.AuthSession{}, fmt.Errorf("failed to refresh session: %w", err)
		}

		sealed, err := sealer.Seal(ctx, next)
		if err != nil {
			return domain.AuthSession{}, fmt.Errorf("failed to refresh session: %w", err)
		}
		return sealed, nil
	}
}

// BuildRefreshSessionFromRepository bumps the row in place, keeping the
// same session id, and updates ip_hash so roaming clients don't get stuck
// on stale ip counters.
//
// sessionCache is BuildValidateSessionFromRepository's cache. Since refresh
// does not rotate the id, the row it just bumped is cached under the same
// key, and a hit re-checks nothing — so every read of the session for the
// rest of that entry's ttl would see the pre-refresh expires_at. That is
// what the bearer middleware computes its X-Auth-Refresh hint from: it
// would keep asking for refreshes the client has already done. Dropping the
// entry is also what would make caching negative verdicts feasible, since
// `expired` stops being a verdict a refresh can silently outdate.
//
// Deleted at the cutover, together with the repository and the cache.
func BuildRefreshSessionFromRepository(
	repo refreshRepository,
	nowFunc func() time.Time,
	sessionCache cache.Cache[domain.AuthSession],
) RefreshSession {
	return func(ctx context.Context, sessionID string, ipHash string) (domain.AuthSession, error) {
		if sessionID == "" {
			return domain.AuthSession{}, domain.ErrAuthSessionNotFound
		}

		now := nowFunc()

		sess, err := repo.Update(ctx, sessionID, func(s domain.AuthSession) (domain.AuthSession, error) {
			if now.After(s.RefreshUntil) {
				return domain.AuthSession{}, domain.ErrAuthSessionRefreshExpired
			}
			if !now.Before(s.LifetimeEndsAt) {
				return domain.AuthSession{}, domain.ErrAuthSessionRefreshExpired
			}

			newExpiresAt := now.Add(authSessionTTL)
			newRefreshUntil := now.Add(authRefreshWindow)
			if newExpiresAt.After(s.LifetimeEndsAt) {
				newExpiresAt = s.LifetimeEndsAt
			}
			if newRefreshUntil.After(s.LifetimeEndsAt) {
				newRefreshUntil = s.LifetimeEndsAt
			}

			s.ExpiresAt = newExpiresAt
			s.RefreshUntil = newRefreshUntil
			s.IPHash = ipHash
			s.LastUsedAt = now
			return s, nil
		})
		if err != nil {
			// Nothing was written on any of these paths, so whatever is
			// cached is as good as it was.
			return domain.AuthSession{}, fmt.Errorf("failed to refresh session: %w", err)
		}

		// After the write is durable, so a validate that misses reads the
		// bumped row.
		cache.Delete(sessionCache, sessionID)

		return sess, nil
	}
}
