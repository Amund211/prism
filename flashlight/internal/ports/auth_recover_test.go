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

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ports"
)

const presentedCredential = "cred0123456789abcdefghijklmnopqrstuvwxyzABC"

func newRecoverHandler(t *testing.T, recoverSession app.RecoverMicrosoftSession, logger *slog.Logger) http.HandlerFunc {
	t.Helper()
	handler, stop := ports.MakeAuthRecoverHandler(recoverSession, fixedNowFunc(exchangeNow), authTestOrigins(t), logger, noopAuthMiddleware, emptyBlocklistConfig)
	t.Cleanup(stop)
	return handler
}

type recoverCall struct {
	calls      int
	credential string
	transport  domain.MicrosoftClientType
	ipHash     string
}

func recoverReturning(err error, call *recoverCall) app.RecoverMicrosoftSession {
	return func(_ context.Context, credential string, transport domain.MicrosoftClientType, ipHash string) (app.MicrosoftExchanged, error) {
		if call != nil {
			call.calls++
			call.credential = credential
			call.transport = transport
			call.ipHash = ipHash
		}
		if err != nil {
			return app.MicrosoftExchanged{}, err
		}
		exchanged, _ := exchangeReturning(transport, nil, nil)(context.Background(), "", "", "")
		return exchanged, nil
	}
}

func credentialRequest(t *testing.T, path, body, cookie string) *http.Request {
	t.Helper()
	r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, path, strings.NewReader(body))
	withRequestIP(r, "1.2.3.4")
	withJSONContentType(r)
	if cookie != "" {
		r.AddCookie(&http.Cookie{Name: rememberMeCookieName, Value: cookie})
	}
	return r
}

func credentialBody(credential string) string {
	return fmt.Sprintf(`{"credential":%q}`, credential)
}

