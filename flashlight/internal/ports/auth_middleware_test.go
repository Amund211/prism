package ports_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ports"
)

func TestBearerAuthMiddleware(t *testing.T) {
	t.Parallel()

	t.Run("passes through with no Authorization header", func(t *testing.T) {
		t.Parallel()
		called := false
		validate := func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
			t.Fatal("validate should not be called when no Authorization header")
			return domain.AuthSession{}, nil
		}
		mw := ports.NewBearerAuthMiddleware(validate)
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
			}, nil
		}
		mw := ports.NewBearerAuthMiddleware(validate)
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
	})

	t.Run("401 on malformed Authorization header", func(t *testing.T) {
		t.Parallel()
		validate := func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
			t.Fatal("validate should not be called for malformed header")
			return domain.AuthSession{}, nil
		}
		mw := ports.NewBearerAuthMiddleware(validate)
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
			mw := ports.NewBearerAuthMiddleware(validate)
			next := func(w http.ResponseWriter, r *http.Request) {
				t.Fatal("next should not be invoked on invalid session")
			}
			handler := mw(next)
			r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
			r.Header.Set("Authorization", "Bearer dead-token")
			w := httptest.NewRecorder()
			handler(w, r)
			require.Equal(t, http.StatusUnauthorized, w.Code)
		})
	}
}
