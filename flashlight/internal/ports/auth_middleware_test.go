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

var authMiddlewareNow = time.Date(2026, 8, 8, 12, 0, 0, 0, time.UTC)

func TestBearerAuthMiddleware(t *testing.T) {
	t.Parallel()

	t.Run("passes through with no Authorization header", func(t *testing.T) {
		t.Parallel()
		called := false
		validate := func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
			t.Fatal("validate should not be called when no Authorization header")
			return domain.AuthSession{}, nil
		}
		mw := ports.NewBearerAuthMiddleware(validate, func() time.Time { return authMiddlewareNow })
		next := func(w http.ResponseWriter, r *http.Request) {
			called = true
			_, ok := ports.AuthFromContext(r.Context())
			require.False(t, ok, "no auth context should be attached without bearer")
			w.WriteHeader(http.StatusOK)
		}
		handler := mw(next)
		r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
		w := httptest.NewRecorder()
		handler(w, r)
		require.True(t, called)
		require.Equal(t, http.StatusOK, w.Code)
	})

	t.Run("attaches auth context for valid bearer", func(t *testing.T) {
		t.Parallel()
		validate := func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
			return domain.AuthSession{
				ID:           sessionID,
				IdentityType: domain.AuthSessionIdentityAnonymous,
				IdentityKey:  "user-xyz",
				ExpiresAt:    authMiddlewareNow.Add(time.Hour),
			}, nil
		}
		mw := ports.NewBearerAuthMiddleware(validate, func() time.Time { return authMiddlewareNow })
		var seen ports.AuthContext
		next := func(w http.ResponseWriter, r *http.Request) {
			ctx, ok := ports.AuthFromContext(r.Context())
			require.True(t, ok)
			seen = ctx
			w.WriteHeader(http.StatusOK)
		}
		handler := mw(next)
		r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
		r.Header.Set("Authorization", "Bearer good-token")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusOK, w.Code)
		require.Equal(t, "good-token", seen.SessionID)
		require.Equal(t, domain.AuthSessionIdentityAnonymous, seen.IdentityType)
		require.Equal(t, "user-xyz", seen.IdentityKey)
		require.Empty(t, w.Result().Header.Get(ports.AuthRefreshHeader), "a fresh session needs no refresh hint")
	})

	// Reading the header off w.Result() rather than w.Header() is the point:
	// the recorder snapshots headers at WriteHeader, so these only pass if the
	// middleware set it before the handler ran.
	for _, tc := range []struct {
		name      string
		expiresAt time.Time
	}{
		{"inside the refresh window", authMiddlewareNow.Add(4 * time.Minute)},
		{"exactly at the refresh point", authMiddlewareNow.Add(5 * time.Minute)},
		{"already past expiry", authMiddlewareNow.Add(-time.Minute)},
	} {
		t.Run("sets the refresh hint when "+tc.name, func(t *testing.T) {
			t.Parallel()
			validate := func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
				return domain.AuthSession{
					ID:           sessionID,
					IdentityType: domain.AuthSessionIdentityAnonymous,
					IdentityKey:  "user-xyz",
					ExpiresAt:    tc.expiresAt,
				}, nil
			}
			mw := ports.NewBearerAuthMiddleware(validate, func() time.Time { return authMiddlewareNow })
			handler := mw(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(http.StatusOK)
			})
			r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
			r.Header.Set("Authorization", "Bearer good-token")
			w := httptest.NewRecorder()
			handler(w, r)
			require.Equal(t, http.StatusOK, w.Code)
			require.Equal(t, "1", w.Result().Header.Get(ports.AuthRefreshHeader))
		})
	}

	// /v1/tags 401ing for a bad Urchin API key behind a valid bearer: the hint
	// must be set before next(), because the handler writing its own response
	// freezes the header map.
	t.Run("keeps the refresh hint on a handler's own 401", func(t *testing.T) {
		t.Parallel()
		validate := func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
			return domain.AuthSession{
				ID:           sessionID,
				IdentityType: domain.AuthSessionIdentityAnonymous,
				IdentityKey:  "user-xyz",
				ExpiresAt:    authMiddlewareNow.Add(4 * time.Minute),
			}, nil
		}
		mw := ports.NewBearerAuthMiddleware(validate, func() time.Time { return authMiddlewareNow })
		handler := mw(func(w http.ResponseWriter, r *http.Request) {
			http.Error(w, "Invalid urchin API key. Fix it or remove the key.", http.StatusUnauthorized)
		})
		r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/tags/uuid", http.NoBody)
		r.Header.Set("Authorization", "Bearer good-token")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusUnauthorized, w.Code)
		require.Equal(t, "1", w.Result().Header.Get(ports.AuthRefreshHeader))
	})

	t.Run("no refresh hint without an Authorization header", func(t *testing.T) {
		t.Parallel()
		validate := func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
			t.Fatal("validate should not be called when no Authorization header")
			return domain.AuthSession{}, nil
		}
		mw := ports.NewBearerAuthMiddleware(validate, func() time.Time { return authMiddlewareNow })
		handler := mw(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
		})
		r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
		w := httptest.NewRecorder()
		handler(w, r)
		require.Empty(t, w.Result().Header.Get(ports.AuthRefreshHeader))
	})

	t.Run("401 on malformed Authorization header", func(t *testing.T) {
		t.Parallel()
		validate := func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
			t.Fatal("validate should not be called for malformed header")
			return domain.AuthSession{}, nil
		}
		mw := ports.NewBearerAuthMiddleware(validate, func() time.Time { return authMiddlewareNow })
		next := func(w http.ResponseWriter, r *http.Request) {
			t.Fatal("next should not be invoked on malformed header")
		}
		handler := mw(next)
		r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
		r.Header.Set("Authorization", "Basic creds")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusUnauthorized, w.Code)
	})

	for _, sentinel := range []error{
		domain.ErrAuthSessionNotFound,
		domain.ErrAuthSessionRevoked,
		domain.ErrAuthSessionExpired,
	} {

		t.Run("401 on "+sentinel.Error(), func(t *testing.T) {
			t.Parallel()
			validate := func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
				return domain.AuthSession{}, sentinel
			}
			mw := ports.NewBearerAuthMiddleware(validate, func() time.Time { return authMiddlewareNow })
			next := func(w http.ResponseWriter, r *http.Request) {
				t.Fatal("next should not be invoked on invalid session")
			}
			handler := mw(next)
			r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
			r.Header.Set("Authorization", "Bearer dead-token")
			w := httptest.NewRecorder()
			handler(w, r)
			require.Equal(t, http.StatusUnauthorized, w.Code)
			require.Empty(t, w.Result().Header.Get(ports.AuthRefreshHeader), "nothing to refresh when validation failed")
		})
	}
}
