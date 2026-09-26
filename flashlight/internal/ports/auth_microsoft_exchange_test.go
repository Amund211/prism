package ports_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ports"
)

const (
	rememberMeCookieName = "fl_rm"
	testCredential       = "the-secret-credential"
	testVerifier         = "the-secret-verifier-0123456789abcdefghijklmnopq"
)

var exchangeNow = time.Date(2026, 9, 27, 12, 0, 0, 0, time.UTC)

func newMicrosoftExchangeHandler(t *testing.T, exchange app.ExchangeMicrosoftSignIn, logger *slog.Logger) http.HandlerFunc {
	t.Helper()
	handler, stop := ports.MakeMicrosoftSignInExchangeHandler(exchange, fixedNowFunc(exchangeNow), authTestOrigins(t), logger, noopAuthMiddleware, emptyBlocklistConfig)
	t.Cleanup(stop)
	return handler
}

func fixedNowFunc(now time.Time) func() time.Time {
	return func() time.Time { return now }
}

type exchangeCall struct {
	calls    int
	result   string
	verifier string
	ipHash   string
}

func exchangeReturning(clientType domain.MicrosoftClientType, err error, call *exchangeCall) app.ExchangeMicrosoftSignIn {
	return func(_ context.Context, result, verifier, ipHash string) (app.MicrosoftExchanged, error) {
		if call != nil {
			call.calls++
			call.result = result
			call.verifier = verifier
			call.ipHash = ipHash
		}
		if err != nil {
			return app.MicrosoftExchanged{}, err
		}
		return app.MicrosoftExchanged{
			Session: domain.AuthSession{
				ID:             "flsess_microsoft",
				IdentityType:   domain.AuthSessionIdentityMicrosoft,
				IdentityKey:    "a937646bf11544c38dbf9ae4a65669a0",
				ExpiresAt:      exchangeNow.Add(time.Hour),
				RefreshUntil:   exchangeNow.Add(2 * time.Hour),
				LifetimeEndsAt: exchangeNow.Add(24 * time.Hour),
			},
			ClientType: clientType,
			Credential: testCredential,
		}, nil
	}
}

func exchangeRequest(t *testing.T, body string) *http.Request {
	t.Helper()
	r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/microsoft/exchange", strings.NewReader(body))
	withRequestIP(r, "1.2.3.4")
	withJSONContentType(r)
	return r
}

func exchangeBody(result, verifier string) string {
	return fmt.Sprintf(`{"result":%q,"verifier":%q}`, result, verifier)
}

