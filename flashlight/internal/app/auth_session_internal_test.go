package app

import (
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/domain"
)

// In-package: the deadline arithmetic and refreshed() are policy, not API,
// and the point of extracting them is testing them with no sealer at all.

var policyOrigin = time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)

// sealedSession is what Unseal produces: no deadlines, they are derived.
func sealedSession(issuedAt, lineageIssuedAt time.Time, generation int) domain.AuthSession {
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

func TestDeadlinesFor(t *testing.T) {
	t.Parallel()

	t.Run("derives all three from the two origins", func(t *testing.T) {
		t.Parallel()
		sess := sealedSession(policyOrigin, policyOrigin, 0)

		d, err := deadlinesFor(sess)
		require.NoError(t, err)
		require.Equal(t, policyOrigin.Add(authSessionTTL), d.expiresAt)
		require.Equal(t, policyOrigin.Add(authRefreshWindow), d.refreshUntil)
		require.Equal(t, policyOrigin.Add(authMaxSessionAge), d.lifetimeEndsAt)
	})

	t.Run("takes the cap from lineageIssuedAt, not from issuedAt", func(t *testing.T) {
		t.Parallel()
		// The reseal case: this handle was minted 20h into the chain.
		sess := sealedSession(policyOrigin.Add(20*time.Hour), policyOrigin, 40)

		d, err := deadlinesFor(sess)
		require.NoError(t, err)
		require.Equal(t, policyOrigin.Add(authMaxSessionAge), d.lifetimeEndsAt,
			"the cap belongs to the chain, so a reseal must not move it")
		require.Equal(t, policyOrigin.Add(20*time.Hour).Add(authSessionTTL), d.expiresAt,
			"the ttl belongs to this handle")
	})

	t.Run("clamps both refreshUntil and expiresAt to the cap", func(t *testing.T) {
		t.Parallel()
		// 23h30m in: both windows would land past the cap.
		sess := sealedSession(policyOrigin.Add(23*time.Hour+30*time.Minute), policyOrigin, 47)
		chainCap := policyOrigin.Add(authMaxSessionAge)

		d, err := deadlinesFor(sess)
		require.NoError(t, err)
		require.Equal(t, chainCap, d.refreshUntil)
		// Clamped because the client schedules off expiresAt: ports derives
		// both refreshInSeconds and the X-Auth-Refresh hint from
		// expiresAt - 5m, so an expiresAt past the cap puts the proactive
		// re-login *after* the session is already dead.
		require.Equal(t, chainCap, d.expiresAt)
	})

	t.Run("refuses a tier it cannot evaluate", func(t *testing.T) {
		t.Parallel()
		sess := sealedSession(policyOrigin, policyOrigin, 0)
		sess.IdentityType = domain.AuthSessionIdentityType("microsoft")

		_, err := deadlinesFor(sess)
		require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
	})

	t.Run("refuses a session missing either origin", func(t *testing.T) {
		t.Parallel()
		noIssuedAt := sealedSession(time.Time{}, policyOrigin, 0)
		_, err := deadlinesFor(noIssuedAt)
		require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)

		noLineageIssuedAt := sealedSession(policyOrigin, time.Time{}, 0)
		_, err = deadlinesFor(noLineageIssuedAt)
		require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
	})
}

func TestWithDeadlines(t *testing.T) {
	t.Parallel()

	sess := sealedSession(policyOrigin, policyOrigin, 0)
	filled, err := withDeadlines(sess)
	require.NoError(t, err)

	require.Equal(t, policyOrigin.Add(authSessionTTL), filled.ExpiresAt)
	require.Equal(t, policyOrigin.Add(authRefreshWindow), filled.RefreshUntil)
	require.Equal(t, policyOrigin.Add(authMaxSessionAge), filled.LifetimeEndsAt)
	// Everything else survives untouched.
	require.Equal(t, sess.ID, filled.ID)
	require.Equal(t, sess.IdentityKey, filled.IdentityKey)
	require.Equal(t, sess.CreatedAt, filled.CreatedAt)
	require.Equal(t, sess.LineageIssuedAt, filled.LineageIssuedAt)
	require.Equal(t, sess.Lineage, filled.Lineage)
	require.Equal(t, sess.Generation, filled.Generation)
}

