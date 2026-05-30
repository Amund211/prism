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

// authAnonymousIPCap mirrors the production constant in
// auth_anonymous_login.go. Kept here because it's anonymous-specific
// and only referenced by these tests.
const authAnonymousIPCap = 4

func TestBuildAnonymousLogin(t *testing.T) {
	t.Parallel()

	ctx := context.Background()

	t.Run("issues a session with computed timestamps and a generated id", func(t *testing.T) {
		t.Parallel()
		now := time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)

		var enforceCalled, createCalled, generated bool
		repo := &fakeAuthSessionRepo{
			enforceActiveIPCapFn: func(_ context.Context, identityType domain.AuthSessionIdentityType, ipHash string, maxActive int, capNow time.Time) error {
				enforceCalled = true
				require.Equal(t, domain.AuthSessionIdentityAnonymous, identityType)
				require.Equal(t, "iphash-abc", ipHash)
				require.Equal(t, authAnonymousIPCap, maxActive)
				require.Equal(t, now, capNow)
				return nil
			},
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
		generate := func() (string, error) {
			generated = true
			return "flsess_test-id", nil
		}

		login := app.BuildAnonymousLogin(repo, func() time.Time { return now }, generate)
		sess, err := login(ctx, "user-12345", "iphash-abc")
		require.NoError(t, err)

		require.True(t, enforceCalled)
		require.True(t, generated)
		require.True(t, createCalled)
		require.Equal(t, "flsess_test-id", sess.ID)
		require.Equal(t, now, sess.LastUsedAt)
	})

	t.Run("propagates EnforceActiveIPCap errors and does not generate or Create", func(t *testing.T) {
		t.Parallel()
		repo := &fakeAuthSessionRepo{
			enforceActiveIPCapFn: func(_ context.Context, _ domain.AuthSessionIdentityType, _ string, _ int, _ time.Time) error {
				return errors.New("ip cap query failed")
			},
		}
		generate := func() (string, error) {
			t.Fatal("generate should not be called when EnforceActiveIPCap fails")
			return "", nil
		}
		login := app.BuildAnonymousLogin(repo, time.Now, generate)
		_, err := login(ctx, "user-A", "ipA")
		require.Error(t, err)
	})

	t.Run("propagates generator errors and does not Create", func(t *testing.T) {
		t.Parallel()
		repo := &fakeAuthSessionRepo{
			enforceActiveIPCapFn: func(_ context.Context, _ domain.AuthSessionIdentityType, _ string, _ int, _ time.Time) error {
				return nil
			},
		}
		generate := func() (string, error) {
			return "", errors.New("rand failed")
		}
		login := app.BuildAnonymousLogin(repo, time.Now, generate)
		_, err := login(ctx, "user-A", "ipA")
		require.Error(t, err)
	})
}
