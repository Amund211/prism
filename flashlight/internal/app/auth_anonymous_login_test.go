package app_test

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
)

// allowFunc satisfies the app package's unexported issuanceGuard by
// structural typing, the same way fakeSessionSealer does. Login-specific,
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

const testLineage = "fllineage_0190d3c1-8f2a-7d3e-9c11-4a6b8e2f0d55"

func fixedLineage() func() (string, error) {
	return func() (string, error) { return testLineage, nil }
}

func TestBuildAnonymousLogin(t *testing.T) {
	t.Parallel()

	ctx := context.Background()

	t.Run("seals a generation-0 session whose two origins are both now", func(t *testing.T) {
		t.Parallel()
		now := time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)

		var allowCalled bool
		var sealed domain.AuthSession
		sealer := &fakeSessionSealer{
			sealFn: func(_ context.Context, s domain.AuthSession) (domain.AuthSession, error) {
				sealed = s
				s.ID = "flsess_body.sig"
				return s, nil
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

		login := app.BuildAnonymousLogin(sealer, guard, fixedNow(now), fixedLineage())
		sess, err := login(ctx, "user-12345", "iphash-abc")
		require.NoError(t, err)

		require.True(t, allowCalled, "the guard must be consulted on every issue")
		require.Equal(t, "flsess_body.sig", sess.ID, "the handle is whatever Seal minted")

		require.Equal(t, domain.AuthSessionIdentityAnonymous, sealed.IdentityType)
		require.Equal(t, "user-12345", sealed.IdentityKey)
		require.Equal(t, testLineage, sealed.Lineage)
		require.Equal(t, 0, sealed.Generation, "a login starts the chain")
		require.Equal(t, now, sealed.CreatedAt)
		require.Equal(t, now, sealed.LineageIssuedAt,
			"at login the handle's origin and the chain's origin are the same instant")

		// The deadlines ports reports as durations, derived rather than
		// stamped — so a login and a reseal answer through one function.
		require.Equal(t, now.Add(authSessionTTL), sess.ExpiresAt)
		require.Equal(t, now.Add(authRefreshWindow), sess.RefreshUntil)
		require.Equal(t, now.Add(authMaxSessionAge), sess.LifetimeEndsAt)
	})

	t.Run("the sealed handle carries the flsess_ prefix through the real sealer", func(t *testing.T) {
		t.Parallel()
		// Released rainbow throws on a login response whose handle lacks
		// the prefix, so this is a wire contract and not cosmetics.
		now := time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)

		login := app.BuildAnonymousLogin(newTestSealer(t), allowAll(), fixedNow(now), fixedLineage())
		sess, err := login(ctx, "user-12345", "iphash-abc")
		require.NoError(t, err)
		require.True(t, strings.HasPrefix(sess.ID, "flsess_"),
			"login must hand back a flsess_-prefixed handle")
		require.Contains(t, sess.ID, ".", "the handle is <signed>.<signature>")
	})

	t.Run("propagates guard refusals and seals nothing", func(t *testing.T) {
		t.Parallel()
		sealer := &fakeSessionSealer{
			sealFn: func(_ context.Context, _ domain.AuthSession) (domain.AuthSession, error) {
				t.Fatal("Seal should not be called when the guard refuses")
				return domain.AuthSession{}, nil
			},
		}
		guard := allowFunc(func(_ context.Context, _ domain.AuthSessionIdentityType, _ string, _ string, _ time.Time) error {
			return fmt.Errorf("some cap reached: %w", domain.ErrAuthSessionIssuanceRefused)
		})
		lineage := func() (string, error) {
			t.Fatal("the lineage should not be minted when the guard refuses")
			return "", nil
		}

		login := app.BuildAnonymousLogin(sealer, guard, time.Now, lineage)
		_, err := login(ctx, "user-A", "ipA")
		require.ErrorIs(t, err, domain.ErrAuthSessionIssuanceRefused,
			"the wrap has to keep the refusal classifiable, or ports answers it with a 500")
	})

	t.Run("propagates lineage generator errors and seals nothing", func(t *testing.T) {
		t.Parallel()
		sealer := &fakeSessionSealer{
			sealFn: func(_ context.Context, _ domain.AuthSession) (domain.AuthSession, error) {
				t.Fatal("Seal should not be called when the lineage cannot be minted")
				return domain.AuthSession{}, nil
			},
		}
		lineage := func() (string, error) { return "", errors.New("rand failed") }

		login := app.BuildAnonymousLogin(sealer, allowAll(), time.Now, lineage)
		_, err := login(ctx, "user-A", "ipA")
		require.Error(t, err)
	})

	t.Run("propagates seal failures", func(t *testing.T) {
		t.Parallel()
		sealer := &fakeSessionSealer{
			sealFn: func(_ context.Context, _ domain.AuthSession) (domain.AuthSession, error) {
				return domain.AuthSession{}, errors.New("seal failed")
			},
		}

		login := app.BuildAnonymousLogin(sealer, allowAll(), time.Now, fixedLineage())
		_, err := login(ctx, "user-A", "ipA")
		require.Error(t, err)
	})
}

// The cutover's whole claim, end to end through the production sealer: a
// login validates, a refresh of it rotates the handle without moving the
// chain cap, and the parent keeps working.
func TestLoginValidatesAndRefreshesThroughTheSignedSealer(t *testing.T) {
	t.Parallel()

	ctx := context.Background()
	now := time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)
	sealer := newTestSealer(t)

	login := app.BuildAnonymousLogin(sealer, allowAll(), fixedNow(now), app.GenerateLineage)
	issued, err := login(ctx, "user-12345", "iphash-abc")
	require.NoError(t, err)

	later := now.Add(30 * time.Minute)
	validate := app.BuildValidateSession(sealer, fixedNow(later))
	validated, err := validate(ctx, issued.ID)
	require.NoError(t, err)
	require.Equal(t, "user-12345", validated.IdentityKey)
	require.Equal(t, issued.LifetimeEndsAt, validated.LifetimeEndsAt)

	refreshed, err := app.BuildRefreshSession(sealer, fixedNow(later))(ctx, issued.ID, "iphash-abc")
	require.NoError(t, err)
	require.NotEqual(t, issued.ID, refreshed.ID, "every refresh rotates the handle")
	require.Equal(t, issued.Lineage, refreshed.Lineage)
	require.Equal(t, 1, refreshed.Generation)
	require.Equal(t, issued.LifetimeEndsAt, refreshed.LifetimeEndsAt,
		"a refresh must not move the chain cap")

	_, err = validate(ctx, refreshed.ID)
	require.NoError(t, err)
	_, err = validate(ctx, issued.ID)
	require.NoError(t, err, "a refreshed parent is not revoked")
}

func TestGenerateLineage(t *testing.T) {
	t.Parallel()

	first, err := app.GenerateLineage()
	require.NoError(t, err)
	second, err := app.GenerateLineage()
	require.NoError(t, err)

	// A literal, so the test fails if the production prefix drifts.
	require.True(t, strings.HasPrefix(first, "fllineage_"),
		"lineages must start with the literal fllineage_ prefix")
	require.NotEqual(t, first, second)
	// prefix + a hyphenated uuid
	require.Len(t, first, len("fllineage_")+36)
}