func TestAuthRecoverHandler(t *testing.T) {
	t.Parallel()

	t.Run("rainbow sends fl_rm and gets a new one", func(t *testing.T) {
		t.Parallel()
		var call recoverCall
		handler := newRecoverHandler(t, recoverReturning(nil, &call), authTestLogger)

		r := credentialRequest(t, "/v1/auth/recover", `{}`, presentedCredential)
		r.Header.Set("Origin", "https://example.com")
		w := httptest.NewRecorder()
		handler(w, r)

		resp := w.Result()
		require.Equal(t, http.StatusOK, resp.StatusCode)
		require.Equal(t, recoverCall{calls: 1, credential: presentedCredential, transport: domain.MicrosoftClientRainbow, ipHash: call.ipHash}, call)
		require.NotEmpty(t, call.ipHash)
		require.Equal(t, "no-store", resp.Header.Get("Cache-Control"))
		require.Equal(t, "https://example.com", resp.Header.Get("Access-Control-Allow-Origin"))
		require.Equal(t, "true", resp.Header.Get("Access-Control-Allow-Credentials"))

		cookie := findCookie(t, resp, rememberMeCookieName)
		require.Equal(t, testCredential, cookie.Value)
		require.Equal(t, "/v1/auth/", cookie.Path)
		require.Empty(t, cookie.Domain, "host-only")
		require.Equal(t, 7776000, cookie.MaxAge, "Max-Age is re-set on every recover")
		require.True(t, cookie.Secure)
		require.True(t, cookie.HttpOnly)
		require.Equal(t, http.SameSiteLaxMode, cookie.SameSite)

		var body map[string]any
		require.NoError(t, json.Unmarshal(w.Body.Bytes(), &body))
		require.Equal(t, "flsess_microsoft", body["sessionId"])
		require.Equal(t, "microsoft", body["tier"])
		require.EqualValues(t, 3600, body["expiresInSeconds"])
		require.Equal(t, "a937646b-f115-44c3-8dbf-9ae4a65669a0", body["uuid"])
		require.NotContains(t, body, "credential")
	})

	t.Run("prism sends the credential in the body and gets it back there", func(t *testing.T) {
		t.Parallel()
		var call recoverCall
		handler := newRecoverHandler(t, recoverReturning(nil, &call), authTestLogger)

		w := httptest.NewRecorder()
		handler(w, credentialRequest(t, "/v1/auth/recover", credentialBody(presentedCredential), ""))

		require.Equal(t, http.StatusOK, w.Code)
		require.Equal(t, presentedCredential, call.credential)
		require.Equal(t, domain.MicrosoftClientPrism, call.transport)
		require.Empty(t, w.Result().Cookies())
		var body map[string]any
		require.NoError(t, json.Unmarshal(w.Body.Bytes(), &body))
		require.Equal(t, "flsess_microsoft", body["sessionId"])
		require.Equal(t, "a937646b-f115-44c3-8dbf-9ae4a65669a0", body["uuid"])
		require.Equal(t, testCredential, body["credential"])
	})

	for _, tc := range []struct {
		err    error
		status int
	}{
		{domain.ErrUserCredentialNotFound, http.StatusUnauthorized},
		{domain.ErrUserCredentialStale, http.StatusUnauthorized},
		{domain.ErrUserCredentialClientMismatch, http.StatusUnauthorized},
		{domain.ErrAuthSessionIssuanceRefused, http.StatusTooManyRequests},
		{errors.New("db down"), http.StatusInternalServerError},
	} {
		t.Run(fmt.Sprintf("%d for %v, and fl_rm is left alone", tc.status, tc.err), func(t *testing.T) {
			t.Parallel()
			handler := newRecoverHandler(t, recoverReturning(fmt.Errorf("wrapped: %w", tc.err), nil), authTestLogger)

			w := httptest.NewRecorder()
			handler(w, credentialRequest(t, "/v1/auth/recover", `{}`, presentedCredential))

			require.Equal(t, tc.status, w.Code)
			require.Empty(t, w.Result().Cookies())
		})
	}

	for name, tc := range map[string]struct {
		body   string
		cookie string
		status int
	}{
		"no credential":           {`{}`, "", http.StatusUnauthorized},
		"empty body credential":   {credentialBody(""), "", http.StatusUnauthorized},
		"short cookie":            {`{}`, presentedCredential[:42], http.StatusUnauthorized},
		"long body credential":    {credentialBody(presentedCredential + "x"), "", http.StatusUnauthorized},
		"bad chars in credential": {credentialBody(presentedCredential[:42] + "+"), "", http.StatusUnauthorized},
		"cookie and body":         {credentialBody(presentedCredential), presentedCredential, http.StatusBadRequest},
		"not json":                {"nope", presentedCredential, http.StatusBadRequest},
		"no body":                 {"", presentedCredential, http.StatusBadRequest},
		"body too large":          {fmt.Sprintf(`{"pad":%q}`, strings.Repeat("p", 4096)), presentedCredential, http.StatusBadRequest},
	} {
		t.Run(fmt.Sprintf("%d for %s", tc.status, name), func(t *testing.T) {
			t.Parallel()
			var call recoverCall
			handler := newRecoverHandler(t, recoverReturning(nil, &call), authTestLogger)

			w := httptest.NewRecorder()
			handler(w, credentialRequest(t, "/v1/auth/recover", tc.body, tc.cookie))

			require.Equal(t, tc.status, w.Code)
			require.Zero(t, call.calls)
			require.Empty(t, w.Result().Cookies())
		})
	}

	t.Run("415 without a json content type", func(t *testing.T) {
		t.Parallel()
		var call recoverCall
		handler := newRecoverHandler(t, recoverReturning(nil, &call), authTestLogger)

		r := credentialRequest(t, "/v1/auth/recover", `{}`, presentedCredential)
		r.Header.Set("Content-Type", "text/plain")
		w := httptest.NewRecorder()
		handler(w, r)

		require.Equal(t, http.StatusUnsupportedMediaType, w.Code)
		require.Zero(t, call.calls)
	})

	t.Run("the presented and the new credential stay out of the log", func(t *testing.T) {
		t.Parallel()
		var logs bytes.Buffer
		logger := slog.New(slog.NewJSONHandler(&logs, nil))

		for _, err := range []error{nil, domain.ErrUserCredentialStale, domain.ErrUserCredentialClientMismatch, errors.New("unexpected")} {
			handler := newRecoverHandler(t, recoverReturning(err, nil), logger)
			handler(httptest.NewRecorder(), credentialRequest(t, "/v1/auth/recover", `{}`, presentedCredential))
			handler(httptest.NewRecorder(), credentialRequest(t, "/v1/auth/recover", credentialBody(presentedCredential), ""))
		}

		require.NotEmpty(t, logs.String())
		for _, secret := range []string{presentedCredential, testCredential} {
			require.NotContains(t, logs.String(), secret)
		}
	})

	t.Run("rate limits per ip", func(t *testing.T) {
		t.Parallel()
		handler := newRecoverHandler(t, recoverReturning(nil, nil), authTestLogger)

		last := 0
		for range 100 {
			w := httptest.NewRecorder()
			handler(w, credentialRequest(t, "/v1/auth/recover", credentialBody(presentedCredential), ""))
			last = w.Code
			if last != http.StatusOK {
				break
			}
		}
		require.Equal(t, http.StatusTooManyRequests, last)
	})
}

