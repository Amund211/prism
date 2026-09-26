package ports_test

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/getsentry/sentry-go"
	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ports"
)

const flowCookieName = "__Host-fl_flow"

func newMicrosoftStartHandler(t *testing.T, start app.StartMicrosoftSignIn, blocklistConfig ports.BlocklistConfig) http.HandlerFunc {
	t.Helper()
	handler, stop := ports.MakeMicrosoftSignInStartHandler(start, authTestLogger, noopAuthMiddleware, blocklistConfig)
	t.Cleanup(stop)
	return handler
}

func newMicrosoftCallbackHandler(t *testing.T, finish app.FinishMicrosoftSignIn, logger *slog.Logger, sentryMiddleware func(http.HandlerFunc) http.HandlerFunc) http.HandlerFunc {
	t.Helper()
	handler, stop := ports.MakeMicrosoftSignInCallbackHandler(finish, logger, sentryMiddleware, emptyBlocklistConfig)
	t.Cleanup(stop)
	return handler
}

func startReturning(started app.MicrosoftSignInStart, err error, calls *int) app.StartMicrosoftSignIn {
	return func(context.Context) (app.MicrosoftSignInStart, error) {
		if calls != nil {
			*calls++
		}
		return started, err
	}
}

var testStart = app.MicrosoftSignInStart{
	AuthorizeURL: "https://login.example.com/authorize?state=abc",
	FlowCookie:   "flflow_payload.signature",
	ExpiresIn:    10 * time.Minute,
}

func findCookie(t *testing.T, resp *http.Response, name string) *http.Cookie {
	t.Helper()
	for _, c := range resp.Cookies() {
		if c.Name == name {
			return c
		}
	}
	require.Failf(t, "cookie not set", "no %s cookie in the response", name)
	return nil
}

func TestMicrosoftSignInStartHandler(t *testing.T) {
	t.Parallel()

	t.Run("sets the flow cookie and redirects to Microsoft", func(t *testing.T) {
		t.Parallel()
		handler := newMicrosoftStartHandler(t, startReturning(testStart, nil, nil), emptyBlocklistConfig)

		r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/auth/microsoft/start", http.NoBody)
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()
		handler(w, r)

		resp := w.Result()
		require.Equal(t, http.StatusFound, resp.StatusCode)
		require.Equal(t, testStart.AuthorizeURL, resp.Header.Get("Location"))
		require.Equal(t, "no-store", resp.Header.Get("Cache-Control"))

		cookie := findCookie(t, resp, flowCookieName)
		require.Equal(t, testStart.FlowCookie, cookie.Value)
		require.Equal(t, "/", cookie.Path)
		require.Empty(t, cookie.Domain, "__Host- forbids a Domain attribute")
		require.True(t, cookie.Secure)
		require.True(t, cookie.HttpOnly)
		require.Equal(t, http.SameSiteLaxMode, cookie.SameSite, "Strict would drop it on the redirect back from Microsoft")
		require.Equal(t, 600, cookie.MaxAge)
	})

	t.Run("refuses return until the client flows exist", func(t *testing.T) {
		t.Parallel()
		calls := 0
		handler := newMicrosoftStartHandler(t, startReturning(testStart, nil, &calls), emptyBlocklistConfig)

		r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/auth/microsoft/start?return=https%3A%2F%2Fprismoverlay.com", http.NoBody)
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()
		handler(w, r)

		require.Equal(t, http.StatusBadRequest, w.Code)
		require.Zero(t, calls)
		require.Empty(t, w.Result().Cookies())
	})

	t.Run("500s when the flow cannot start", func(t *testing.T) {
		t.Parallel()
		handler := newMicrosoftStartHandler(t, startReturning(app.MicrosoftSignInStart{}, errors.New("boom"), nil), emptyBlocklistConfig)

		r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/auth/microsoft/start", http.NoBody)
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()
		handler(w, r)

		require.Equal(t, http.StatusInternalServerError, w.Code)
		require.Empty(t, w.Result().Cookies())
	})

	t.Run("blocked callers are refused", func(t *testing.T) {
		t.Parallel()
		calls := 0
		handler := newMicrosoftStartHandler(t, startReturning(testStart, nil, &calls), ports.BlocklistConfig{IPs: []string{"1.2.3.4"}})

		r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/auth/microsoft/start", http.NoBody)
		withRequestIP(r, "1.2.3.4")
		w := httptest.NewRecorder()
		handler(w, r)

		require.Equal(t, http.StatusBadRequest, w.Code)
		require.Zero(t, calls)
	})

	t.Run("rate limits per ip", func(t *testing.T) {
		t.Parallel()
		handler := newMicrosoftStartHandler(t, startReturning(testStart, nil, nil), emptyBlocklistConfig)

		do := func(ip string) int {
			r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/auth/microsoft/start", http.NoBody)
			withRequestIP(r, ip)
			w := httptest.NewRecorder()
			handler(w, r)
			return w.Code
		}

		last := 0
		for range 100 {
			last = do("1.2.3.4")
			if last != http.StatusFound {
				break
			}
		}
		require.Equal(t, http.StatusTooManyRequests, last)
		require.Equal(t, http.StatusFound, do("5.6.7.8"))
	})
}

