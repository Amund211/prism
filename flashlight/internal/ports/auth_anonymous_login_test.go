package ports_test

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ports"
)

func TestAnonymousLoginHandler(t *testing.T) {
	t.Parallel()

	// fixedNow returns a stable nowFunc and the matching base time —
	// gives the test deterministic deltas to assert against.
	fixedNow := func(t time.Time) func() time.Time {
		return func() time.Time { return t }
	}

	t.Run("returns 200 with duration-based session payload", func(t *testing.T) {
		t.Parallel()
		now := time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)
		var sawUserID, sawIPHash string
		login := func(ctx context.Context, userID, ipHash string) (domain.AuthSession, error) {
			sawUserID = userID
			sawIPHash = ipHash
			return domain.AuthSession{
				ID:             "sid-123",
				IdentityType:   domain.AuthSessionIdentityAnonymous,
				IdentityKey:    userID,
				CreatedAt:      now,
				ExpiresAt:      now.Add(1 * time.Hour),
				RefreshUntil:   now.Add(2 * time.Hour),
				LifetimeEndsAt: now.Add(24 * time.Hour),
			}, nil
		}

		handler := ports.MakeAnonymousLoginHandler(login, fixedNow(now), authTestLogger, noopAuthMiddleware, ports.BlocklistConfig{})
		body := strings.NewReader(`{"userId":"user-abc"}`)
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", body)
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()

		handler(w, r)

		require.Equal(t, http.StatusOK, w.Code)
		require.Equal(t, "application/json", w.Header().Get("Content-Type"))

		var resp struct {
			SessionID             string `json:"sessionId"`
			Tier                  string `json:"tier"`
			ExpiresInSeconds      int64  `json:"expiresInSeconds"`
			RefreshUntilInSeconds int64  `json:"refreshUntilInSeconds"`
			RefreshInSeconds      int64  `json:"refreshInSeconds"`
			CanRefresh            bool   `json:"canRefresh"`
		}
		require.NoError(t, json.NewDecoder(w.Body).Decode(&resp))
		require.Equal(t, "sid-123", resp.SessionID)
		require.Equal(t, "anonymous", resp.Tier)
		require.Equal(t, int64(3600), resp.ExpiresInSeconds, "expires_at = now + 1h")
		require.Equal(t, int64(7200), resp.RefreshUntilInSeconds, "refresh_until = now + 2h")
		require.Equal(t, int64(3300), resp.RefreshInSeconds, "refresh_at = expires_at - 5min = now + 55min")
		require.True(t, resp.CanRefresh,
			"refresh_until < lifetime_ends_at; next refresh can still grant a full window")
		require.Equal(t, "user-abc", sawUserID)
		require.NotEmpty(t, sawIPHash)
	})

	t.Run("sets Cache-Control: no-store on the session response", func(t *testing.T) {
		t.Parallel()
		now := time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)
		login := func(ctx context.Context, userID, ipHash string) (domain.AuthSession, error) {
			return domain.AuthSession{
				ID:             "sid-cache",
				IdentityType:   domain.AuthSessionIdentityAnonymous,
				IdentityKey:    userID,
				CreatedAt:      now,
				ExpiresAt:      now.Add(1 * time.Hour),
				RefreshUntil:   now.Add(2 * time.Hour),
				LifetimeEndsAt: now.Add(24 * time.Hour),
			}, nil
		}
		handler := ports.MakeAnonymousLoginHandler(login, fixedNow(now), authTestLogger, noopAuthMiddleware, ports.BlocklistConfig{})
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(`{"userId":"user-abc"}`))
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusOK, w.Code)
		require.Equal(t, "no-store", w.Header().Get("Cache-Control"),
			"session responses carry a bearer token; no intermediary should cache them")
	})

	t.Run("canRefresh is false on the last refresh whose refresh_until got pinned to lifetime_ends_at", func(t *testing.T) {
		t.Parallel()
		now := time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)
		// Refresh near the cap: refresh_until exactly equals lifetime_ends_at.
		// expires_at still has a normal 1h ahead — the client gets a
		// full session this time but should re-auth on the next tick.
		login := func(ctx context.Context, userID, ipHash string) (domain.AuthSession, error) {
			capAt := now.Add(90 * time.Minute)
			return domain.AuthSession{
				ID:             "sid-late",
				IdentityType:   domain.AuthSessionIdentityAnonymous,
				IdentityKey:    userID,
				CreatedAt:      now.Add(-22 * time.Hour),
				ExpiresAt:      now.Add(60 * time.Minute),
				RefreshUntil:   capAt,
				LifetimeEndsAt: capAt,
			}, nil
		}
		handler := ports.MakeAnonymousLoginHandler(login, fixedNow(now), authTestLogger, noopAuthMiddleware, ports.BlocklistConfig{})
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(`{"userId":"user-late"}`))
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusOK, w.Code)

		var resp struct {
			ExpiresInSeconds int64 `json:"expiresInSeconds"`
			CanRefresh       bool  `json:"canRefresh"`
		}
		require.NoError(t, json.NewDecoder(w.Body).Decode(&resp))
		require.Equal(t, int64(3600), resp.ExpiresInSeconds,
			"client should still get a full session this round")
		require.False(t, resp.CanRefresh,
			"refresh_until == lifetime_ends_at; next refresh is clamped, so client must re-auth instead")
	})

	t.Run("400 on invalid userId", func(t *testing.T) {
		t.Parallel()
		login := func(ctx context.Context, userID, ipHash string) (domain.AuthSession, error) {
			t.Fatal("login should not be called when userId is invalid")
			return domain.AuthSession{}, nil
		}
		handler := ports.MakeAnonymousLoginHandler(login, time.Now, authTestLogger, noopAuthMiddleware, ports.BlocklistConfig{})
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(`{"userId":""}`))
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusBadRequest, w.Code)
	})

	t.Run("400 on userId longer than the hard cap", func(t *testing.T) {
		t.Parallel()
		login := func(ctx context.Context, userID, ipHash string) (domain.AuthSession, error) {
			t.Fatal("login should not be called when userId is too long")
			return domain.AuthSession{}, nil
		}
		handler := ports.MakeAnonymousLoginHandler(login, time.Now, authTestLogger, noopAuthMiddleware, ports.BlocklistConfig{})
		// 101 chars — past the 100-char hard cap.
		body := fmt.Sprintf(`{"userId":%q}`, strings.Repeat("x", 101))
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(body))
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusBadRequest, w.Code)
	})

	t.Run("accepts userId in the warn band (above 50, within 100)", func(t *testing.T) {
		t.Parallel()
		// 60 chars — over the previous limit but under the new cap.
		// Behaviour change introduced when we bumped the cap to 100;
		// the request also fires a reporting.Report call which Sentry
		// will pick up (not verified here since the reporter is global).
		longID := strings.Repeat("x", 60)
		var sawUserID string
		login := func(ctx context.Context, userID, ipHash string) (domain.AuthSession, error) {
			sawUserID = userID
			now := time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)
			return domain.AuthSession{
				ID:             "sid-warn",
				IdentityType:   domain.AuthSessionIdentityAnonymous,
				IdentityKey:    userID,
				CreatedAt:      now,
				ExpiresAt:      now.Add(1 * time.Hour),
				RefreshUntil:   now.Add(2 * time.Hour),
				LifetimeEndsAt: now.Add(24 * time.Hour),
			}, nil
		}
		handler := ports.MakeAnonymousLoginHandler(login, time.Now, authTestLogger, noopAuthMiddleware, ports.BlocklistConfig{})
		body := fmt.Sprintf(`{"userId":%q}`, longID)
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(body))
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusOK, w.Code)
		require.Equal(t, longID, sawUserID)
	})

	t.Run("400 on malformed JSON", func(t *testing.T) {
		t.Parallel()
		login := func(ctx context.Context, userID, ipHash string) (domain.AuthSession, error) {
			t.Fatal("login should not be called on malformed body")
			return domain.AuthSession{}, nil
		}
		handler := ports.MakeAnonymousLoginHandler(login, time.Now, authTestLogger, noopAuthMiddleware, ports.BlocklistConfig{})
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(`not-json`))
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusBadRequest, w.Code)
	})
}
