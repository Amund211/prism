package app

import (
	"context"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/domain"
)

// validateRepository is the subset of the auth-session repository
// that BuildValidateSession depends on.
type validateRepository interface {
	Update(ctx context.Context, id string, update func(domain.AuthSession) (domain.AuthSession, error)) (domain.AuthSession, error)
}

// ValidateSession looks up a session by id, checks it's still within
// its expires_at and max-age windows, and bumps last_used_at — all
// inside a single repository Update call. Used by the bearer
// middleware on each request.
//
// Successful validations are cached so repeat requests from the same
// session don't hammer Postgres. The cache TTL is the caller's choice;
// a 1-minute TTL trades up to one minute of staleness (a recently
// revoked / expired session can still be served from cache that long,
// and last_used_at gets bumped at most once per TTL window) for a
// large reduction in DB load on the validate hot path.
type ValidateSession func(ctx context.Context, sessionID string) (domain.AuthSession, error)

func BuildValidateSession(
	repo validateRepository,
	nowFunc func() time.Time,
	sessionCache cache.Cache[domain.AuthSession],
) ValidateSession {
	return func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
		if sessionID == "" {
			return domain.AuthSession{}, domain.ErrAuthSessionNotFound
		}

		sess, _, err := cache.GetOrCreate(ctx, sessionCache, sessionID, func() (domain.AuthSession, error) {
			now := nowFunc()
			return repo.Update(ctx, sessionID, func(s domain.AuthSession) (domain.AuthSession, error) {
				if now.After(s.ExpiresAt) {
					return domain.AuthSession{}, domain.ErrAuthSessionExpired
				}
				if !now.Before(s.LifetimeEndsAt) {
					return domain.AuthSession{}, domain.ErrAuthSessionExpired
				}
				s.LastUsedAt = now
				return s, nil
			})
		})
		if err != nil {
			return domain.AuthSession{}, fmt.Errorf("failed to validate session: %w", err)
		}
		return sess, nil
	}
}