func TestMicrosoftSignInExchangeHandler(t *testing.T) {
	t.Parallel()

	t.Run("rainbow gets fl_rm and the session", func(t *testing.T) {
		t.Parallel()
		var call exchangeCall
		handler := newMicrosoftExchangeHandler(t, exchangeReturning(domain.MicrosoftClientRainbow, nil, &call), authTestLogger)

		r := exchangeRequest(t, exchangeBody(testResultToken, testVerifier))
		r.Header.Set("Origin", "https://example.com")
		w := httptest.NewRecorder()
		handler(w, r)

		resp := w.Result()
		require.Equal(t, http.StatusOK, resp.StatusCode)
		require.Equal(t, 1, call.calls)
		require.Equal(t, testResultToken, call.result)
		require.Equal(t, testVerifier, call.verifier)
		require.NotEmpty(t, call.ipHash)
		require.Equal(t, "no-store", resp.Header.Get("Cache-Control"))
		require.Equal(t, "https://example.com", resp.Header.Get("Access-Control-Allow-Origin"))
		require.Equal(t, "true", resp.Header.Get("Access-Control-Allow-Credentials"))

		cookie := findCookie(t, resp, rememberMeCookieName)
		require.Equal(t, testCredential, cookie.Value)
		require.Equal(t, "/v1/auth/", cookie.Path)
		require.Empty(t, cookie.Domain, "host-only")
		require.Equal(t, 7776000, cookie.MaxAge)
		require.True(t, cookie.Secure)
		require.True(t, cookie.HttpOnly)
		require.Equal(t, http.SameSiteLaxMode, cookie.SameSite)

		var body map[string]any
		require.NoError(t, json.Unmarshal(w.Body.Bytes(), &body))
		require.Equal(t, "flsess_microsoft", body["sessionId"])
		require.Equal(t, "microsoft", body["tier"])
		require.EqualValues(t, 3600, body["expiresInSeconds"])
		require.NotContains(t, body, "credential", "rainbow's credential is the cookie, never script-readable")
	})

	t.Run("prism gets the credential in the body and no cookie", func(t *testing.T) {
		t.Parallel()
		handler := newMicrosoftExchangeHandler(t, exchangeReturning(domain.MicrosoftClientPrism, nil, nil), authTestLogger)

		w := httptest.NewRecorder()
		handler(w, exchangeRequest(t, exchangeBody(testResultToken, testVerifier)))

		require.Equal(t, http.StatusOK, w.Code)
		require.Empty(t, w.Result().Cookies())
		var body map[string]any
		require.NoError(t, json.Unmarshal(w.Body.Bytes(), &body))
		require.Equal(t, "flsess_microsoft", body["sessionId"])
		require.Equal(t, "microsoft", body["tier"])
		require.Equal(t, testCredential, body["credential"])
	})

	for _, tc := range []struct {
		err    error
		status int
	}{
		{domain.ErrMicrosoftSignInResultInvalid, http.StatusUnauthorized},
		{domain.ErrMicrosoftSignInResultExpired, http.StatusUnauthorized},
		{domain.ErrMicrosoftSignInVerifierMismatch, http.StatusUnauthorized},
		{domain.ErrAuthSessionIssuanceRefused, http.StatusTooManyRequests},
		{errors.New("db down"), http.StatusInternalServerError},
	} {
		t.Run(fmt.Sprintf("%d for %v", tc.status, tc.err), func(t *testing.T) {
			t.Parallel()
			handler := newMicrosoftExchangeHandler(t, exchangeReturning(domain.MicrosoftClientRainbow, fmt.Errorf("wrapped: %w", tc.err), nil), authTestLogger)

			w := httptest.NewRecorder()
			handler(w, exchangeRequest(t, exchangeBody(testResultToken, testVerifier)))

			require.Equal(t, tc.status, w.Code)
			require.Empty(t, w.Result().Cookies())
		})
	}

	for name, body := range map[string]string{
		"not json":           "nope",
		"no result":          exchangeBody("", testVerifier),
		"result too long":    exchangeBody(strings.Repeat("r", 1025), testVerifier),
		"no verifier":        exchangeBody(testResultToken, ""),
		"short verifier":     exchangeBody(testResultToken, strings.Repeat("v", 42)),
		"long verifier":      exchangeBody(testResultToken, strings.Repeat("v", 129)),
		"verifier bad chars": exchangeBody(testResultToken, strings.Repeat("v", 42)+"+"),
		"body too large":     fmt.Sprintf(`{"pad":%q,"result":%q,"verifier":%q}`, strings.Repeat("p", 4096), testResultToken, testVerifier),
	} {
		t.Run("400 for "+name, func(t *testing.T) {
			t.Parallel()
			var call exchangeCall
			handler := newMicrosoftExchangeHandler(t, exchangeReturning(domain.MicrosoftClientRainbow, nil, &call), authTestLogger)

			w := httptest.NewRecorder()
			handler(w, exchangeRequest(t, body))

			require.Equal(t, http.StatusBadRequest, w.Code)
			require.Zero(t, call.calls)
		})
	}

	t.Run("415 without a json content type", func(t *testing.T) {
		t.Parallel()
		var call exchangeCall
		handler := newMicrosoftExchangeHandler(t, exchangeReturning(domain.MicrosoftClientRainbow, nil, &call), authTestLogger)

		r := exchangeRequest(t, exchangeBody(testResultToken, testVerifier))
		r.Header.Set("Content-Type", "text/plain")
		w := httptest.NewRecorder()
		handler(w, r)

		require.Equal(t, http.StatusUnsupportedMediaType, w.Code)
		require.Zero(t, call.calls)
	})

	t.Run("the result, verifier and credential stay out of the log", func(t *testing.T) {
		t.Parallel()
		var logs bytes.Buffer
		logger := slog.New(slog.NewJSONHandler(&logs, nil))

		for _, err := range []error{nil, domain.ErrMicrosoftSignInVerifierMismatch, errors.New("unexpected")} {
			for _, clientType := range []domain.MicrosoftClientType{domain.MicrosoftClientRainbow, domain.MicrosoftClientPrism} {
				handler := newMicrosoftExchangeHandler(t, exchangeReturning(clientType, err, nil), logger)
				handler(httptest.NewRecorder(), exchangeRequest(t, exchangeBody(testResultToken, testVerifier)))
			}
		}

		require.NotEmpty(t, logs.String())
		for _, secret := range []string{testResultToken, testVerifier, testCredential} {
			require.NotContains(t, logs.String(), secret)
		}
	})

	t.Run("rate limits per ip", func(t *testing.T) {
		t.Parallel()
		handler := newMicrosoftExchangeHandler(t, exchangeReturning(domain.MicrosoftClientPrism, nil, nil), authTestLogger)

		last := 0
		for range 100 {
			w := httptest.NewRecorder()
			handler(w, exchangeRequest(t, exchangeBody(testResultToken, testVerifier)))
			last = w.Code
			if last != http.StatusOK {
				break
			}
		}
		require.Equal(t, http.StatusTooManyRequests, last)
	})
}
