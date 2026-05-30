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
	EnforceActiveIPCap(ctx context.Context, identityType domain.AuthSessionIdentityType, ipHash string, maxActive int, now time.Time) error
}

// authAnonymousIPCap is the max number of concurrently-active
// anonymous sessions per ip_hash. When exceeded, the oldest active
// sessions are evicted before issuing a new one.
const authAnonymousIPCap = 4

// AnonymousLogin issues a new anonymous-tier session for (userID,
// ipHash). It enforces the per-IP anonymous session cap by deleting
// the oldest active sessions for the ip until there's room, then
// inserts (or upserts, single-active-per-identity) the new row.
//
// userID is trusted as-is — input shape validation is the caller's
// responsibility.
type AnonymousLogin func(ctx context.Context, userID string, ipHash string) (domain.AuthSession, error)

func BuildAnonymousLogin(
	repo anonymousLoginRepository,
	nowFunc func() time.Time,
	generateSessionID func() (string, error),
) AnonymousLogin {
	return func(ctx context.Context, userID string, ipHash string) (domain.AuthSession, error) {
		now := nowFunc()

		if err := repo.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, ipHash, authAnonymousIPCap, now); err != nil {
			return domain.AuthSession{}, fmt.Errorf("failed to enforce ip cap: %w", err)
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
