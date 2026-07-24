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

		handler := newAnonymousLoginHandler(t, login, fixedNow(now))
		body := strings.NewReader(`{"userId":"user-abc"}`)
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", body)
		withJSONContentType(r)
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
		handler := newAnonymousLoginHandler(t, login, fixedNow(now))
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(`{"userId":"user-abc"}`))
		withJSONContentType(r)
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
		handler := newAnonymousLoginHandler(t, login, fixedNow(now))
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(`{"userId":"user-late"}`))
		withJSONContentType(r)
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

	t.Run("returns cors headers", func(t *testing.T) {
		t.Parallel()
		now := time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)
		login := func(ctx context.Context, userID, ipHash string) (domain.AuthSession, error) {
			return domain.AuthSession{
				ID:             "sid-cors",
				IdentityType:   domain.AuthSessionIdentityAnonymous,
				IdentityKey:    userID,
				CreatedAt:      now,
				ExpiresAt:      now.Add(1 * time.Hour),
				RefreshUntil:   now.Add(2 * time.Hour),
				LifetimeEndsAt: now.Add(24 * time.Hour),
			}, nil
		}
		handler := newAnonymousLoginHandler(t, login, fixedNow(now))

		origin := "https://subdomain.example.com"
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(`{"userId":"user-abc"}`))
		r.Header.Set("Origin", origin)
		withJSONContentType(r)
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()

		handler(w, r)

		require.Equal(t, http.StatusOK, w.Code)
		require.Equal(t, origin, w.Header().Get("Access-Control-Allow-Origin"))
	})

	// A JSON content type is not CORS-safelisted, so requiring it is what
	// forces a preflight. Without the gate a page on any origin could make
	// a visitor's browser POST text/plain with a JSON body — no preflight,
	// so the request lands — and mint sessions from the visitor's IP until
	// their real ones are evicted by the ip cap.
	t.Run("415 on a content type that would skip the preflight", func(t *testing.T) {
		t.Parallel()
		for _, contentType := range []string{
			"",
			"text/plain",
			"text/plain;charset=UTF-8",
			"application/x-www-form-urlencoded",
			"multipart/form-data; boundary=x",
		} {
			t.Run(fmt.Sprintf("%q", contentType), func(t *testing.T) {
				t.Parallel()
				login := func(ctx context.Context, userID, ipHash string) (domain.AuthSession, error) {
					t.Fatal("login should not be called for a non-JSON content type")
					return domain.AuthSession{}, nil
				}
				handler := newAnonymousLoginHandler(t, login, time.Now)
				r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(`{"userId":"user-abc"}`))
				if contentType != "" {
					r.Header.Set("Content-Type", contentType)
				}
				withRequestIP(r, "1.2.3.4")
				w := httptest.NewRecorder()

				handler(w, r)

				require.Equal(t, http.StatusUnsupportedMediaType, w.Code)
			})
		}
	})

	t.Run("accepts a JSON content type with parameters", func(t *testing.T) {
		t.Parallel()
		now := time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)
		login := func(ctx context.Context, userID, ipHash string) (domain.AuthSession, error) {
			return domain.AuthSession{
				ID:             "sid-charset",
				IdentityType:   domain.AuthSessionIdentityAnonymous,
				IdentityKey:    userID,
				CreatedAt:      now,
				ExpiresAt:      now.Add(1 * time.Hour),
				RefreshUntil:   now.Add(2 * time.Hour),
				LifetimeEndsAt: now.Add(24 * time.Hour),
			}, nil
		}
		handler := newAnonymousLoginHandler(t, login, fixedNow(now))
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(`{"userId":"user-abc"}`))
		// What fetch() sends when you hand it a JSON string body.
		r.Header.Set("Content-Type", "application/json; charset=utf-8")
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()

		handler(w, r)

		require.Equal(t, http.StatusOK, w.Code)
	})

	t.Run("rate limits per ip", func(t *testing.T) {
		t.Parallel()
		now := time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)
		logins := 0
		login := func(ctx context.Context, userID, ipHash string) (domain.AuthSession, error) {
			logins++
			return domain.AuthSession{
				ID:             "sid-limit",
				IdentityType:   domain.AuthSessionIdentityAnonymous,
				IdentityKey:    userID,
				CreatedAt:      now,
				ExpiresAt:      now.Add(1 * time.Hour),
				RefreshUntil:   now.Add(2 * time.Hour),
				LifetimeEndsAt: now.Add(24 * time.Hour),
			}, nil
		}
		handler := newAnonymousLoginHandler(t, login, fixedNow(now))

		doLogin := func(ip string, userID string) int {
			body := fmt.Sprintf(`{"userId":%q}`, userID)
			r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(body))
			withJSONContentType(r)
			withRequestIP(r, ip)
			w := httptest.NewRecorder()
			handler(w, r)
			return w.Code
		}

		// The burst is 60, after which the same IP is refused without ever
		// reaching the (write-heavy) login use case. The bucket refills at 1/s
		// off the wall clock, so a slow run could hand a token back mid-loop —
		// keep asking rather than pinning the exact boundary request.
		accepted := 0
		var lastCode int
		for range 65 {
			lastCode = doLogin("1.2.3.4", "user-abc")
			if lastCode != http.StatusOK {
				break
			}
			accepted++
		}

		require.Equal(t, http.StatusTooManyRequests, lastCode)
		require.GreaterOrEqual(t, accepted, 60, "the full burst should be allowed through")
		require.Equal(t, accepted, logins, "the throttled request must not reach the login use case")

		// Keyed on the IP, not the body — a fresh userId from the same IP is
		// still refused, and an unrelated IP is unaffected.
		require.Equal(t, http.StatusTooManyRequests, doLogin("1.2.3.4", "some-other-user"))
		require.Equal(t, http.StatusOK, doLogin("5.6.7.8", "user-abc"))
	})

	t.Run("400 on invalid userId", func(t *testing.T) {
		t.Parallel()
		login := func(ctx context.Context, userID, ipHash string) (domain.AuthSession, error) {
			t.Fatal("login should not be called when userId is invalid")
			return domain.AuthSession{}, nil
		}
		handler := newAnonymousLoginHandler(t, login, time.Now)
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(`{"userId":""}`))
		withJSONContentType(r)
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
		handler := newAnonymousLoginHandler(t, login, time.Now)
		// 101 chars — past the 100-char hard cap.
		body := fmt.Sprintf(`{"userId":%q}`, strings.Repeat("x", 101))
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(body))
		withJSONContentType(r)
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
		handler := newAnonymousLoginHandler(t, login, time.Now)
		body := fmt.Sprintf(`{"userId":%q}`, longID)
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(body))
		withJSONContentType(r)
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
		handler := newAnonymousLoginHandler(t, login, time.Now)
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(`not-json`))
		withJSONContentType(r)
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()
		handler(w, r)
		require.Equal(t, http.StatusBadRequest, w.Code)
	})
}
