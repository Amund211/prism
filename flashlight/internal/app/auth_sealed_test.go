package app_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
)

var sealedOrigin = time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)

// unsealed is what a sealer hands back: identity and the two origins, and
// no deadlines — the app layer derives those.
func unsealed(issuedAt, lineageIssuedAt time.Time, generation int) domain.AuthSession {
	return domain.AuthSession{
		ID:              "flsess_handle",
		IdentityType:    domain.AuthSessionIdentityAnonymous,
		IdentityKey:     "user-A",
		CreatedAt:       issuedAt,
		LineageIssuedAt: lineageIssuedAt,
		Lineage:         "fllineage_0190d3c1-8f2a-7d3e-9c11-4a6b8e2f0d55",
		Generation:      generation,
	}
}

func TestBuildValidateSessionFromSealer(t *testing.T) {
	t.Parallel()

	ctx := context.Background()

	t.Run("returns the session with its deadlines derived", func(t *testing.T) {
		t.Parallel()
		now := sealedOrigin.Add(30 * time.Minute)

		var gotHandle string
		sealer := unsealTo(unsealed(sealedOrigin, sealedOrigin, 0))
		sealer.unsealFn = func(_ context.Context, handle string) (domain.AuthSession, error) {
			gotHandle = handle
			return unsealed(sealedOrigin, sealedOrigin, 0), nil
		}

		validate := app.BuildValidateSession(sealer, fixedNow(now))
		sess, err := validate(ctx, "flsess_handle")
		require.NoError(t, err)

		require.Equal(t, "flsess_handle", gotHandle, "the handle is passed through verbatim")
		require.Equal(t, sealedOrigin.Add(authSessionTTL), sess.ExpiresAt)
		require.Equal(t, sealedOrigin.Add(authRefreshWindow), sess.RefreshUntil)
		require.Equal(t, sealedOrigin.Add(authMaxSessionAge), sess.LifetimeEndsAt)
		require.Equal(t, "user-A", sess.IdentityKey)
	})

	t.Run("refuses a session past its ttl", func(t *testing.T) {
		t.Parallel()
		sealer := unsealTo(unsealed(sealedOrigin, sealedOrigin, 0))

		validate := app.BuildValidateSession(sealer, fixedNow(sealedOrigin.Add(authSessionTTL).Add(time.Nanosecond)))
		_, err := validate(ctx, "flsess_handle")
		require.ErrorIs(t, err, domain.ErrAuthSessionExpired)
	})

	t.Run("refuses a session past the chain cap even inside its own ttl", func(t *testing.T) {
		t.Parallel()
		// Minted 23h30m into the chain, so its ttl outlives the cap.
		sealer := unsealTo(unsealed(sealedOrigin.Add(23*time.Hour+30*time.Minute), sealedOrigin, 47))

		validate := app.BuildValidateSession(sealer, fixedNow(sealedOrigin.Add(authMaxSessionAge)))
		_, err := validate(ctx, "flsess_handle")
		require.ErrorIs(t, err, domain.ErrAuthSessionExpired)
	})

	t.Run("propagates an unseal refusal", func(t *testing.T) {
		t.Parallel()
		sealer := &fakeSessionSealer{
			unsealFn: func(_ context.Context, _ string) (domain.AuthSession, error) {
				return domain.AuthSession{}, domain.ErrAuthSessionNotFound
			},
		}

		validate := app.BuildValidateSession(sealer, fixedNow(sealedOrigin))
		_, err := validate(ctx, "garbage")
		require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
	})
}

func TestBuildRefreshSessionFromSealer(t *testing.T) {
	t.Parallel()

	ctx := context.Background()

	t.Run("reseals into a new handle and re-derives the deadlines", func(t *testing.T) {
		t.Parallel()
		now := sealedOrigin.Add(30 * time.Minute)

		var sealedArg domain.AuthSession
		sealer := unsealTo(unsealed(sealedOrigin, sealedOrigin, 0))
		sealer.sealFn = func(_ context.Context, s domain.AuthSession) (domain.AuthSession, error) {
			sealedArg = s
			s.ID = "flsess_resealed"
			return s, nil
		}

		refresh := app.BuildRefreshSession(sealer, fixedNow(now))
		sess, err := refresh(ctx, "flsess_handle", "iphash")
		require.NoError(t, err)

		require.Equal(t, "flsess_resealed", sess.ID)
		require.Empty(t, sealedArg.ID, "the parent's handle must not travel into Seal")
		require.Equal(t, now, sess.CreatedAt)
		require.Equal(t, sealedOrigin, sess.LineageIssuedAt)
		require.Equal(t, 1, sess.Generation)
		require.Equal(t, now.Add(authSessionTTL), sess.ExpiresAt)
		require.Equal(t, sealedOrigin.Add(authMaxSessionAge), sess.LifetimeEndsAt)
	})

	t.Run("refuses a session past its refresh window", func(t *testing.T) {
		t.Parallel()
		sealer := unsealTo(unsealed(sealedOrigin, sealedOrigin, 0))

		refresh := app.BuildRefreshSession(sealer, fixedNow(sealedOrigin.Add(authRefreshWindow).Add(time.Nanosecond)))
		_, err := refresh(ctx, "flsess_handle", "iphash")
		require.ErrorIs(t, err, domain.ErrAuthSessionRefreshExpired)
	})

	t.Run("refreshes a session past its ttl", func(t *testing.T) {
		t.Parallel()
		sealer := unsealTo(unsealed(sealedOrigin, sealedOrigin, 0))

		refresh := app.BuildRefreshSession(sealer, fixedNow(sealedOrigin.Add(90*time.Minute)))
		_, err := refresh(ctx, "flsess_handle", "iphash")
		require.NoError(t, err, "the grace window between the ttl and refreshUntil is the point")
	})

	t.Run("propagates an unseal refusal", func(t *testing.T) {
		t.Parallel()
		sealer := &fakeSessionSealer{
			unsealFn: func(_ context.Context, _ string) (domain.AuthSession, error) {
				return domain.AuthSession{}, domain.ErrAuthSessionNotFound
			},
		}

		refresh := app.BuildRefreshSession(sealer, fixedNow(sealedOrigin))
		_, err := refresh(ctx, "garbage", "iphash")
		require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
	})

	t.Run("propagates a seal failure", func(t *testing.T) {
		t.Parallel()
		sealFailed := errors.New("seal failed")
		sealer := unsealTo(unsealed(sealedOrigin, sealedOrigin, 0))
		sealer.sealFn = func(_ context.Context, _ domain.AuthSession) (domain.AuthSession, error) {
			return domain.AuthSession{}, sealFailed
		}

		refresh := app.BuildRefreshSession(sealer, fixedNow(sealedOrigin.Add(time.Minute)))
		_, err := refresh(ctx, "flsess_handle", "iphash")
		require.ErrorIs(t, err, sealFailed)
	})
}
