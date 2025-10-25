package ports

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

func MakeGetAccountByUUIDHandler(
	getAccountByUUID app.GetAccountByUUID,
	allowedOrigins *DomainSuffixes,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
) http.HandlerFunc {
	ipLimiter, _ := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(8),
		ratelimiting.BurstSize(480),
	)
	ipRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		ipLimiter,
		ratelimiting.IPKeyFunc,
	)
	userIDLimiter, _ := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(2),
		ratelimiting.BurstSize(120),
	)
	userIDRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		// NOTE: Rate limiting based on user controlled value
		userIDLimiter,
		ratelimiting.UserIDKeyFunc,
	)

	makeOnLimitExceeded := func(rateLimiter ratelimiting.RequestRateLimiter) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusTooManyRequests)
			w.Write([]byte(`{"success":false,"cause":"rate limit exceeded"}`))
		}
	}

	middleware := ComposeMiddlewares(
		buildMetricsMiddleware(),
		logging.NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		reporting.NewAddMetaMiddleware("get_account_by_uuid"),
		BuildCORSMiddleware(allowedOrigins),
		NewRateLimitMiddleware(ipRateLimiter, makeOnLimitExceeded(ipRateLimiter)),
		NewRateLimitMiddleware(userIDRateLimiter, makeOnLimitExceeded(userIDRateLimiter)),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		rawUUID := r.PathValue("uuid")

		handleError := func(ctx context.Context, cause string, statusCode int) {
			response, err := makeErrorAccountResponseForUUID(ctx, rawUUID, cause)
			if err != nil {
				reporting.Report(ctx, fmt.Errorf("failed to marshal error response: %w", err))
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusInternalServerError)
				w.Write([]byte(`{"success":false,"cause":"internal server error"}`))
				return
			}

			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(statusCode)
			w.Write(response)
		}

		userID := r.Header.Get("X-User-Id")
		ctx = reporting.SetUserIDInContext(ctx, userID)
		if userID == "" {
			userID = "<missing>"
		}

		uuid, err := strutils.NormalizeUUID(rawUUID)
		if err != nil {
			handleError(ctx, "invalid uuid", http.StatusBadRequest)
			return
		}

		ctx = logging.AddMetaToContext(ctx,
			slog.String("userId", userID),
			slog.String("uuid", uuid),
		)
		ctx = reporting.AddExtrasToContext(ctx,
			map[string]string{
				"uuid": uuid,
			},
		)

		account, err := getAccountByUUID(ctx, uuid)
		if errors.Is(err, domain.ErrUsernameNotFound) {
			handleError(ctx, "not found", http.StatusNotFound)
			return
		} else if errors.Is(err, domain.ErrTemporarilyUnavailable) {
			handleError(ctx, "temporarily unavailable", http.StatusServiceUnavailable)
			return
		}

		if err != nil {
			// NOTE: GetAccountByUUID implementations handle their own error reporting
			handleError(ctx, "internal server error", http.StatusInternalServerError)
			return
		}

		ctx = reporting.AddExtrasToContext(ctx,
			map[string]string{
				"username": account.Username,
			},
		)
		ctx = logging.AddMetaToContext(ctx, slog.String("username", account.Username))

		response, err := makeSuccessAccountResponse(ctx, account)
		if err != nil {
			reporting.Report(ctx, fmt.Errorf("failed to create success response: %w", err))
			handleError(ctx, "internal server error", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(response)
	}

	return middleware(handler)
}

func makeErrorAccountResponseForUUID(ctx context.Context, uuid string, cause string) ([]byte, error) {
	return makeAccountResponse(ctx, "", false, uuid, cause)
}
