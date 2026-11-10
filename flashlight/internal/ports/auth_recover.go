package ports

import (
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"regexp"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
)

var credentialRx = regexp.MustCompile(`^[A-Za-z0-9_-]{43}$`)

type credentialRequest struct {
	Credential string `json:"credential"`
}

func rememberMeCookie(value string, maxAge int) *http.Cookie {
	return &http.Cookie{
		Name:     rememberMeCookieName,
		Value:    value,
		Path:     "/v1/auth/",
		MaxAge:   maxAge,
		Secure:   true,
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
	}
}

// Looser than sign-in: every prism start recovers, often many behind one NAT.
func newCredentialIPLimiters() (ratelimiting.RequestRateLimiter, ratelimiting.RequestRateLimiter, func()) {
	short, stopShort := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(1),
		ratelimiting.BurstSize(60),
	)
	long, stopLong := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(0.1),
		ratelimiting.BurstSize(200),
	)
	stop := func() {
		stopShort()
		stopLong()
	}
	return ratelimiting.NewRequestBasedRateLimiter(short, IPHashKeyFunc), ratelimiting.NewRequestBasedRateLimiter(long, IPHashKeyFunc), stop
}

func readCredential(w http.ResponseWriter, r *http.Request) (string, domain.MicrosoftClientType, int) {
	var body credentialRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, authBodyMaxBytes)).Decode(&body); err != nil {
		return "", "", http.StatusBadRequest
	}

	cookie, cookieErr := r.Cookie(rememberMeCookieName)
	hasCookie := cookieErr == nil
	switch {
	case body.Credential != "" && hasCookie:
		return "", "", http.StatusBadRequest
	case body.Credential != "":
		if !credentialRx.MatchString(body.Credential) {
			return "", domain.MicrosoftClientPrism, http.StatusUnauthorized
		}
		return body.Credential, domain.MicrosoftClientPrism, 0
	case hasCookie:
		if !credentialRx.MatchString(cookie.Value) {
			return "", domain.MicrosoftClientRainbow, http.StatusUnauthorized
		}
		return cookie.Value, domain.MicrosoftClientRainbow, 0
	default:
		return "", "", http.StatusUnauthorized
	}
}