type finishCall struct {
	calls      int
	flowCookie string
	state      string
	code       string
}

func finishReturning(account domain.MinecraftAccount, err error, call *finishCall) app.FinishMicrosoftSignIn {
	return func(_ context.Context, flowCookie, state, code string) (domain.MinecraftAccount, error) {
		if call != nil {
			call.calls++
			call.flowCookie = flowCookie
			call.state = state
			call.code = code
		}
		return account, err
	}
}

const (
	testCallbackCode  = "M.C123_the-secret-code"
	testCallbackState = "the-secret-state"
	testFlowCookie    = "flflow_the-secret-cookie.sig"
)

func callbackRequest(t *testing.T, query string, withCookie bool) *http.Request {
	t.Helper()
	r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/auth/microsoft/callback?"+query, http.NoBody)
	withRequestIP(r, "1.2.3.4")
	if withCookie {
		r.AddCookie(&http.Cookie{Name: flowCookieName, Value: testFlowCookie})
	}
	return r
}

var validCallbackQuery = "code=" + testCallbackCode + "&state=" + testCallbackState

func requireFlowCookieCleared(t *testing.T, resp *http.Response) {
	t.Helper()
	cookie := findCookie(t, resp, flowCookieName)
	require.Empty(t, cookie.Value)
	require.Negative(t, cookie.MaxAge)
	require.Equal(t, "/", cookie.Path)
	require.True(t, cookie.Secure, "a __Host- cookie without Secure is ignored, so it would not clear")
	require.True(t, cookie.HttpOnly)
}

