package ports_test

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ports"
)

const credentialsTestBearer = "flsess_the-bearer-of-this-request.sig"

var credentialsNow = time.Date(2026, 9, 27, 12, 0, 0, 0, time.UTC)

type listSignInsCall struct {
	calls        int
	identityType domain.AuthSessionIdentityType
	identityKey  string
}

func listSignInsReturning(signIns []domain.ActiveSignIn, err error, call *listSignInsCall) app.ListMicrosoftSignIns {
	return func(_ context.Context, identityType domain.AuthSessionIdentityType, identityKey string) ([]domain.ActiveSignIn, error) {
		if call != nil {
			call.calls++
			call.identityType = identityType
			call.identityKey = identityKey
		}
		return signIns, err
	}
}

func bearerFor(tier domain.AuthSessionIdentityType) func(http.HandlerFunc) http.HandlerFunc {
	validate := func(_ context.Context, sessionID string) (domain.AuthSession, error) {
		if sessionID != credentialsTestBearer {
			return domain.AuthSession{}, domain.ErrAuthSessionNotFound
		}
		return domain.AuthSession{
			ID:           sessionID,
			IdentityType: tier,
			IdentityKey:  "a937646bf11544c38dbf9ae4a65669a0",
			ExpiresAt:    credentialsNow.Add(time.Hour),
		}, nil
	}
	return ports.NewBearerAuthMiddleware(validate, fixedNowFunc(credentialsNow), emptyBlocklistConfig)
}

func newCredentialsHandler(t *testing.T, list app.ListMicrosoftSignIns, bearer func(http.HandlerFunc) http.HandlerFunc, logger *slog.Logger) http.HandlerFunc {
	t.Helper()
	handler, stop := ports.MakeAuthCredentialsHandler(list, authTestOrigins(t), logger, noopAuthMiddleware, bearer, emptyBlocklistConfig)
	t.Cleanup(stop)
	return handler
}

func credentialsRequest(t *testing.T, bearer string) *http.Request {
	t.Helper()
	r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/auth/credentials", http.NoBody)
	withRequestIP(r, "1.2.3.4")
	if bearer != "" {
		r.Header.Set("Authorization", "Bearer "+bearer)
	}
	return r
}

