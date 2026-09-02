package app

import (
	"context"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
)

// anonymousLoginRepository is the subset of the auth-session
// repository that BuildAnonymousLogin depends on.
type anonymousLoginRepository interface {
	Create(ctx context.Context, sess domain.AuthSession) error
}

// issuanceGuard is consulted before a new session is issued. It refuses
// by returning an error wrapping domain.ErrAuthSessionIssuanceRefused —
// anything else is read as the guard itself breaking, which internal/ports
// answers with a 500 and a Sentry report rather than the 429 a refused
// client should see. Deliberately not a sessionSealer method: a backing
// that cannot count across handles has to say so at the wiring site in
// main.go, not by silently succeeding. Today the only implementation is
// authsessionguard.AllowAll, whose doc comment records what was given up.
type issuanceGuard interface {
	Allow(ctx context.Context, identityType domain.AuthSessionIdentityType, identityKey string, ipHash string, now time.Time) error
}

// AnonymousLogin issues a new anonymous-tier session for (userID,
// ipHash), if the issuance guard allows it. Nothing the caller already
// holds is touched: concurrent sessions for one identity coexist and
// expire naturally.
//
// userID is trusted as-is — input shape validation is the caller's
// responsibility.
type AnonymousLogin func(ctx context.Context, userID string, ipHash string) (domain.AuthSession, error)

func BuildAnonymousLogin(
	repo anonymousLoginRepository,
	guard issuanceGuard,
	nowFunc func() time.Time,
	generateSessionID func() (string, error),
) AnonymousLogin {
	return func(ctx context.Context, userID string, ipHash string) (domain.AuthSession, error) {
		now := nowFunc()

		if err := guard.Allow(ctx, domain.AuthSessionIdentityAnonymous, userID, ipHash, now); err != nil {
			return domain.AuthSession{}, fmt.Errorf("failed to check issuance guard: %w", err)
		}

		id, err := generateSessionID()
		if err != nil {
			return domain.AuthSession{}, fmt.Errorf("failed to generate session id: %w", err)
		}

		sess := domain.AuthSession{
			ID:             id,
			IdentityType:   domain.AuthSessionIdentityAnonymous,
			IdentityKey:    userID,
			IPHash:         ipHash,
			CreatedAt:      now,
			ExpiresAt:      now.Add(authSessionTTL),
			RefreshUntil:   now.Add(authRefreshWindow),
			LifetimeEndsAt: now.Add(authMaxSessionAge),
			LastUsedAt:     now,
		}

		if err := repo.Create(ctx, sess); err != nil {
			return domain.AuthSession{}, fmt.Errorf("failed to create anonymous session: %w", err)
		}

		return sess, nil
	}
}
