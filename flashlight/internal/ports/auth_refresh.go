package ports

import (
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
)

// MakeAuthRefreshHandler returns a handler for POST /v1/auth/refresh.
// Accepts a Bearer token (which may be past expires_at but within
// refresh_until). Tier-agnostic: the underlying use case branches on
// the stored session.
func MakeAuthRefreshHandler(
	refresh app.RefreshSession,
	nowFunc func() time.Time,
	allowedOrigins *DomainSuffixes,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
	blocklistConfig BlocklistConfig,
) (http.HandlerFunc, func()) {
	// A refresh costs a SELECT-FOR-UPDATE transaction on the session row (no
	// IP-cap UPDATE — that one is on the login path only), and the bearer is
	// only checked inside that transaction, so an unknown token is just as
	// expensive as a valid one. The request IP is all we can key on before
	// touching the database.
	ipLimiter, stopIPLimiter := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(1),
		ratelimiting.BurstSize(60),
	)
	ipRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		ipLimiter,
		IPHashKeyFunc,
	)
	ipLimiterLong, stopIPLimiterLong := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(0.1),
		ratelimiting.BurstSize(200),
	)
	ipRateLimiterLong := ratelimiting.NewRequestBasedRateLimiter(
		ipLimiterLong,
		IPHashKeyFunc,
	)

	middleware := ComposeMiddlewares(
		NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		BuildBlocklistMiddleware(blocklistConfig),
		buildMetricsMiddleware("auth-refresh"),
		NewReportingMetaMiddleware("auth-refresh"),
		BuildCORSMiddleware(allowedOrigins),
		NewRateLimitMiddleware(ipRateLimiter, makeOnAuthLimitExceeded(ipRateLimiter)),
		NewRateLimitMiddleware(ipRateLimiterLong, makeOnAuthLimitExceeded(ipRateLimiterLong)),
	)

	stop := func() {
		stopIPLimiter()
		stopIPLimiterLong()
	}

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		sessionID, ok := bearerFromAuthorization(r)
		if !ok {
			http.Error(w, "Missing bearer token", http.StatusUnauthorized)
			return
		}

		ipHash := GetIP(r).Hash()

		view, err := refresh(ctx, sessionID, ipHash)
		switch {
		case errors.Is(err, domain.ErrAuthSessionRefreshTooSoon):
			// Not a 401: the session is fine, so re-auth is the wrong reaction.
			logging.FromContext(ctx).InfoContext(ctx, "Session refreshed too soon", "statusCode", http.StatusTooManyRequests)
			http.Error(w, "Session refreshed too recently", http.StatusTooManyRequests)
			return
		case errors.Is(err, domain.ErrAuthSessionNotFound),
			errors.Is(err, domain.ErrAuthSessionRevoked),
			errors.Is(err, domain.ErrAuthSessionRefreshExpired):
			http.Error(w, "Session is no longer refreshable", http.StatusUnauthorized)
			return
		case err != nil:
			logging.FromContext(ctx).ErrorContext(ctx, "Session refresh failed", "error", err.Error())
			reporting.Report(ctx, fmt.Errorf("session refresh: %w", err))
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

		writeAuthSessionResponse(ctx, w, view, nowFunc())
	}

	return middleware(handler), stop
}
