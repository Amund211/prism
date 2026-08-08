package ports_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/domain"
)

func TestAuthRefreshHandler(t *testing.T) {
	t.Parallel()

	t.Run("happy path returns refreshed session payload", func(t *testing.T) {
		t.Parallel()
		var sawSessionID string
		refresh := func(ctx context.Context, sessionID, ipHash string) (domain.AuthSession, error) {
			sawSessionID = sessionID
			now := time.Date(2026, 1, 1, 13, 0, 0, 0, time.UTC)
			return domain.AuthSession{
				ID:             sessionID,
				IdentityType:   domain.AuthSessionIdentityAnonymous,
				CreatedAt:      now.Add(-30 * time.Minute),
				ExpiresAt:      now.Add(1 * time.Hour),
				RefreshUntil:   now.Add(2 * time.Hour),
				LifetimeEndsAt: now.Add(23 * time.Hour),
			}, nil
		}
		handler := newAuthRefreshHandler(t, refresh, time.Now)
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/refresh", http.NoBody)
		r.Header.Set("Authorization", "Bearer my-session-id")
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusOK, w.Code)
		require.Equal(t, "my-session-id", sawSessionID)
	})

	t.Run("sets Cache-Control: no-store on the refreshed session response", func(t *testing.T) {
		t.Parallel()
		refresh := func(ctx context.Context, sessionID, ipHash string) (domain.AuthSession, error) {
			now := time.Date(2026, 1, 1, 13, 0, 0, 0, time.UTC)
			return domain.AuthSession{
				ID:             sessionID,
				IdentityType:   domain.AuthSessionIdentityAnonymous,
				CreatedAt:      now.Add(-30 * time.Minute),
				ExpiresAt:      now.Add(1 * time.Hour),
				RefreshUntil:   now.Add(2 * time.Hour),
				LifetimeEndsAt: now.Add(23 * time.Hour),
			}, nil
		}
		handler := newAuthRefreshHandler(t, refresh, time.Now)
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/refresh", http.NoBody)
		r.Header.Set("Authorization", "Bearer my-session-id")
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusOK, w.Code)
		require.Equal(t, "no-store", w.Header().Get("Cache-Control"),
			"refresh responses carry a bearer token; no intermediary should cache them")
	})

	t.Run("returns cors headers", func(t *testing.T) {
		t.Parallel()
		refresh := func(ctx context.Context, sessionID, ipHash string) (domain.AuthSession, error) {
			now := time.Date(2026, 1, 1, 13, 0, 0, 0, time.UTC)
			return domain.AuthSession{
				ID:             sessionID,
				IdentityType:   domain.AuthSessionIdentityAnonymous,
				CreatedAt:      now.Add(-30 * time.Minute),
				ExpiresAt:      now.Add(1 * time.Hour),
				RefreshUntil:   now.Add(2 * time.Hour),
				LifetimeEndsAt: now.Add(23 * time.Hour),
			}, nil
		}
		handler := newAuthRefreshHandler(t, refresh, time.Now)

		origin := "https://subdomain.example.com"
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/refresh", http.NoBody)
		r.Header.Set("Authorization", "Bearer my-session-id")
		r.Header.Set("Origin", origin)
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()

		handler(w, r)

		require.Equal(t, http.StatusOK, w.Code)
		require.Equal(t, origin, w.Header().Get("Access-Control-Allow-Origin"))
	})

	t.Run("rate limits per ip", func(t *testing.T) {
		t.Parallel()
		refreshes := 0
		refresh := func(ctx context.Context, sessionID, ipHash string) (domain.AuthSession, error) {
			refreshes++
			now := time.Date(2026, 1, 1, 13, 0, 0, 0, time.UTC)
			return domain.AuthSession{
				ID:             sessionID,
				IdentityType:   domain.AuthSessionIdentityAnonymous,
				CreatedAt:      now.Add(-30 * time.Minute),
				ExpiresAt:      now.Add(1 * time.Hour),
				RefreshUntil:   now.Add(2 * time.Hour),
				LifetimeEndsAt: now.Add(23 * time.Hour),
			}, nil
		}
		handler := newAuthRefreshHandler(t, refresh, time.Now)

		doRefresh := func(ip string) int {
			r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/refresh", http.NoBody)
			r.Header.Set("Authorization", "Bearer my-session-id")
			withRequestIP(r, ip)
			w := httptest.NewRecorder()
			handler(w, r)
			return w.Code
		}

		// The burst is 60, after which the same IP is refused without ever
		// reaching the (write-heavy) refresh use case. The bucket refills at
		// 1/s off the wall clock, so a slow run could hand a token back
		// mid-loop — keep asking rather than pinning the exact boundary.
		accepted := 0
		var lastCode int
		for range 65 {
			lastCode = doRefresh("1.2.3.4")
			if lastCode != http.StatusOK {
				break
			}
			accepted++
		}

		require.Equal(t, http.StatusTooManyRequests, lastCode)
		require.GreaterOrEqual(t, accepted, 60, "the full burst should be allowed through")
		require.Equal(t, accepted, refreshes, "the throttled request must not reach the refresh use case")

		require.Equal(t, http.StatusOK, doRefresh("5.6.7.8"), "an unrelated IP is unaffected")
	})

	t.Run("401 when bearer is missing", func(t *testing.T) {
		t.Parallel()
		refresh := func(ctx context.Context, sessionID, ipHash string) (domain.AuthSession, error) {
			t.Fatal("should not be called without bearer")
			return domain.AuthSession{}, nil
		}
		handler := newAuthRefreshHandler(t, refresh, time.Now)
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/refresh", http.NoBody)
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusUnauthorized, w.Code)
	})

	t.Run("429 on "+domain.ErrAuthSessionRefreshTooSoon.Error(), func(t *testing.T) {
		t.Parallel()
		// Deliberately not a 401: the session is still good, so the client
		// must keep using it rather than re-authenticating.
		refresh := func(ctx context.Context, sessionID, ipHash string) (domain.AuthSession, error) {
			return domain.AuthSession{}, domain.ErrAuthSessionRefreshTooSoon
		}
		handler := newAuthRefreshHandler(t, refresh, time.Now)
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/refresh", http.NoBody)
		r.Header.Set("Authorization", "Bearer some-id")
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusTooManyRequests, w.Code)
	})

	for _, sentinel := range []error{
		domain.ErrAuthSessionNotFound,
		domain.ErrAuthSessionRevoked,
		domain.ErrAuthSessionRefreshExpired,
	} {

		t.Run("401 on "+sentinel.Error(), func(t *testing.T) {
			t.Parallel()
			refresh := func(ctx context.Context, sessionID, ipHash string) (domain.AuthSession, error) {
				return domain.AuthSession{}, sentinel
			}
			handler := newAuthRefreshHandler(t, refresh, time.Now)
			r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/refresh", http.NoBody)
			r.Header.Set("Authorization", "Bearer some-id")
			withRequestIP(r, "1.2.3.4")
			w := httptest.NewRecorder()
			handler(w, r)
			require.Equal(t, http.StatusUnauthorized, w.Code)
		})
	}
}