func newLogoutHandler(t *testing.T, logout app.LogoutMicrosoft, logger *slog.Logger) http.HandlerFunc {
	t.Helper()
	handler, stop := ports.MakeAuthLogoutHandler(logout, authTestOrigins(t), logger, noopAuthMiddleware, emptyBlocklistConfig)
	t.Cleanup(stop)
	return handler
}

type logoutCall struct {
	calls      int
	credential string
}

func logoutReturning(err error, call *logoutCall) app.LogoutMicrosoft {
	return func(_ context.Context, credential string) (string, int, error) {
		if call != nil {
			call.calls++
			call.credential = credential
		}
		if err != nil {
			return "", 0, err
		}
		return "a937646bf11544c38dbf9ae4a65669a0", 3, nil
	}
}

func requireRememberMeCleared(t *testing.T, resp *http.Response) {
	t.Helper()
	cookie := findCookie(t, resp, rememberMeCookieName)
	require.Empty(t, cookie.Value)
	require.Negative(t, cookie.MaxAge, "Max-Age=0")
	require.Equal(t, "/v1/auth/", cookie.Path, "a clear on another path does not match")
	require.Empty(t, cookie.Domain)
	require.True(t, cookie.Secure)
	require.True(t, cookie.HttpOnly)
	require.Equal(t, http.SameSiteLaxMode, cookie.SameSite)
}

