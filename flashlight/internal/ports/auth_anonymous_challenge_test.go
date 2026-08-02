package ports_test

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/ports"
	"github.com/Amund211/flashlight/internal/proofofwork"
)

func TestAnonymousChallengeHandler(t *testing.T) {
	t.Parallel()

	postChallenge := func(t *testing.T, handler http.HandlerFunc, ip string) *httptest.ResponseRecorder {
		t.Helper()
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/challenge", nil)
		withJSONContentType(r)
		withRequestIP(r, ip)
		w := httptest.NewRecorder()
		handler(w, r)
		return w
	}

	type challengeResponse struct {
		Challenge        string `json:"challenge"`
		Algorithm        string `json:"algorithm"`
		Difficulty       int    `json:"difficulty"`
		ExpiresInSeconds int64  `json:"expiresInSeconds"`
	}

	t.Run("returns a challenge the client can act on without parsing it", func(t *testing.T) {
		t.Parallel()
		issue, _ := newProofOfWorkScheme(t, 4)
		handler := newAnonymousChallengeHandler(t, issue)

		w := postChallenge(t, handler, "1.2.3.4")

		require.Equal(t, http.StatusOK, w.Code)
		require.Equal(t, "application/json", w.Header().Get("Content-Type"))
		require.Equal(t, "no-store", w.Header().Get("Cache-Control"),
			"a challenge is single-use and bound to one ip; no intermediary should hand it out twice")

		var resp challengeResponse
		require.NoError(t, json.NewDecoder(w.Body).Decode(&resp))
		require.NotEmpty(t, resp.Challenge)
		require.Equal(t, "sha256-leading-zeros-v1", resp.Algorithm,
			"clients key off this name and must reject values they don't know")
		require.Equal(t, 4, resp.Difficulty)
		require.Equal(t, int64(60), resp.ExpiresInSeconds)
	})

	t.Run("the default difficulty is zero", func(t *testing.T) {
		t.Parallel()
		issue, _ := newProofOfWorkScheme(t, proofofwork.DefaultDifficulty)
		handler := newAnonymousChallengeHandler(t, issue)

		var resp challengeResponse
		require.NoError(t, json.NewDecoder(postChallenge(t, handler, "1.2.3.4").Body).Decode(&resp))
		require.Equal(t, 0, resp.Difficulty,
			"the mechanism ships mandatory and the work ships at nothing")
	})

	t.Run("challenges are bound to the caller's ip", func(t *testing.T) {
		t.Parallel()
		var sawIPHash string
		issue := func(ipHash string, clientType string) (proofofwork.Challenge, error) {
			sawIPHash = ipHash
			return proofofwork.Challenge{Value: "blob", Algorithm: "x", ExpiresIn: 60 * time.Second}, nil
		}
		handler := newAnonymousChallengeHandler(t, issue)

		require.Equal(t, http.StatusOK, postChallenge(t, handler, "1.2.3.4").Code)
		require.Equal(t, ports.IP("1.2.3.4").Hash(), sawIPHash)
	})

	t.Run("difficulty is priced on the normalized client type", func(t *testing.T) {
		t.Parallel()
		var sawClientType string
		issue := func(ipHash string, clientType string) (proofofwork.Challenge, error) {
			sawClientType = clientType
			return proofofwork.Challenge{Value: "blob", Algorithm: "x", ExpiresIn: 60 * time.Second}, nil
		}
		handler := newAnonymousChallengeHandler(t, issue)

		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/challenge", nil)
		withJSONContentType(r)
		withRequestIP(r, "1.2.3.4")
		// Raw header values are attacker-controlled; the difficulty function
		// must only ever see the allowlisted normalization of them.
		r.Header.Set("X-Client-Type", "prism-but-not-really")
		r.Header.Set("X-Client-Version", "v99.99.99")
		w := httptest.NewRecorder()
		handler(w, r)

		require.Equal(t, http.StatusOK, w.Code)
		require.Equal(t, "unknown", sawClientType)
	})

	t.Run("returns cors headers", func(t *testing.T) {
		t.Parallel()
		issue, _ := newProofOfWorkScheme(t, 0)
		handler := newAnonymousChallengeHandler(t, issue)

		origin := "https://subdomain.example.com"
		r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/challenge", nil)
		r.Header.Set("Origin", origin)
		withJSONContentType(r)
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()

		handler(w, r)

		require.Equal(t, http.StatusOK, w.Code)
		require.Equal(t, origin, w.Header().Get("Access-Control-Allow-Origin"))
	})

	// Same reasoning as on login: a JSON content type is not
	// CORS-safelisted, so requiring it forces a preflight and keeps an
	// arbitrary origin from spending a visitor's challenge budget — and
	// with it the visitor's ability to log in.
	t.Run("415 on a content type that would skip the preflight", func(t *testing.T) {
		t.Parallel()
		for _, contentType := range []string{"", "text/plain", "application/x-www-form-urlencoded"} {
			t.Run(fmt.Sprintf("%q", contentType), func(t *testing.T) {
				t.Parallel()
				issue := func(ipHash string, clientType string) (proofofwork.Challenge, error) {
					t.Fatal("no challenge should be minted for a non-JSON content type")
					return proofofwork.Challenge{}, nil
				}
				handler := newAnonymousChallengeHandler(t, issue)

				r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/anonymous/challenge", nil)
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

	t.Run("500 when minting fails", func(t *testing.T) {
		t.Parallel()
		issue := func(ipHash string, clientType string) (proofofwork.Challenge, error) {
			return proofofwork.Challenge{}, errors.New("no entropy")
		}
		handler := newAnonymousChallengeHandler(t, issue)
		require.Equal(t, http.StatusInternalServerError, postChallenge(t, handler, "1.2.3.4").Code)
	})

	t.Run("rate limits per ip", func(t *testing.T) {
		t.Parallel()
		issued := 0
		issue := func(ipHash string, clientType string) (proofofwork.Challenge, error) {
			issued++
			return proofofwork.Challenge{Value: "blob", Algorithm: "x", ExpiresIn: 60 * time.Second}, nil
		}
		handler := newAnonymousChallengeHandler(t, issue)

		// The endpoint touches no database, but it is unauthenticated and
		// shouldn't be a free HMAC oracle. Same burst as login, which is the
		// only thing a challenge is good for. The bucket refills at 1/s off
		// the wall clock, so keep asking rather than pinning the boundary.
		accepted := 0
		var lastCode int
		for range 65 {
			lastCode = postChallenge(t, handler, "1.2.3.4").Code
			if lastCode != http.StatusOK {
				break
			}
			accepted++
		}

		require.Equal(t, http.StatusTooManyRequests, lastCode)
		require.GreaterOrEqual(t, accepted, 60, "the full burst should be allowed through")
		require.Equal(t, accepted, issued, "the throttled request must not mint a challenge")
		require.Equal(t, http.StatusOK, postChallenge(t, handler, "5.6.7.8").Code)
	})
}
