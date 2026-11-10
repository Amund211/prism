package ports

import (
	"errors"
	"fmt"
	"log/slog"
	"net/http"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
)

// Microseconds, as Postgres stores them: sign-ins less than 1s apart stay distinct.
const signInTimeLayout = "2006-01-02T15:04:05.000000Z07:00"

type activeSignInResponse struct {
	ClientType string `json:"clientType"`
	CreatedAt  string `json:"createdAt"`
	LastUsedAt string `json:"lastUsedAt"`
}

type credentialsResponse struct {
	Credentials []activeSignInResponse `json:"credentials"`
}

// MakeAuthCredentialsHandler returns a handler for GET /v1/auth/credentials:
// the active-sign-ins view. It takes a Microsoft-tier bearer and returns
// clientType, createdAt and lastUsedAt (RFC 3339 with microseconds, UTC) for each Microsoft
// sign-in of that identity with a live credential. It never returns a hash.
// No bearer is a 401, another tier a 403.
func MakeAuthCredentialsHandler(
	list app.ListMicrosoftSignIns,
	allowedOrigins *DomainSuffixes,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
	bearerAuthMiddleware func(http.HandlerFunc) http.HandlerFunc,
	blocklistConfig BlocklistConfig,
) (http.HandlerFunc, func()) {
	ipRateLimiter, ipRateLimiterLong, stopIP := newCredentialIPLimiters()
	identityLimiter, stopIdentity := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(0.5),
		ratelimiting.BurstSize(20),
	)
	identityRateLimiter := ratelimiting.NewRequestBasedRateLimiter(identityLimiter, UserIDKeyFunc)
	stop := func() {
		stopIP()
		stopIdentity()
	}

	middleware := ComposeMiddlewares(
		NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		BuildBlocklistMiddleware(blocklistConfig),
		buildMetricsMiddleware("auth-credentials"),
		NewReportingMetaMiddleware("auth-credentials"),
		BuildCORSMiddleware(allowedOrigins),
		NewRateLimitMiddleware(ipRateLimiter, makeOnAuthLimitExceeded(ipRateLimiter)),
		NewRateLimitMiddleware(ipRateLimiterLong, makeOnAuthLimitExceeded(ipRateLimiterLong)),
		bearerAuthMiddleware,
		NewRateLimitMiddleware(identityRateLimiter, makeOnAuthLimitExceeded(identityRateLimiter)),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		logger := logging.FromContext(ctx)

		auth, ok := AuthFromContext(ctx)
		if !ok {
			http.Error(w, "Sign in with Microsoft", http.StatusUnauthorized)
			return
		}

		signIns, err := list(ctx, auth.IdentityType, auth.IdentityKey)
		switch {
		case errors.Is(err, domain.ErrAuthSessionTierRefused):
			logger.InfoContext(ctx, "Refused credentials listing", "tier", string(auth.IdentityType))
			http.Error(w, "Sign in with Microsoft", http.StatusForbidden)
			return
		case err != nil:
			logger.ErrorContext(ctx, "Credentials listing failed", "error", err.Error())
			reporting.Report(ctx, fmt.Errorf("list credentials: %w", err))
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

		response := credentialsResponse{Credentials: make([]activeSignInResponse, 0, len(signIns))}
		for _, signIn := range signIns {
			response.Credentials = append(response.Credentials, activeSignInResponse{
				ClientType: string(signIn.ClientType),
				CreatedAt:  signIn.CreatedAt.UTC().Format(signInTimeLayout),
				LastUsedAt: signIn.LastUsedAt.UTC().Format(signInTimeLayout),
			})
		}

		logger.InfoContext(ctx, "Listed credentials", "count", len(signIns))
		writeAuthJSONResponse(ctx, w, "credentials", response)
	}

	return middleware(handler), stop
}
