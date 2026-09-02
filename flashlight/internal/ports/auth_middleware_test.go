package ports_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
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
		mw := ports.NewBearerAuthMiddleware(validate, func() time.Time { return authMiddlewareNow }, ports.BlocklistConfig{})
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
		require.Equal(t, ports.AuthSessionAbsent, w.Result().Header.Get(ports.AuthSessionHeader), "a stripped Authorization header is invisible without this")
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
		mw := ports.NewBearerAuthMiddleware(validate, func() time.Time { return authMiddlewareNow }, ports.BlocklistConfig{})
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
		require.Equal(t, ports.AuthSessionValid, w.Result().Header.Get(ports.AuthSessionHeader))
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
			mw := ports.NewBearerAuthMiddleware(validate, func() time.Time { return authMiddlewareNow }, ports.BlocklistConfig{})
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
		mw := ports.NewBearerAuthMiddleware(validate, func() time.Time { return authMiddlewareNow }, ports.BlocklistConfig{})
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

	// The whole reason the header exists: this 401 is the handler's, not the
	// middleware's, and only the header says so.
	t.Run("marks a handler's own 401 as validated", func(t *testing.T) {
		t.Parallel()
		validate := func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
			return domain.AuthSession{
				ID:           sessionID,
				IdentityType: domain.AuthSessionIdentityAnonymous,
				IdentityKey:  "user-xyz",
				ExpiresAt:    authMiddlewareNow.Add(time.Hour),
			}, nil
		}
		mw := ports.NewBearerAuthMiddleware(validate, func() time.Time { return authMiddlewareNow }, ports.BlocklistConfig{})
		handler := mw(func(w http.ResponseWriter, r *http.Request) {
			http.Error(w, "Invalid urchin API key. Fix it or remove the key.", http.StatusUnauthorized)
		})
		r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/tags/uuid", http.NoBody)
		r.Header.Set("Authorization", "Bearer good-token")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusUnauthorized, w.Code)
		require.Equal(t, ports.AuthSessionValid, w.Result().Header.Get(ports.AuthSessionHeader))
	})

	t.Run("no refresh hint without an Authorization header", func(t *testing.T) {
		t.Parallel()
		validate := func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
			t.Fatal("validate should not be called when no Authorization header")
			return domain.AuthSession{}, nil
		}
		mw := ports.NewBearerAuthMiddleware(validate, func() time.Time { return authMiddlewareNow }, ports.BlocklistConfig{})
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
		mw := ports.NewBearerAuthMiddleware(validate, func() time.Time { return authMiddlewareNow }, ports.BlocklistConfig{})
		next := func(w http.ResponseWriter, r *http.Request) {
			t.Fatal("next should not be invoked on malformed header")
		}
		handler := mw(next)
		r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
		r.Header.Set("Authorization", "Basic creds")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusUnauthorized, w.Code)
		require.Empty(t, w.Result().Header.Get(ports.AuthSessionHeader), "a client bug is not a session state")
	})

	t.Run("500 and no header when validate fails unexpectedly", func(t *testing.T) {
		t.Parallel()
		validate := func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
			return domain.AuthSession{}, errors.New("the database is on fire")
		}
		mw := ports.NewBearerAuthMiddleware(validate, func() time.Time { return authMiddlewareNow }, ports.BlocklistConfig{})
		next := func(w http.ResponseWriter, r *http.Request) {
			t.Fatal("next should not be invoked when validation errors")
		}
		handler := mw(next)
		r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
		r.Header.Set("Authorization", "Bearer good-token")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusInternalServerError, w.Code)
		require.Empty(t, w.Result().Header.Get(ports.AuthSessionHeader), "the session state is unknown, and unknown is spelled no header")
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
			mw := ports.NewBearerAuthMiddleware(validate, func() time.Time { return authMiddlewareNow }, ports.BlocklistConfig{})
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
			require.Empty(t, w.Result().Header.Get(ports.AuthSessionHeader), "never claim we validated a session we rejected")
		})
	}
}

