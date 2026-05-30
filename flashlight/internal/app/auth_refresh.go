package app

import (
	"context"
	"fmt"
	"time"

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
type RefreshSession func(ctx context.Context, sessionID string, ipHash string) (domain.AuthSession, error)

func BuildRefreshSession(repo refreshRepository, nowFunc func() time.Time) RefreshSession {
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
			return domain.AuthSession{}, fmt.Errorf("failed to refresh session: %w", err)
		}
		return sess, nil
	}
}
