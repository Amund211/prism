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

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ports"
	"github.com/Amund211/flashlight/internal/proofofwork"
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
		body := strings.NewReader(anonymousLoginBody("user-abc"))
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
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(anonymousLoginBody("user-abc")))
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
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(anonymousLoginBody("user-late")))
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
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(anonymousLoginBody("user-abc")))
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
				r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(anonymousLoginBody("user-abc")))
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
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(anonymousLoginBody("user-abc")))
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
			body := anonymousLoginBody(userID)
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
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(anonymousLoginBody("")))
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
		body := anonymousLoginBody(strings.Repeat("x", 101))
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
		body := anonymousLoginBody(longID)
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

// TestAnonymousLoginProofOfWork covers the handshake the endpoint now
// requires. The mechanism ships mandatory at difficulty 0, so "no proof"
// has to be a rejection even while the work is free — that is the whole
// reason for shipping it before any client does.
func TestAnonymousLoginProofOfWork(t *testing.T) {
	t.Parallel()

	failIfCalled := func(t *testing.T, reason string) app.AnonymousLogin {
		return func(ctx context.Context, userID, ipHash string) (domain.AuthSession, error) {
			t.Fatalf("login should not be called %s", reason)
			return domain.AuthSession{}, nil
		}
	}

	issuedSession := func(now time.Time) app.AnonymousLogin {
		return func(ctx context.Context, userID, ipHash string) (domain.AuthSession, error) {
			return domain.AuthSession{
				ID:             "sid-pow",
				IdentityType:   domain.AuthSessionIdentityAnonymous,
				IdentityKey:    userID,
				CreatedAt:      now,
				ExpiresAt:      now.Add(1 * time.Hour),
				RefreshUntil:   now.Add(2 * time.Hour),
				LifetimeEndsAt: now.Add(24 * time.Hour),
			}, nil
		}
	}

	postLogin := func(t *testing.T, handler http.HandlerFunc, ip string, body string) *httptest.ResponseRecorder {
		t.Helper()
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/login", strings.NewReader(body))
		withJSONContentType(r)
		withRequestIP(r, ip)
		w := httptest.NewRecorder()
		handler(w, r)
		return w
	}

	t.Run("400 on missing or oversized proof fields", func(t *testing.T) {
		t.Parallel()
		for name, body := range map[string]string{
			"no proof at all":      `{"userId":"user-abc"}`,
			"no challenge":         `{"userId":"user-abc","solution":"1"}`,
			"empty challenge":      `{"userId":"user-abc","challenge":"","solution":"1"}`,
			"no solution":          `{"userId":"user-abc","challenge":"blob"}`,
			"empty solution":       `{"userId":"user-abc","challenge":"blob","solution":""}`,
			"huge challenge":       fmt.Sprintf(`{"userId":"user-abc","challenge":%q,"solution":"1"}`, strings.Repeat("x", 513)),
			"huge solution":        fmt.Sprintf(`{"userId":"user-abc","challenge":"blob","solution":%q}`, strings.Repeat("x", 129)),
			"whole body oversized": fmt.Sprintf(`{"userId":"user-abc","challenge":%q,"solution":"1"}`, strings.Repeat("x", 4096)),
		} {
			t.Run(name, func(t *testing.T) {
				t.Parallel()
				verify := func(challenge, solution, ipHash string) error {
					t.Fatal("verification should not be reached for a malformed body")
					return nil
				}
				handler := newAnonymousLoginHandlerWithProof(t, failIfCalled(t, "without a well-formed proof"), verify, time.Now)
				require.Equal(t, http.StatusBadRequest, postLogin(t, handler, "1.2.3.4", body).Code)
			})
		}
	})

	// The empty string is a valid proof at difficulty 0, so nothing about
	// the hashing forces a client to implement the loop. Rejecting it does
	// — and finding out the client shipped a stub the day we raise the
	// difficulty is exactly the retrofit this design avoids.
	t.Run("400 on an empty solution even though difficulty is 0", func(t *testing.T) {
		t.Parallel()
		issue, verify := newProofOfWorkScheme(t, 0)
		challenge, err := issue(ports.IP("1.2.3.4").Hash(), "prism")
		require.NoError(t, err)

		handler := newAnonymousLoginHandlerWithProof(t, failIfCalled(t, "with an empty solution"), verify, time.Now)
		body := fmt.Sprintf(`{"userId":"user-abc","challenge":%q,"solution":""}`, challenge.Value)
		require.Equal(t, http.StatusBadRequest, postLogin(t, handler, "1.2.3.4", body).Code)
	})

	t.Run("403 on a rejected proof, ahead of any database work", func(t *testing.T) {
		t.Parallel()
		for name, cause := range map[string]error{
			"malformed":             proofofwork.ErrMalformedChallenge,
			"bad signature":         proofofwork.ErrBadSignature,
			"expired":               proofofwork.ErrChallengeExpired,
			"ip mismatch":           proofofwork.ErrIPMismatch,
			"replayed":              proofofwork.ErrNonceReplayed,
			"insufficient work":     proofofwork.ErrInsufficientWork,
			"unsupported algorithm": proofofwork.ErrUnsupportedAlgorithm,
		} {
			t.Run(name, func(t *testing.T) {
				t.Parallel()
				verify := func(challenge, solution, ipHash string) error { return cause }
				handler := newAnonymousLoginHandlerWithProof(t, failIfCalled(t, "for a rejected proof"), verify, time.Now)
				require.Equal(t, http.StatusForbidden, postLogin(t, handler, "1.2.3.4", anonymousLoginBody("user-abc")).Code)
			})
		}
	})

	t.Run("verification gets the body's proof and the request's ip hash", func(t *testing.T) {
		t.Parallel()
		var sawChallenge, sawSolution, sawIPHash string
		verify := func(challenge, solution, ipHash string) error {
			sawChallenge, sawSolution, sawIPHash = challenge, solution, ipHash
			return nil
		}
		now := time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)
		handler := newAnonymousLoginHandlerWithProof(t, issuedSession(now), verify, func() time.Time { return now })

		body := `{"userId":"user-abc","challenge":"some-blob","solution":"42"}`
		require.Equal(t, http.StatusOK, postLogin(t, handler, "1.2.3.4", body).Code)
		require.Equal(t, "some-blob", sawChallenge)
		require.Equal(t, "42", sawSolution)
		require.Equal(t, ports.IP("1.2.3.4").Hash(), sawIPHash,
			"the proof is bound to the caller's ip, so it must be checked against the ip we'd bill the login to")
	})

	// End to end over both endpoints, with real hashing: what a client
	// actually has to do, and what it buys an attacker who tries to reuse
	// the result.
	t.Run("a challenge from the challenge endpoint logs in exactly once", func(t *testing.T) {
		t.Parallel()
		const difficulty = 8
		now := time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)
		issue, verify := newProofOfWorkScheme(t, difficulty)
		challengeHandler := newAnonymousChallengeHandler(t, issue)
		loginHandler := newAnonymousLoginHandlerWithProof(t, issuedSession(now), verify, func() time.Time { return now })

		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/challenge", nil)
		withJSONContentType(r)
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()
		challengeHandler(w, r)
		require.Equal(t, http.StatusOK, w.Code)

		var challenge struct {
			Challenge  string `json:"challenge"`
			Algorithm  string `json:"algorithm"`
			Difficulty int    `json:"difficulty"`
		}
		require.NoError(t, json.NewDecoder(w.Body).Decode(&challenge))
		require.Equal(t, difficulty, challenge.Difficulty)

		body := fmt.Sprintf(
			`{"userId":"user-abc","challenge":%q,"solution":%q}`,
			challenge.Challenge,
			solveChallenge(t, challenge.Challenge, challenge.Difficulty),
		)
		require.Equal(t, http.StatusOK, postLogin(t, loginHandler, "1.2.3.4", body).Code)

		require.Equal(t, http.StatusForbidden, postLogin(t, loginHandler, "1.2.3.4", body).Code,
			"replaying a solved challenge would price identity per minute instead of per identity")
	})

	t.Run("a challenge solved for one ip does not work from another", func(t *testing.T) {
		t.Parallel()
		now := time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)
		issue, verify := newProofOfWorkScheme(t, 0)
		loginHandler := newAnonymousLoginHandlerWithProof(t, issuedSession(now), verify, func() time.Time { return now })

		challenge, err := issue(ports.IP("1.2.3.4").Hash(), "prism")
		require.NoError(t, err)
		body := fmt.Sprintf(
			`{"userId":"user-abc","challenge":%q,"solution":%q}`,
			challenge.Value,
			solveChallenge(t, challenge.Value, challenge.Difficulty),
		)

		require.Equal(t, http.StatusForbidden, postLogin(t, loginHandler, "5.6.7.8", body).Code,
			"one rented CPU box must not be able to solve challenges for a pool of proxy exits")
		require.Equal(t, http.StatusOK, postLogin(t, loginHandler, "1.2.3.4", body).Code,
			"and the misdirected attempt must not have burned the challenge")
	})
}
