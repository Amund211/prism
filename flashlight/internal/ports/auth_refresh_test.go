package ports_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ports"
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
		handler := ports.MakeAuthRefreshHandler(refresh, time.Now, authTestLogger, noopAuthMiddleware, ports.BlocklistConfig{})
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
		handler := ports.MakeAuthRefreshHandler(refresh, time.Now, authTestLogger, noopAuthMiddleware, ports.BlocklistConfig{})
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/refresh", http.NoBody)
		r.Header.Set("Authorization", "Bearer my-session-id")
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusOK, w.Code)
		require.Equal(t, "no-store", w.Header().Get("Cache-Control"),
			"refresh responses carry a bearer token; no intermediary should cache them")
	})

	t.Run("401 when bearer is missing", func(t *testing.T) {
		t.Parallel()
		refresh := func(ctx context.Context, sessionID, ipHash string) (domain.AuthSession, error) {
			t.Fatal("should not be called without bearer")
			return domain.AuthSession{}, nil
		}
		handler := ports.MakeAuthRefreshHandler(refresh, time.Now, authTestLogger, noopAuthMiddleware, ports.BlocklistConfig{})
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/refresh", http.NoBody)
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusUnauthorized, w.Code)
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
			handler := ports.MakeAuthRefreshHandler(refresh, time.Now, authTestLogger, noopAuthMiddleware, ports.BlocklistConfig{})
			r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/refresh", http.NoBody)
			r.Header.Set("Authorization", "Bearer some-id")
			withRequestIP(r, "1.2.3.4")
			w := httptest.NewRecorder()
			handler(w, r)
			require.Equal(t, http.StatusUnauthorized, w.Code)
		})
	}
}