// The blocklist in front matches the X-User-Id header, which a blocked caller
// just omits. These pin the check on the verified identity.
func TestBearerAuthMiddlewareBlocklist(t *testing.T) {
	t.Parallel()

	validateAs := func(identityKey string) func(context.Context, string) (domain.AuthSession, error) {
		return func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
			return domain.AuthSession{
				ID:           sessionID,
				IdentityType: domain.AuthSessionIdentityAnonymous,
				IdentityKey:  identityKey,
				ExpiresAt:    authMiddlewareNow.Add(time.Hour),
			}, nil
		}
	}

	blocklist := ports.BlocklistConfig{UserIDs: []string{"blocked-user"}}

	t.Run("refuses a blocked identity with no X-User-Id to block on", func(t *testing.T) {
		t.Parallel()
		mw := ports.NewBearerAuthMiddleware(validateAs("blocked-user"), func() time.Time { return authMiddlewareNow }, blocklist)
		handler := mw(func(w http.ResponseWriter, r *http.Request) {
			t.Fatal("next should not be invoked for a blocked identity")
		})
		r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
		r.Header.Set("Authorization", "Bearer good-token")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusBadRequest, w.Code, "same status and body as the header-keyed blocklist")
	})

	// The front blocklist has nothing to match; only the verified identity is left.
	t.Run("refuses a blocked identity behind an unblocked X-User-Id", func(t *testing.T) {
		t.Parallel()
		mw := ports.NewBearerAuthMiddleware(validateAs("blocked-user"), func() time.Time { return authMiddlewareNow }, blocklist)
		handler := mw(func(w http.ResponseWriter, r *http.Request) {
			t.Fatal("next should not be invoked for a blocked identity")
		})
		r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
		r.Header.Set("Authorization", "Bearer good-token")
		r.Header.Set("X-User-Id", "some-other-user")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusBadRequest, w.Code)
	})

	// The session is fine; it is the identity we refuse.
	t.Run("still reports the session as valid when refusing", func(t *testing.T) {
		t.Parallel()
		mw := ports.NewBearerAuthMiddleware(validateAs("blocked-user"), func() time.Time { return authMiddlewareNow }, blocklist)
		handler := mw(func(w http.ResponseWriter, r *http.Request) {
			t.Fatal("next should not be invoked for a blocked identity")
		})
		r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
		r.Header.Set("Authorization", "Bearer good-token")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, ports.AuthSessionValid, w.Result().Header.Get(ports.AuthSessionHeader))
	})

	// Login takes 100 chars, the header is truncated to 50, and one entry must
	// cover both.
	t.Run("normalizes the identity the way the header path is normalized", func(t *testing.T) {
		t.Parallel()
		longKey := strings.Repeat("a", 60)
		mw := ports.NewBearerAuthMiddleware(
			validateAs(longKey),
			func() time.Time { return authMiddlewareNow },
			ports.BlocklistConfig{UserIDs: []string{ports.NewUserID(longKey).String()}},
		)
		handler := mw(func(w http.ResponseWriter, r *http.Request) {
			t.Fatal("next should not be invoked for a blocked identity")
		})
		r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
		r.Header.Set("Authorization", "Bearer good-token")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusBadRequest, w.Code, "the 50-char entry that blocks the header path must block this one too")
	})

	t.Run("lets an unblocked identity through", func(t *testing.T) {
		t.Parallel()
		called := false
		mw := ports.NewBearerAuthMiddleware(validateAs("fine-user"), func() time.Time { return authMiddlewareNow }, blocklist)
		handler := mw(func(w http.ResponseWriter, r *http.Request) {
			called = true
			w.WriteHeader(http.StatusOK)
		})
		r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
		r.Header.Set("Authorization", "Bearer good-token")
		w := httptest.NewRecorder()
		handler(w, r)
		require.True(t, called)
		require.Equal(t, http.StatusOK, w.Code)
	})

	// No bearer, no verified identity — that path belongs to the check in front.
	t.Run("does not consult the blocklist without a bearer", func(t *testing.T) {
		t.Parallel()
		called := false
		validate := func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
			t.Fatal("validate should not be called when no Authorization header")
			return domain.AuthSession{}, nil
		}
		mw := ports.NewBearerAuthMiddleware(validate, func() time.Time { return authMiddlewareNow }, blocklist)
		handler := mw(func(w http.ResponseWriter, r *http.Request) {
			called = true
			w.WriteHeader(http.StatusOK)
		})
		r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
		r.Header.Set("X-User-Id", "blocked-user")
		w := httptest.NewRecorder()
		handler(w, r)
		require.True(t, called)
		require.Equal(t, http.StatusOK, w.Code)
	})
}
