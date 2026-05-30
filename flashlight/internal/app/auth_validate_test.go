package app_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
)

// validateUpdateRepo wires up Update so the test's "current session"
// value is passed to the update closure, and the closure's
// transformed result is returned to the caller as if it had been
// persisted. Lets each test verify both the validation branches and
// the LastUsedAt mutation in one place.
func validateUpdateRepo(t *testing.T, current domain.AuthSession, wantID string) *fakeAuthSessionRepo {
	return &fakeAuthSessionRepo{
		updateFn: func(_ context.Context, id string, update func(domain.AuthSession) (domain.AuthSession, error)) (domain.AuthSession, error) {
			require.Equal(t, wantID, id)
			return update(current)
		},
	}
}

func TestBuildValidateSession(t *testing.T) {
	t.Parallel()

	ctx := context.Background()

	t.Run("returns session and bumps last_used_at for a valid session", func(t *testing.T) {
		t.Parallel()
		now := time.Date(2026, 1, 1, 12, 30, 0, 0, time.UTC)
		current := domain.AuthSession{
			ID:             "flsess_sid",
			IdentityType:   domain.AuthSessionIdentityAnonymous,
			IdentityKey:    "user-A",
			CreatedAt:      now.Add(-10 * time.Minute),
			ExpiresAt:      now.Add(50 * time.Minute),
			RefreshUntil:   now.Add(110 * time.Minute),
			LifetimeEndsAt: now.Add(authMaxSessionAge - 10*time.Minute),
			LastUsedAt:     now.Add(-5 * time.Minute),
		}

		var captured domain.AuthSession
		repo := &fakeAuthSessionRepo{
			updateFn: func(_ context.Context, id string, update func(domain.AuthSession) (domain.AuthSession, error)) (domain.AuthSession, error) {
				require.Equal(t, "flsess_sid", id)
				updated, err := update(current)
				captured = updated
				return updated, err
			},
		}

		validate := app.BuildValidateSession(repo, func() time.Time { return now }, cache.NewBasicCache[domain.AuthSession]())
		sess, err := validate(ctx, "flsess_sid")
		require.NoError(t, err)
		require.Equal(t, "flsess_sid", sess.ID)
		require.Equal(t, now, captured.LastUsedAt,
			"validate should bump LastUsedAt to now")
	})

	t.Run("second call within cache window skips the repository", func(t *testing.T) {
		t.Parallel()
		now := time.Date(2026, 1, 1, 12, 30, 0, 0, time.UTC)
		current := domain.AuthSession{
			ID:             "flsess_sid",
			IdentityType:   domain.AuthSessionIdentityAnonymous,
			IdentityKey:    "user-A",
			CreatedAt:      now.Add(-10 * time.Minute),
			ExpiresAt:      now.Add(50 * time.Minute),
			RefreshUntil:   now.Add(110 * time.Minute),
			LifetimeEndsAt: now.Add(authMaxSessionAge - 10*time.Minute),
			LastUsedAt:     now.Add(-5 * time.Minute),
		}

		updateCalls := 0
		repo := &fakeAuthSessionRepo{
			updateFn: func(_ context.Context, id string, update func(domain.AuthSession) (domain.AuthSession, error)) (domain.AuthSession, error) {
				updateCalls++
				return update(current)
			},
		}

		validate := app.BuildValidateSession(repo, func() time.Time { return now }, cache.NewBasicCache[domain.AuthSession]())
		_, err := validate(ctx, "flsess_sid")
		require.NoError(t, err)
		_, err = validate(ctx, "flsess_sid")
		require.NoError(t, err)
		require.Equal(t, 1, updateCalls,
			"second call should be served from cache without touching the repo")
	})

	t.Run("rejects expired session via the update closure", func(t *testing.T) {
		t.Parallel()
		now := time.Date(2026, 1, 1, 12, 30, 0, 0, time.UTC)
		current := domain.AuthSession{
			ID:             "flsess_sid",
			IdentityType:   domain.AuthSessionIdentityAnonymous,
			CreatedAt:      now.Add(-90 * time.Minute),
			ExpiresAt:      now.Add(-30 * time.Minute),
			RefreshUntil:   now.Add(30 * time.Minute),
			LifetimeEndsAt: now.Add(authMaxSessionAge - 90*time.Minute),
			LastUsedAt:     now.Add(-90 * time.Minute),
		}
		validate := app.BuildValidateSession(validateUpdateRepo(t, current, "flsess_sid"), func() time.Time { return now }, cache.NewBasicCache[domain.AuthSession]())
		_, err := validate(ctx, "flsess_sid")
		require.ErrorIs(t, err, domain.ErrAuthSessionExpired)
	})

	t.Run("rejects session past lifetime_ends_at", func(t *testing.T) {
		t.Parallel()
		now := time.Date(2026, 1, 1, 12, 30, 0, 0, time.UTC)
		current := domain.AuthSession{
			ID:           "flsess_sid",
			IdentityType: domain.AuthSessionIdentityAnonymous,
			CreatedAt:    now.Add(-(authMaxSessionAge + 5*time.Minute)),
			// Within expires_at but past the absolute lifetime cap:
			ExpiresAt:      now.Add(30 * time.Minute),
			RefreshUntil:   now.Add(60 * time.Minute),
			LifetimeEndsAt: now.Add(-5 * time.Minute),
			LastUsedAt:     now.Add(-(authMaxSessionAge + 5*time.Minute)),
		}
		validate := app.BuildValidateSession(validateUpdateRepo(t, current, "flsess_sid"), func() time.Time { return now }, cache.NewBasicCache[domain.AuthSession]())
		_, err := validate(ctx, "flsess_sid")
		require.ErrorIs(t, err, domain.ErrAuthSessionExpired)
	})

	t.Run("missing returns ErrAuthSessionNotFound", func(t *testing.T) {
		t.Parallel()
		repo := &fakeAuthSessionRepo{
			updateFn: func(_ context.Context, _ string, _ func(domain.AuthSession) (domain.AuthSession, error)) (domain.AuthSession, error) {
				return domain.AuthSession{}, domain.ErrAuthSessionNotFound
			},
		}
		validate := app.BuildValidateSession(repo, time.Now, cache.NewBasicCache[domain.AuthSession]())
		_, err := validate(ctx, "no-such")
		require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
	})

	t.Run("propagates repo errors", func(t *testing.T) {
		t.Parallel()
		repo := &fakeAuthSessionRepo{
			updateFn: func(_ context.Context, _ string, _ func(domain.AuthSession) (domain.AuthSession, error)) (domain.AuthSession, error) {
				return domain.AuthSession{}, errors.New("db down")
			},
		}
		validate := app.BuildValidateSession(repo, time.Now, cache.NewBasicCache[domain.AuthSession]())
		_, err := validate(ctx, "flsess_sid")
		require.Error(t, err)
	})

	t.Run("validation errors are not cached", func(t *testing.T) {
		t.Parallel()
		updateCalls := 0
		repo := &fakeAuthSessionRepo{
			updateFn: func(_ context.Context, _ string, _ func(domain.AuthSession) (domain.AuthSession, error)) (domain.AuthSession, error) {
				updateCalls++
				return domain.AuthSession{}, domain.ErrAuthSessionNotFound
			},
		}
		validate := app.BuildValidateSession(repo, time.Now, cache.NewBasicCache[domain.AuthSession]())
		_, err := validate(ctx, "flsess_sid")
		require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
		_, err = validate(ctx, "flsess_sid")
		require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
		require.Equal(t, 2, updateCalls,
			"failed validations should not be cached; both calls should hit the repo")
	})

	t.Run("empty id rejected without a lookup", func(t *testing.T) {
		t.Parallel()
		validate := app.BuildValidateSession(&fakeAuthSessionRepo{}, time.Now, cache.NewBasicCache[domain.AuthSession]())
		_, err := validate(ctx, "")
		require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
	})
}