func TestMicrosoftSignInCallbackHandler(t *testing.T) {
	t.Parallel()

	account := domain.MinecraftAccount{UUID: "a937646bf11544c38dbf9ae4a65669a0", Username: "Skydeath"}

	t.Run("signs in and clears the flow cookie", func(t *testing.T) {
		t.Parallel()
		var call finishCall
		handler := newMicrosoftCallbackHandler(t, finishReturning(account, nil, &call), authTestLogger, noopAuthMiddleware)

		w := httptest.NewRecorder()
		handler(w, callbackRequest(t, validCallbackQuery, true))

		resp := w.Result()
		require.Equal(t, http.StatusOK, resp.StatusCode)
		require.Equal(t, finishCall{calls: 1, flowCookie: testFlowCookie, state: testCallbackState, code: testCallbackCode}, call)
		require.Contains(t, w.Body.String(), "Signed in as Skydeath")
		requireFlowCookieCleared(t, resp)

		require.Equal(t, "text/html; charset=utf-8", resp.Header.Get("Content-Type"))
		require.Equal(t, "no-store", resp.Header.Get("Cache-Control"))
		require.Equal(t, "no-referrer", resp.Header.Get("Referrer-Policy"), "the page URL holds the code")
		require.Contains(t, resp.Header.Get("Content-Security-Policy"), "default-src 'none'")
		require.Equal(t, "nosniff", resp.Header.Get("X-Content-Type-Options"))
	})

	t.Run("passes an absent cookie as empty", func(t *testing.T) {
		t.Parallel()
		var call finishCall
		handler := newMicrosoftCallbackHandler(t, finishReturning(domain.MinecraftAccount{}, domain.ErrMicrosoftSignInFlowMissing, &call), authTestLogger, noopAuthMiddleware)

		w := httptest.NewRecorder()
		handler(w, callbackRequest(t, validCallbackQuery, false))

		require.Equal(t, 1, call.calls)
		require.Empty(t, call.flowCookie)
		require.Equal(t, http.StatusBadRequest, w.Code)
		require.Contains(t, w.Body.String(), "flow_missing")
	})

	t.Run("escapes the username", func(t *testing.T) {
		t.Parallel()
		handler := newMicrosoftCallbackHandler(t, finishReturning(domain.MinecraftAccount{UUID: "x", Username: "<script>"}, nil, nil), authTestLogger, noopAuthMiddleware)

		w := httptest.NewRecorder()
		handler(w, callbackRequest(t, validCallbackQuery, true))

		require.NotContains(t, w.Body.String(), "<script>")
		require.Contains(t, w.Body.String(), "&lt;script&gt;")
	})

	for _, tc := range []struct {
		err    error
		code   string
		status int
	}{
		{domain.ErrMicrosoftSignInFlowMissing, "flow_missing", http.StatusBadRequest},
		{domain.ErrMicrosoftSignInFlowInvalid, "flow_invalid", http.StatusBadRequest},
		{domain.ErrMicrosoftSignInFlowExpired, "flow_expired", http.StatusBadRequest},
		{domain.ErrMicrosoftSignInStateMismatch, "state_mismatch", http.StatusBadRequest},
		{domain.ErrMicrosoftCodeRejected, "code_rejected", http.StatusBadRequest},
		{domain.ErrXbox, "xbox_refused", http.StatusForbidden},
		{domain.ErrNoXboxAccount, "no_xbox_account", http.StatusForbidden},
		{domain.ErrXboxUnavailableInRegion, "xbox_unavailable_in_region", http.StatusForbidden},
		{domain.ErrAdultVerificationRequired, "adult_verification_required", http.StatusForbidden},
		{domain.ErrChildAccount, "child_account", http.StatusForbidden},
		{domain.ErrClientNotApproved, "client_not_approved", http.StatusForbidden},
		{domain.ErrNoGame, "no_game", http.StatusForbidden},
		{domain.ErrNoProfile, "no_profile", http.StatusForbidden},
		{domain.ErrTemporarilyUnavailable, "temporarily_unavailable", http.StatusServiceUnavailable},
		{errors.New("something unexpected"), "internal_error", http.StatusInternalServerError},
	} {
		t.Run("renders "+tc.code, func(t *testing.T) {
			t.Parallel()
			handler := newMicrosoftCallbackHandler(t, finishReturning(domain.MinecraftAccount{}, fmt.Errorf("wrapped: %w", tc.err), nil), authTestLogger, noopAuthMiddleware)

			w := httptest.NewRecorder()
			handler(w, callbackRequest(t, validCallbackQuery, true))

			require.Equal(t, tc.status, w.Code)
			require.Contains(t, w.Body.String(), tc.code)
			require.NotContains(t, w.Body.String(), "wrapped", "the page shows the code, not the error text")
			requireFlowCookieCleared(t, w.Result())
		})
	}

	t.Run("an error from Microsoft does not reach the chain", func(t *testing.T) {
		t.Parallel()
		var call finishCall
		handler := newMicrosoftCallbackHandler(t, finishReturning(account, nil, &call), authTestLogger, noopAuthMiddleware)

		w := httptest.NewRecorder()
		handler(w, callbackRequest(t, "error=access_denied&error_description=The+user+said+no&state="+testCallbackState, true))

		require.Zero(t, call.calls)
		require.Equal(t, http.StatusBadRequest, w.Code)
		require.Contains(t, w.Body.String(), "microsoft_error")
		requireFlowCookieCleared(t, w.Result())
	})

	for name, query := range map[string]string{
		"no code":  "state=" + testCallbackState,
		"no state": "code=" + testCallbackCode,
		"nothing":  "",
	} {
		t.Run("refuses a callback with "+name, func(t *testing.T) {
			t.Parallel()
			var call finishCall
			handler := newMicrosoftCallbackHandler(t, finishReturning(account, nil, &call), authTestLogger, noopAuthMiddleware)

			w := httptest.NewRecorder()
			handler(w, callbackRequest(t, query, true))

			require.Zero(t, call.calls)
			require.Equal(t, http.StatusBadRequest, w.Code)
			require.Contains(t, w.Body.String(), "invalid_callback")
			requireFlowCookieCleared(t, w.Result())
		})
	}

	t.Run("the code, state and cookie reach neither the log nor Sentry", func(t *testing.T) {
		t.Parallel()
		var logs bytes.Buffer
		logger := slog.New(slog.NewJSONHandler(&logs, nil))

		var sentryRequests []*sentry.Request
		recordingSentry := func(next http.HandlerFunc) http.HandlerFunc {
			return func(w http.ResponseWriter, r *http.Request) {
				sentryRequests = append(sentryRequests, sentry.NewRequest(r))
				next(w, r)
			}
		}

		for _, err := range []error{nil, domain.ErrClientNotApproved, domain.ErrMicrosoftSignInStateMismatch, errors.New("unexpected")} {
			handler := newMicrosoftCallbackHandler(t, finishReturning(account, err, nil), logger, recordingSentry)
			w := httptest.NewRecorder()
			handler(w, callbackRequest(t, validCallbackQuery, true))
		}

		require.NotEmpty(t, logs.String())
		require.Len(t, sentryRequests, 4)
		for _, secret := range []string{testCallbackCode, testCallbackState, testFlowCookie} {
			require.NotContains(t, logs.String(), secret)
			for _, req := range sentryRequests {
				require.NotContains(t, fmt.Sprintf("%+v", *req), secret)
			}
		}
	})

	t.Run("rate limits per ip", func(t *testing.T) {
		t.Parallel()
		handler := newMicrosoftCallbackHandler(t, finishReturning(account, nil, nil), authTestLogger, noopAuthMiddleware)

		last := 0
		for range 100 {
			w := httptest.NewRecorder()
			handler(w, callbackRequest(t, validCallbackQuery, true))
			last = w.Code
			if last != http.StatusOK {
				break
			}
		}
		require.Equal(t, http.StatusTooManyRequests, last)
	})
}
