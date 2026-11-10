package app

import (
	"context"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
)

// ValidateSession resolves a bearer handle and checks it is still within
// its expiry and max-age windows. Used by the bearer middleware on each
// request.
type ValidateSession func(ctx context.Context, sessionID string) (domain.AuthSession, error)

// BuildValidateSession validates against a sessionSealer: a signature
// check and the derived deadlines, no lookup and so nothing to cache.
func BuildValidateSession(sealer sessionSealer, nowFunc func() time.Time) ValidateSession {
	return func(ctx context.Context, handle string) (domain.AuthSession, error) {
		sess, err := sealer.Unseal(ctx, handle)
		if err != nil {
			return domain.AuthSession{}, fmt.Errorf("failed to validate session: %w", err)
		}
		sess, err = withDeadlines(sess)
		if err != nil {
			return domain.AuthSession{}, fmt.Errorf("failed to validate session: %w", err)
		}

		now := nowFunc()
		if now.After(sess.ExpiresAt) || !now.Before(sess.LifetimeEndsAt) {
			return domain.AuthSession{}, fmt.Errorf("failed to validate session: %w", domain.ErrAuthSessionExpired)
		}
		return sess, nil
	}
}
