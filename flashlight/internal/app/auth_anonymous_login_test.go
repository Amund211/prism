package app_test

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
)

// allowFunc satisfies the app package's unexported issuanceGuard by
// structural typing, the same way fakeAuthSessionRepo does. Login-specific,
// so it lives here rather than in the shared helpers.
type allowFunc func(ctx context.Context, identityType domain.AuthSessionIdentityType, identityKey string, ipHash string, now time.Time) error

func (f allowFunc) Allow(ctx context.Context, identityType domain.AuthSessionIdentityType, identityKey string, ipHash string, now time.Time) error {
	return f(ctx, identityType, identityKey, ipHash, now)
}

func allowAll() allowFunc {
	return func(_ context.Context, _ domain.AuthSessionIdentityType, _ string, _ string, _ time.Time) error {
		return nil
	}
}

func TestBuildAnonymousLogin(t *testing.T) {
	t.Parallel()

	ctx := context.Background()

	t.Run("issues a session with computed timestamps and a generated id", func(t *testing.T) {
		t.Parallel()
		now := time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)

		var allowCalled, createCalled, generated bool
		repo := &fakeAuthSessionRepo{
			createFn: func(_ context.Context, sess domain.AuthSession) error {
				createCalled = true
				require.Equal(t, "flsess_test-id", sess.ID)
				require.Equal(t, domain.AuthSessionIdentityAnonymous, sess.IdentityType)
				require.Equal(t, "user-12345", sess.IdentityKey)
				require.Equal(t, "iphash-abc", sess.IPHash)
				require.Equal(t, now, sess.CreatedAt)
				require.Equal(t, now.Add(authSessionTTL), sess.ExpiresAt)
				require.Equal(t, now.Add(authRefreshWindow), sess.RefreshUntil)
				require.Equal(t, now, sess.LastUsedAt,
					"app should set LastUsedAt to CreatedAt on issue")
				return nil
			},
		}
		guard := allowFunc(func(_ context.Context, identityType domain.AuthSessionIdentityType, identityKey string, ipHash string, guardNow time.Time) error {
			allowCalled = true
			require.Equal(t, domain.AuthSessionIdentityAnonymous, identityType)
			require.Equal(t, "user-12345", identityKey)
			require.Equal(t, "iphash-abc", ipHash)
			require.Equal(t, now, guardNow)
			return nil
		})
		generate := func() (string, error) {
			generated = true
			return "flsess_test-id", nil
		}

		login := app.BuildAnonymousLogin(repo, guard, func() time.Time { return now }, generate)
		sess, err := login(ctx, "user-12345", "iphash-abc")
		require.NoError(t, err)

		require.True(t, allowCalled, "the guard must be consulted on every issue")
		require.True(t, generated)
		require.True(t, createCalled)
		require.Equal(t, "flsess_test-id", sess.ID)
		require.Equal(t, now, sess.LastUsedAt)
	})

	t.Run("propagates guard refusals and does not generate or Create", func(t *testing.T) {
		t.Parallel()
		repo := &fakeAuthSessionRepo{}
		guard := allowFunc(func(_ context.Context, _ domain.AuthSessionIdentityType, _ string, _ string, _ time.Time) error {
			return fmt.Errorf("some cap reached: %w", domain.ErrAuthSessionIssuanceRefused)
		})
		generate := func() (string, error) {
			t.Fatal("generate should not be called when the guard refuses")
			return "", nil
		}
		login := app.BuildAnonymousLogin(repo, guard, time.Now, generate)
		_, err := login(ctx, "user-A", "ipA")
		require.ErrorIs(t, err, domain.ErrAuthSessionIssuanceRefused,
			"the wrap has to keep the refusal classifiable, or ports answers it with a 500")
	})

	t.Run("propagates generator errors and does not Create", func(t *testing.T) {
		t.Parallel()
		repo := &fakeAuthSessionRepo{}
		generate := func() (string, error) {
			return "", errors.New("rand failed")
		}
		login := app.BuildAnonymousLogin(repo, allowAll(), time.Now, generate)
		_, err := login(ctx, "user-A", "ipA")
		require.Error(t, err)
	})
}
