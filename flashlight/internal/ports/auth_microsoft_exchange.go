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
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

// rememberMeCookieName is rainbow's recovery credential. Path=/v1/auth/
// keeps it off data requests; the three endpoints that read it never move.
const rememberMeCookieName = "fl_rm"

// rememberMeMaxAge is 90 days, the credential's idle window.
const rememberMeMaxAge = 90 * 24 * 60 * 60

// resultMaxLength bounds the result token before it is unsealed.
const resultMaxLength = 1024

// verifierRx is an RFC 7636 code verifier.
var verifierRx = regexp.MustCompile(`^[A-Za-z0-9._~-]{43,128}$`)

type microsoftExchangeRequest struct {
	Result   string `json:"result"`
	Verifier string `json:"verifier"`
}

// microsoftSessionResponse is the body of exchange and recover.
type microsoftSessionResponse struct {
	authSessionResponse
	// UUID is the verified Minecraft UUID, dashed like every other uuid in
	// the API. Not on refresh: clients carry it across refreshes themselves.
	UUID string `json:"uuid"`
	// Credential is prism's recovery credential; rainbow's is fl_rm.
	Credential string `json:"credential,omitempty"`
}

func newMicrosoftSessionResponse(issued app.MicrosoftExchanged, now time.Time) (microsoftSessionResponse, error) {
	uuid, err := strutils.NormalizeUUID(issued.Session.IdentityKey)
	if err != nil {
		return microsoftSessionResponse{}, fmt.Errorf("failed to normalize identity key: %w", err)
	}
	return microsoftSessionResponse{
		authSessionResponse: sessionResponseFromSession(issued.Session, now),
		UUID:                uuid,
	}, nil
}

// MakeMicrosoftSignInExchangeHandler returns a handler for
// POST /v1/auth/microsoft/exchange { result, verifier }: a new
// credential and a Microsoft-tier session. Rainbow gets the credential as
// fl_rm, prism in the body.
func MakeMicrosoftSignInExchangeHandler(
	exchange app.ExchangeMicrosoftSignIn,
	nowFunc func() time.Time,
	allowedOrigins *DomainSuffixes,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
	blocklistConfig BlocklistConfig,
) (http.HandlerFunc, func()) {
	ipRateLimiter, stop := newMicrosoftSignInIPLimiter()

	middleware := ComposeMiddlewares(
		NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		BuildBlocklistMiddleware(blocklistConfig),
		buildMetricsMiddleware("auth-microsoft-exchange"),
		NewReportingMetaMiddleware("auth-microsoft-exchange"),
		BuildCredentialedCORSMiddleware(allowedOrigins),
		NewRateLimitMiddleware(ipRateLimiter, makeOnAuthLimitExceeded(ipRateLimiter)),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		logger := logging.FromContext(ctx)

		// Forces a CORS preflight, as on anonymous login.
		if !hasJSONContentType(r) {
			http.Error(w, "Content-Type must be application/json", http.StatusUnsupportedMediaType)
			return
		}

		var body microsoftExchangeRequest
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, authBodyMaxBytes)).Decode(&body); err != nil {
			logger.InfoContext(ctx, "Failed to decode Microsoft exchange body")
			http.Error(w, "Invalid request body", http.StatusBadRequest)
			return
		}
		if body.Result == "" || len(body.Result) > resultMaxLength {
			http.Error(w, "Invalid result", http.StatusBadRequest)
			return
		}
		if !verifierRx.MatchString(body.Verifier) {
			http.Error(w, "Invalid verifier", http.StatusBadRequest)
			return
		}

		exchanged, err := exchange(ctx, body.Result, body.Verifier, GetIP(r).Hash())
		switch {
		case errors.Is(err, domain.ErrMicrosoftSignInResultInvalid),
			errors.Is(err, domain.ErrMicrosoftSignInResultExpired),
			errors.Is(err, domain.ErrMicrosoftSignInVerifierMismatch):
			// Safe to log: no error on this path quotes the result or the
			// verifier.
			logger.InfoContext(ctx, "Refused Microsoft exchange", "error", err.Error())
			http.Error(w, "Sign in again", http.StatusUnauthorized)
			return
		case errors.Is(err, domain.ErrAuthSessionIssuanceRefused):
			logger.InfoContext(ctx, "Refused Microsoft exchange issuance", "error", err.Error())
			http.Error(w, "Too many sessions issued", http.StatusTooManyRequests)
			return
		case err != nil:
			logger.ErrorContext(ctx, "Microsoft exchange failed", "error", err.Error())
			reporting.Report(ctx, fmt.Errorf("microsoft exchange: %w", err))
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

		response, err := newMicrosoftSessionResponse(exchanged, nowFunc())
		if err != nil {
			logger.ErrorContext(ctx, "Microsoft exchange failed", "error", err.Error())
			reporting.Report(ctx, fmt.Errorf("microsoft exchange: %w", err))
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}
		if exchanged.ClientType == domain.MicrosoftClientRainbow {
			http.SetCookie(w, rememberMeCookie(exchanged.Credential, rememberMeMaxAge))
		} else {
			response.Credential = exchanged.Credential
		}

		logger.InfoContext(ctx, "Microsoft exchange succeeded", "clientType", string(exchanged.ClientType), "identityKey", exchanged.Session.IdentityKey)
		writeAuthJSONResponse(ctx, w, "microsoft exchange", response)
	}

	return middleware(handler), stop
}