func TestAuthCredentialsHandler(t *testing.T) {
	t.Parallel()

	signIns := []domain.ActiveSignIn{
		{
			ClientType: domain.MicrosoftClientPrism,
			CreatedAt:  time.Date(2026, 9, 27, 11, 0, 0, 0, time.FixedZone("CEST", 2*60*60)),
			LastUsedAt: time.Date(2026, 9, 27, 11, 59, 30, 123456789, time.UTC),
		},
		{
			ClientType: domain.MicrosoftClientRainbow,
			CreatedAt:  time.Date(2026, 9, 1, 8, 0, 0, 0, time.UTC),
			LastUsedAt: time.Date(2026, 9, 26, 20, 0, 0, 0, time.UTC),
		},
	}

	t.Run("lists the sign-ins of a microsoft session", func(t *testing.T) {
		t.Parallel()
		call := &listSignInsCall{}
		handler := newCredentialsHandler(t, listSignInsReturning(signIns, nil, call), bearerFor(domain.AuthSessionIdentityMicrosoft), authTestLogger)

		w := httptest.NewRecorder()
		handler(w, credentialsRequest(t, credentialsTestBearer))

		require.Equal(t, http.StatusOK, w.Code)
		require.JSONEq(t, `{"credentials":[
			{"clientType":"prism","createdAt":"2026-09-27T09:00:00.000000Z","lastUsedAt":"2026-09-27T11:59:30.123456Z"},
			{"clientType":"rainbow","createdAt":"2026-09-01T08:00:00.000000Z","lastUsedAt":"2026-09-26T20:00:00.000000Z"}
		]}`, w.Body.String())
		require.Equal(t, "application/json", w.Header().Get("Content-Type"))
		require.Equal(t, "no-store", w.Header().Get("Cache-Control"))
		require.Equal(t, ports.AuthSessionValid, w.Header().Get(ports.AuthSessionHeader))
		require.Equal(t, listSignInsCall{1, domain.AuthSessionIdentityMicrosoft, "a937646bf11544c38dbf9ae4a65669a0"}, *call)
	})

	t.Run("no sign-ins is an empty list, not null", func(t *testing.T) {
		t.Parallel()
		for _, listed := range [][]domain.ActiveSignIn{nil, {}} {
			handler := newCredentialsHandler(t, listSignInsReturning(listed, nil, nil), bearerFor(domain.AuthSessionIdentityMicrosoft), authTestLogger)
			w := httptest.NewRecorder()
			handler(w, credentialsRequest(t, credentialsTestBearer))
			require.Equal(t, http.StatusOK, w.Code)
			require.JSONEq(t, `{"credentials":[]}`, w.Body.String())
		}
	})

	t.Run("401 without a bearer", func(t *testing.T) {
		t.Parallel()
		call := &listSignInsCall{}
		handler := newCredentialsHandler(t, listSignInsReturning(signIns, nil, call), bearerFor(domain.AuthSessionIdentityMicrosoft), authTestLogger)

		r := credentialsRequest(t, "")
		r.Header.Set("Origin", "https://example.com")
		w := httptest.NewRecorder()
		handler(w, r)

		require.Equal(t, http.StatusUnauthorized, w.Code)
		require.Equal(t, "https://example.com", w.Header().Get("Access-Control-Allow-Origin"), "the browser must be able to read the 401")
		require.Zero(t, call.calls)
	})

	t.Run("401 for a bad bearer", func(t *testing.T) {
		t.Parallel()
		call := &listSignInsCall{}
		handler := newCredentialsHandler(t, listSignInsReturning(signIns, nil, call), bearerFor(domain.AuthSessionIdentityMicrosoft), authTestLogger)

		w := httptest.NewRecorder()
		handler(w, credentialsRequest(t, "flsess_garbage"))

		require.Equal(t, http.StatusUnauthorized, w.Code)
		require.Zero(t, call.calls)
	})

	t.Run("403 for a session of another tier", func(t *testing.T) {
		t.Parallel()
		call := &listSignInsCall{}
		handler := newCredentialsHandler(t, listSignInsReturning(nil, domain.ErrAuthSessionTierRefused, call), bearerFor(domain.AuthSessionIdentityAnonymous), authTestLogger)

		w := httptest.NewRecorder()
		handler(w, credentialsRequest(t, credentialsTestBearer))

		require.Equal(t, http.StatusForbidden, w.Code)
		require.Equal(t, domain.AuthSessionIdentityAnonymous, call.identityType)
		require.Equal(t, ports.AuthSessionValid, w.Header().Get(ports.AuthSessionHeader), "the session is fine; re-authenticating anonymously will not help")
	})

	t.Run("500 when the list fails", func(t *testing.T) {
		t.Parallel()
		handler := newCredentialsHandler(t, listSignInsReturning(nil, errors.New("db down"), nil), bearerFor(domain.AuthSessionIdentityMicrosoft), authTestLogger)

		w := httptest.NewRecorder()
		handler(w, credentialsRequest(t, credentialsTestBearer))

		require.Equal(t, http.StatusInternalServerError, w.Code)
		require.NotContains(t, w.Body.String(), "db down")
	})

	t.Run("CORS without credentials", func(t *testing.T) {
		t.Parallel()
		handler := newCredentialsHandler(t, listSignInsReturning(signIns, nil, nil), bearerFor(domain.AuthSessionIdentityMicrosoft), authTestLogger)

		r := credentialsRequest(t, credentialsTestBearer)
		r.Header.Set("Origin", "https://example.com")
		w := httptest.NewRecorder()
		handler(w, r)

		require.Equal(t, http.StatusOK, w.Code)
		require.Equal(t, "https://example.com", w.Header().Get("Access-Control-Allow-Origin"))
		require.Empty(t, w.Header().Get("Access-Control-Allow-Credentials"), "a bearer is not a cookie; fl_rm must not ride on this")
	})

	t.Run("the bearer stays out of the log", func(t *testing.T) {
		t.Parallel()
		var logs bytes.Buffer
		logger := slog.New(slog.NewJSONHandler(&logs, nil))

		for _, tc := range []struct {
			tier domain.AuthSessionIdentityType
			err  error
		}{
			{domain.AuthSessionIdentityMicrosoft, nil},
			{domain.AuthSessionIdentityAnonymous, domain.ErrAuthSessionTierRefused},
			{domain.AuthSessionIdentityMicrosoft, errors.New("unexpected")},
		} {
			handler := newCredentialsHandler(t, listSignInsReturning(signIns, tc.err, nil), bearerFor(tc.tier), logger)
			handler(httptest.NewRecorder(), credentialsRequest(t, credentialsTestBearer))
		}

		require.NotEmpty(t, logs.String())
		require.NotContains(t, logs.String(), credentialsTestBearer)
		require.NotContains(t, logs.String(), "the-bearer-of-this-request")
	})

	t.Run("rate limits", func(t *testing.T) {
		t.Parallel()
		handler := newCredentialsHandler(t, listSignInsReturning(signIns, nil, nil), bearerFor(domain.AuthSessionIdentityMicrosoft), authTestLogger)

		last := 0
		for range 100 {
			w := httptest.NewRecorder()
			handler(w, credentialsRequest(t, credentialsTestBearer))
			last = w.Code
			if last != http.StatusOK {
				break
			}
		}
		require.Equal(t, http.StatusTooManyRequests, last)
	})
}
