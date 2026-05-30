package app_test

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
)

func TestBuildRefreshSession(t *testing.T) {
	t.Parallel()

	ctx := context.Background()

	// refreshUpdateRepo wires up Update so the test's "current session"
	// value is passed to the fn under test, and the fn's transformed
	// result is returned to the caller as if it had been persisted.
	refreshUpdateRepo := func(t *testing.T, current domain.AuthSession, wantID string) *fakeAuthSessionRepo {
		return &fakeAuthSessionRepo{
			updateFn: func(_ context.Context, id string, fn func(domain.AuthSession) (domain.AuthSession, error)) (domain.AuthSession, error) {
				require.Equal(t, wantID, id)
				return fn(current)
			},
		}
	}

	t.Run("bumps lifetimes and ip_hash on a valid session", func(t *testing.T) {
		t.Parallel()
		now := time.Date(2026, 1, 1, 12, 30, 0, 0, time.UTC)
		current := domain.AuthSession{
			ID:             "flsess_sid",
			IdentityType:   domain.AuthSessionIdentityAnonymous,
			IdentityKey:    "user-A",
			IPHash:         "old-ip",
			CreatedAt:      now.Add(-30 * time.Minute),
			ExpiresAt:      now.Add(30 * time.Minute),
			RefreshUntil:   now.Add(90 * time.Minute),
			LifetimeEndsAt: now.Add(authMaxSessionAge - 30*time.Minute),
			LastUsedAt:     now.Add(-30 * time.Minute),
		}

		refresh := app.BuildRefreshSession(refreshUpdateRepo(t, current, "flsess_sid"), func() time.Time { return now })
		session, err := refresh(ctx, "flsess_sid", "new-ip")
		require.NoError(t, err)

		require.Equal(t, "flsess_sid", session.ID)
		require.Equal(t, now.Add(authSessionTTL), session.ExpiresAt)
		require.Equal(t, now.Add(authRefreshWindow), session.RefreshUntil)
	})

	t.Run("update callback returns the exact session the repo would persist", func(t *testing.T) {
		t.Parallel()
		// The use case's contract with the repo is "call my update
		// closure on the current row and persist whatever it returns."
		// This test captures the closure's *output* directly so we pin
		// down every field — including the ones that aren't part of
		// the use case's return value (IPHash, LastUsedAt) and the
		// immutable fields (ID, IdentityType, CreatedAt,
		// LifetimeEndsAt) that must round-trip unchanged.
		now := time.Date(2026, 1, 1, 12, 30, 0, 0, time.UTC)
		current := domain.AuthSession{
			ID:             "flsess_sid",
			IdentityType:   domain.AuthSessionIdentityAnonymous,
			IdentityKey:    "user-A",
			IPHash:         "old-ip",
			CreatedAt:      now.Add(-30 * time.Minute),
			ExpiresAt:      now.Add(30 * time.Minute),
			RefreshUntil:   now.Add(90 * time.Minute),
			LifetimeEndsAt: now.Add(authMaxSessionAge - 30*time.Minute),
			LastUsedAt:     now.Add(-30 * time.Minute),
		}

		var captured domain.AuthSession
		repo := &fakeAuthSessionRepo{
			updateFn: func(_ context.Context, id string, fn func(domain.AuthSession) (domain.AuthSession, error)) (domain.AuthSession, error) {
				require.Equal(t, "flsess_sid", id)
				updated, err := fn(current)
				captured = updated
				return updated, err
			},
		}

		refresh := app.BuildRefreshSession(repo, func() time.Time { return now })
		_, err := refresh(ctx, "flsess_sid", "new-ip")
		require.NoError(t, err)

		require.Equal(t, domain.AuthSession{
			ID:             current.ID,
			IdentityType:   current.IdentityType,
			IdentityKey:    current.IdentityKey,
			IPHash:         "new-ip",
			CreatedAt:      current.CreatedAt,
			ExpiresAt:      now.Add(authSessionTTL),
			RefreshUntil:   now.Add(authRefreshWindow),
			LifetimeEndsAt: current.LifetimeEndsAt,
			LastUsedAt:     now,
		}, captured)
	})

	t.Run("rejects refresh past refresh_until", func(t *testing.T) {
		t.Parallel()
		now := time.Date(2026, 1, 1, 12, 30, 0, 0, time.UTC)
		current := domain.AuthSession{
			ID:             "flsess_sid",
			IdentityType:   domain.AuthSessionIdentityAnonymous,
			CreatedAt:      now.Add(-3 * time.Hour),
			ExpiresAt:      now.Add(-2 * time.Hour),
			RefreshUntil:   now.Add(-1 * time.Hour),
			LifetimeEndsAt: now.Add(authMaxSessionAge - 3*time.Hour),
			LastUsedAt:     now.Add(-3 * time.Hour),
		}
		refresh := app.BuildRefreshSession(refreshUpdateRepo(t, current, "flsess_sid"), func() time.Time { return now })
		_, err := refresh(ctx, "flsess_sid", "ip")
		require.ErrorIs(t, err, domain.ErrAuthSessionRefreshExpired)
	})

	t.Run("rejects refresh past lifetime_ends_at", func(t *testing.T) {
		t.Parallel()
		now := time.Date(2026, 1, 1, 12, 30, 0, 0, time.UTC)
		current := domain.AuthSession{
			ID:           "flsess_sid",
			IdentityType: domain.AuthSessionIdentityAnonymous,
			CreatedAt:    now.Add(-(authMaxSessionAge + time.Hour)),
			// refresh_until still ahead, but the absolute lifetime cap
			// has passed — refresh must refuse.
			ExpiresAt:      now.Add(30 * time.Minute),
			RefreshUntil:   now.Add(90 * time.Minute),
			LifetimeEndsAt: now.Add(-time.Hour),
			LastUsedAt:     now.Add(-(authMaxSessionAge + time.Hour)),
		}
		refresh := app.BuildRefreshSession(refreshUpdateRepo(t, current, "flsess_sid"), func() time.Time { return now })
		_, err := refresh(ctx, "flsess_sid", "ip")
		require.ErrorIs(t, err, domain.ErrAuthSessionRefreshExpired)
	})

	t.Run("clamps new expires_at and refresh_until to lifetime_ends_at", func(t *testing.T) {
		t.Parallel()
		now := time.Date(2026, 1, 1, 12, 30, 0, 0, time.UTC)
		// Lifetime ends 30 min from now — both the 1h expires window
		// and the 2h refresh window should get clipped to that.
		lifetimeEndsAt := now.Add(30 * time.Minute)
		current := domain.AuthSession{
			ID:             "flsess_sid",
			IdentityType:   domain.AuthSessionIdentityAnonymous,
			CreatedAt:      now.Add(-(authMaxSessionAge - 30*time.Minute)),
			ExpiresAt:      now.Add(5 * time.Minute),
			RefreshUntil:   now.Add(25 * time.Minute),
			LifetimeEndsAt: lifetimeEndsAt,
			LastUsedAt:     now.Add(-(authMaxSessionAge - 30*time.Minute)),
		}
		refresh := app.BuildRefreshSession(refreshUpdateRepo(t, current, "flsess_sid"), func() time.Time { return now })
		session, err := refresh(ctx, "flsess_sid", "ip")
		require.NoError(t, err)
		require.Equal(t, lifetimeEndsAt, session.ExpiresAt)
		require.Equal(t, lifetimeEndsAt, session.RefreshUntil)
	})

	t.Run("missing id returns ErrAuthSessionNotFound", func(t *testing.T) {
		t.Parallel()
		repo := &fakeAuthSessionRepo{
			updateFn: func(_ context.Context, _ string, _ func(domain.AuthSession) (domain.AuthSession, error)) (domain.AuthSession, error) {
				return domain.AuthSession{}, domain.ErrAuthSessionNotFound
			},
		}
		refresh := app.BuildRefreshSession(repo, time.Now)
		_, err := refresh(ctx, "no-such", "ip")
		require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
	})

	t.Run("empty id rejected without a lookup", func(t *testing.T) {
		t.Parallel()
		refresh := app.BuildRefreshSession(&fakeAuthSessionRepo{}, time.Now)
		_, err := refresh(ctx, "", "ip")
		require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
	})
}
