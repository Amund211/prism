package app

import (
	"context"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/domain"
)

// refreshRepository is the subset of the auth-session repository that
// BuildRefreshSession depends on.
type refreshRepository interface {
	Update(ctx context.Context, id string, update func(domain.AuthSession) (domain.AuthSession, error)) (domain.AuthSession, error)
}

// RefreshSession bumps the lifetime of an existing session given its
// bearer id. Accepts ids that are past expires_at but still within
// refresh_until and lifetime_ends_at. Updates ip_hash so roaming
// clients don't get stuck on stale ip counters.
//
// A successful refresh drops the session's entry from the validate cache
// (see sessionCache below).
type RefreshSession func(ctx context.Context, sessionID string, ipHash string) (domain.AuthSession, error)

// sessionCache is BuildValidateSession's cache. Since refresh does not
// rotate the id, the row it just bumped is cached under the same key, and
// a hit re-checks nothing — so every read of the session for the rest of
// that entry's ttl would see the pre-refresh expires_at. That is what the
// bearer middleware computes its X-Auth-Refresh hint from: it would keep
// asking for refreshes the client has already done. Dropping the entry is
// also what would make caching negative verdicts feasible, since `expired`
// stops being a verdict a refresh can silently outdate.
func BuildRefreshSession(
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