func TestRefreshed(t *testing.T) {
	t.Parallel()

	t.Run("re-stamps issuedAt, copies the lineage, bumps the generation", func(t *testing.T) {
		t.Parallel()
		sess := sealedSession(policyOrigin, policyOrigin, 3)
		now := policyOrigin.Add(30 * time.Minute)

		next, err := refreshed(sess, now)
		require.NoError(t, err)

		require.Equal(t, now, next.CreatedAt, "issuedAt is this handle's, so a reseal re-stamps it")
		require.Equal(t, policyOrigin, next.LineageIssuedAt, "the chain origin is copied, never re-stamped")
		require.Equal(t, sess.Lineage, next.Lineage)
		require.Equal(t, 4, next.Generation)
		require.Equal(t, sess.IdentityType, next.IdentityType)
		require.Equal(t, sess.IdentityKey, next.IdentityKey)
	})

	t.Run("clears the id, because Seal mints the handle", func(t *testing.T) {
		t.Parallel()
		next, err := refreshed(sealedSession(policyOrigin, policyOrigin, 0), policyOrigin.Add(time.Minute))
		require.NoError(t, err)
		require.Empty(t, next.ID)
	})

	t.Run("derives the new deadlines from the new issuedAt", func(t *testing.T) {
		t.Parallel()
		now := policyOrigin.Add(90 * time.Minute)

		next, err := refreshed(sealedSession(policyOrigin, policyOrigin, 0), now)
		require.NoError(t, err)
		require.Equal(t, now.Add(authSessionTTL), next.ExpiresAt)
		require.Equal(t, now.Add(authRefreshWindow), next.RefreshUntil)
		require.Equal(t, policyOrigin.Add(authMaxSessionAge), next.LifetimeEndsAt)
	})

	t.Run("refuses past the refresh window", func(t *testing.T) {
		t.Parallel()
		sess := sealedSession(policyOrigin, policyOrigin, 0)

		_, err := refreshed(sess, policyOrigin.Add(authRefreshWindow))
		require.NoError(t, err, "exactly at refreshUntil is still allowed")

		_, err = refreshed(sess, policyOrigin.Add(authRefreshWindow).Add(time.Nanosecond))
		require.ErrorIs(t, err, domain.ErrAuthSessionRefreshExpired)
	})

	t.Run("refuses at the absolute cap", func(t *testing.T) {
		t.Parallel()
		// 23h30m in, so the refresh window is still open but the cap is not.
		sess := sealedSession(policyOrigin.Add(23*time.Hour+30*time.Minute), policyOrigin, 47)

		_, err := refreshed(sess, policyOrigin.Add(authMaxSessionAge))
		require.ErrorIs(t, err, domain.ErrAuthSessionRefreshExpired,
			"the cap is exclusive: reaching it ends the chain")
	})

	t.Run("the last refresh is pinned to the cap on both windows", func(t *testing.T) {
		t.Parallel()
		sess := sealedSession(policyOrigin.Add(23*time.Hour), policyOrigin, 46)
		now := policyOrigin.Add(23*time.Hour + 30*time.Minute)

		next, err := refreshed(sess, now)
		require.NoError(t, err)
		require.Equal(t, next.LifetimeEndsAt, next.RefreshUntil,
			"pinned refreshUntil is what makes canRefresh false on the wire")
		require.Equal(t, next.LifetimeEndsAt, next.ExpiresAt,
			"so the client's re-login timer fires before the session dies, not after")
	})

	t.Run("refuses a tier it cannot evaluate", func(t *testing.T) {
		t.Parallel()
		sess := sealedSession(policyOrigin, policyOrigin, 0)
		sess.IdentityType = domain.AuthSessionIdentityType("microsoft")

		_, err := refreshed(sess, policyOrigin.Add(time.Minute))
		require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
	})

	// The load-bearing case: a re-stamped chain origin, or a cap read off
	// the per-handle issuedAt, makes refresh an unbounded lifetime
	// extension, silently.
	t.Run("a chain of reseals never moves the derived cap", func(t *testing.T) {
		t.Parallel()
		wantCap := policyOrigin.Add(authMaxSessionAge)

		sess := sealedSession(policyOrigin, policyOrigin, 0)
		now := policyOrigin
		for i := 1; i <= 40; i++ {
			now = now.Add(30 * time.Minute)

			next, err := refreshed(sess, now)
			require.NoError(t, err, "refresh %d should still be inside the 24h chain", i)
			require.Equal(t, wantCap, next.LifetimeEndsAt, "refresh %d moved the cap", i)
			require.Equal(t, policyOrigin, next.LineageIssuedAt, "refresh %d re-stamped the chain origin", i)
			require.Equal(t, sess.Lineage, next.Lineage, "refresh %d minted a new lineage", i)
			require.Equal(t, i, next.Generation)

			sess = next
			sess.ID = "flsess_handle"
		}

		// 20h of chain spent above; the cap is what ends it, not the window.
		_, err := refreshed(sess, policyOrigin.Add(authMaxSessionAge))
		require.ErrorIs(t, err, domain.ErrAuthSessionRefreshExpired)
	})
}