func TestAuthLogoutHandler(t *testing.T) {
	t.Parallel()

	t.Run("rainbow sends fl_rm and has it cleared", func(t *testing.T) {
		t.Parallel()
		var call logoutCall
		handler := newLogoutHandler(t, logoutReturning(nil, &call), authTestLogger)

		r := credentialRequest(t, "/v1/auth/logout", `{}`, presentedCredential)
		r.Header.Set("Origin", "https://example.com")
		w := httptest.NewRecorder()
		handler(w, r)

		resp := w.Result()
		require.Equal(t, http.StatusNoContent, resp.StatusCode)
		require.Equal(t, logoutCall{calls: 1, credential: presentedCredential}, call)
		require.Equal(t, "https://example.com", resp.Header.Get("Access-Control-Allow-Origin"))
		require.Equal(t, "true", resp.Header.Get("Access-Control-Allow-Credentials"))
		requireRememberMeCleared(t, resp)
	})

	t.Run("prism sends the credential in the body", func(t *testing.T) {
		t.Parallel()
		var call logoutCall
		handler := newLogoutHandler(t, logoutReturning(nil, &call), authTestLogger)

		w := httptest.NewRecorder()
		handler(w, credentialRequest(t, "/v1/auth/logout", credentialBody(presentedCredential), ""))

		require.Equal(t, http.StatusNoContent, w.Code)
		require.Equal(t, presentedCredential, call.credential)
		require.Empty(t, w.Result().Cookies())
	})

	t.Run("401 for an unknown credential, and a dead fl_rm is cleared", func(t *testing.T) {
		t.Parallel()
		handler := newLogoutHandler(t, logoutReturning(fmt.Errorf("wrapped: %w", domain.ErrUserCredentialNotFound), nil), authTestLogger)

		w := httptest.NewRecorder()
		handler(w, credentialRequest(t, "/v1/auth/logout", `{}`, presentedCredential))

		require.Equal(t, http.StatusUnauthorized, w.Code)
		requireRememberMeCleared(t, w.Result())
	})

	t.Run("500 keeps fl_rm so the user can retry", func(t *testing.T) {
		t.Parallel()
		handler := newLogoutHandler(t, logoutReturning(errors.New("db down"), nil), authTestLogger)

		w := httptest.NewRecorder()
		handler(w, credentialRequest(t, "/v1/auth/logout", `{}`, presentedCredential))

		require.Equal(t, http.StatusInternalServerError, w.Code)
		require.Empty(t, w.Result().Cookies())
	})

	for name, tc := range map[string]struct {
		body   string
		cookie string
		status int
	}{
		"no credential":   {`{}`, "", http.StatusUnauthorized},
		"cookie and body": {credentialBody(presentedCredential), presentedCredential, http.StatusBadRequest},
		"not json":        {"nope", "", http.StatusBadRequest},
	} {
		t.Run(fmt.Sprintf("%d for %s", tc.status, name), func(t *testing.T) {
			t.Parallel()
			var call logoutCall
			handler := newLogoutHandler(t, logoutReturning(nil, &call), authTestLogger)

			w := httptest.NewRecorder()
			handler(w, credentialRequest(t, "/v1/auth/logout", tc.body, tc.cookie))

			require.Equal(t, tc.status, w.Code)
			require.Zero(t, call.calls)
		})
	}

	t.Run("415 without a json content type", func(t *testing.T) {
		t.Parallel()
		var call logoutCall
		handler := newLogoutHandler(t, logoutReturning(nil, &call), authTestLogger)

		r := credentialRequest(t, "/v1/auth/logout", `{}`, presentedCredential)
		r.Header.Set("Content-Type", "text/plain")
		w := httptest.NewRecorder()
		handler(w, r)

		require.Equal(t, http.StatusUnsupportedMediaType, w.Code)
		require.Zero(t, call.calls)
	})

	t.Run("the credential stays out of the log", func(t *testing.T) {
		t.Parallel()
		var logs bytes.Buffer
		logger := slog.New(slog.NewJSONHandler(&logs, nil))

		for _, err := range []error{nil, domain.ErrUserCredentialNotFound, errors.New("unexpected")} {
			handler := newLogoutHandler(t, logoutReturning(err, nil), logger)
			handler(httptest.NewRecorder(), credentialRequest(t, "/v1/auth/logout", `{}`, presentedCredential))
			handler(httptest.NewRecorder(), credentialRequest(t, "/v1/auth/logout", credentialBody(presentedCredential), ""))
		}

		require.NotEmpty(t, logs.String())
		require.NotContains(t, logs.String(), presentedCredential)
	})

	t.Run("rate limits per ip", func(t *testing.T) {
		t.Parallel()
		handler := newLogoutHandler(t, logoutReturning(nil, nil), authTestLogger)

		last := 0
		for range 100 {
			w := httptest.NewRecorder()
			handler(w, credentialRequest(t, "/v1/auth/logout", credentialBody(presentedCredential), ""))
			last = w.Code
			if last != http.StatusNoContent {
				break
			}
		}
		require.Equal(t, http.StatusTooManyRequests, last)
	})
}