// MakeAuthRecoverHandler returns a handler for POST /v1/auth/recover: a
// credential for a new Microsoft-tier session and the credential's
// successor. Rainbow sends and gets fl_rm, prism { credential }. The path
// is version-pinned by fl_rm's Path=/v1/auth/.
func MakeAuthRecoverHandler(
	recoverSession app.RecoverMicrosoftSession,
	nowFunc func() time.Time,
	allowedOrigins *DomainSuffixes,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
	blocklistConfig BlocklistConfig,
) (http.HandlerFunc, func()) {
	ipRateLimiter, ipRateLimiterLong, stop := newCredentialIPLimiters()

	middleware := ComposeMiddlewares(
		NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		BuildBlocklistMiddleware(blocklistConfig),
		buildMetricsMiddleware("auth-recover"),
		NewReportingMetaMiddleware("auth-recover"),
		BuildCredentialedCORSMiddleware(allowedOrigins),
		NewRateLimitMiddleware(ipRateLimiter, makeOnAuthLimitExceeded(ipRateLimiter)),
		NewRateLimitMiddleware(ipRateLimiterLong, makeOnAuthLimitExceeded(ipRateLimiterLong)),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		logger := logging.FromContext(ctx)

		// Forces a CORS preflight, as on anonymous login.
		if !hasJSONContentType(r) {
			http.Error(w, "Content-Type must be application/json", http.StatusUnsupportedMediaType)
			return
		}

		credential, transport, status := readCredential(w, r)
		if status != 0 {
			logger.InfoContext(ctx, "Refused recover request", "status", status, "clientType", string(transport))
			http.Error(w, http.StatusText(status), status)
			return
		}

		// A failed recover never clears fl_rm: a tab that lost a rotation
		// race would clear the cookie the winning tab was just given.
		recovered, err := recoverSession(ctx, credential, transport, GetIP(r).Hash())
		switch {
		case errors.Is(err, domain.ErrUserCredentialStale),
			errors.Is(err, domain.ErrUserCredentialClientMismatch):
			// Safe to log: no error on this path quotes the credential.
			logger.WarnContext(ctx, "Refused recover", "clientType", string(transport), "error", err.Error())
			http.Error(w, "Sign in again", http.StatusUnauthorized)
			return
		case errors.Is(err, domain.ErrUserCredentialNotFound):
			logger.InfoContext(ctx, "Refused recover", "clientType", string(transport), "error", err.Error())
			http.Error(w, "Sign in again", http.StatusUnauthorized)
			return
		case errors.Is(err, domain.ErrAuthSessionIssuanceRefused):
			logger.InfoContext(ctx, "Refused recover issuance", "error", err.Error())
			http.Error(w, "Too many sessions issued", http.StatusTooManyRequests)
			return
		case err != nil:
			logger.ErrorContext(ctx, "Recover failed", "error", err.Error())
			reporting.Report(ctx, fmt.Errorf("recover: %w", err))
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

		response, err := newMicrosoftSessionResponse(recovered, nowFunc())
		if err != nil {
			logger.ErrorContext(ctx, "Recover failed", "error", err.Error())
			reporting.Report(ctx, fmt.Errorf("recover: %w", err))
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}
		if transport == domain.MicrosoftClientRainbow {
			http.SetCookie(w, rememberMeCookie(recovered.Credential, rememberMeMaxAge))
		} else {
			response.Credential = recovered.Credential
		}

		logger.InfoContext(ctx, "Recover succeeded", "clientType", string(transport), "identityKey", recovered.Session.IdentityKey)
		writeAuthJSONResponse(ctx, w, "recover", response)
	}

	return middleware(handler), stop
}

// MakeAuthLogoutHandler returns a handler for POST /v1/auth/logout: delete
// every credential of the presented credential's identity. Live sessions
// run to their own deadline. Clears fl_rm unless the delete failed.
func MakeAuthLogoutHandler(
	logout app.LogoutMicrosoft,
	allowedOrigins *DomainSuffixes,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
	blocklistConfig BlocklistConfig,
) (http.HandlerFunc, func()) {
	ipRateLimiter, ipRateLimiterLong, stop := newCredentialIPLimiters()

	middleware := ComposeMiddlewares(
		NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		BuildBlocklistMiddleware(blocklistConfig),
		buildMetricsMiddleware("auth-logout"),
		NewReportingMetaMiddleware("auth-logout"),
		BuildCredentialedCORSMiddleware(allowedOrigins),
		NewRateLimitMiddleware(ipRateLimiter, makeOnAuthLimitExceeded(ipRateLimiter)),
		NewRateLimitMiddleware(ipRateLimiterLong, makeOnAuthLimitExceeded(ipRateLimiterLong)),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		logger := logging.FromContext(ctx)

		if !hasJSONContentType(r) {
			http.Error(w, "Content-Type must be application/json", http.StatusUnsupportedMediaType)
			return
		}

		credential, transport, status := readCredential(w, r)
		clearCookie := func() {
			if transport == domain.MicrosoftClientRainbow {
				http.SetCookie(w, rememberMeCookie("", -1))
			}
		}
		if status != 0 {
			logger.InfoContext(ctx, "Refused logout request", "status", status, "clientType", string(transport))
			if status == http.StatusUnauthorized {
				clearCookie()
			}
			http.Error(w, http.StatusText(status), status)
			return
		}

		identityKey, deleted, err := logout(ctx, credential)
		switch {
		case errors.Is(err, domain.ErrUserCredentialNotFound):
			logger.InfoContext(ctx, "Refused logout", "clientType", string(transport), "error", err.Error())
			clearCookie()
			http.Error(w, "Not signed in", http.StatusUnauthorized)
			return
		case err != nil:
			// fl_rm is kept so the user can retry.
			logger.ErrorContext(ctx, "Logout failed", "error", err.Error())
			reporting.Report(ctx, fmt.Errorf("logout: %w", err))
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

		clearCookie()
		logger.InfoContext(ctx, "Logout succeeded", "clientType", string(transport), "identityKey", identityKey, "deleted", deleted)
		w.Header().Set("Cache-Control", "no-store")
		w.WriteHeader(http.StatusNoContent)
	}

	return middleware(handler), stop
}
