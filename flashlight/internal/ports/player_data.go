package ports

import (
	"context"
	"encoding/json"
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

func MakeGetPlayerDataHandler(
	getAndPersistPlayerWithCache app.GetAndPersistPlayerWithCache,
	logger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
) http.HandlerFunc {
	ipRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		ratelimiting.NewTokenBucketRateLimiter(
			ratelimiting.RefillPerSecond(8),
			ratelimiting.BurstSize(480),
		),
		ratelimiting.IPKeyFunc,
	)
	userIdRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		// NOTE: Rate limiting based on user controlled value
		ratelimiting.NewTokenBucketRateLimiter(
			ratelimiting.RefillPerSecond(2),
			ratelimiting.BurstSize(120),
		),
		ratelimiting.UserIdKeyFunc,
	)

	makeOnLimitExceeded := func(rateLimiter ratelimiting.RequestRateLimiter) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			ctx := r.Context()
			logger := logging.FromContext(ctx)

			statusCode := http.StatusTooManyRequests

			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(statusCode)
			w.Write([]byte(`{"success":false,"cause":"Rate limit exceeded"}`))

			logger.Info("Returning response", "statusCode", statusCode, "reason", "ratelimit exceeded", "key", rateLimiter.KeyFor(r))
		}
	}

	middleware := ComposeMiddlewares(
		logging.NewRequestLoggerMiddleware(logger),
		sentryMiddleware,
		NewRateLimitMiddleware(ipRateLimiter, makeOnLimitExceeded(ipRateLimiter)),
		NewRateLimitMiddleware(userIdRateLimiter, makeOnLimitExceeded(userIdRateLimiter)),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		logger := logging.FromContext(ctx)
		rawUUID := r.URL.Query().Get("uuid")

		uuid, err := strutils.NormalizeUUID(rawUUID)
		if err != nil {
			statusCode := http.StatusBadRequest

			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(statusCode)
			w.Write([]byte(`{"success":false,"cause":"Invalid UUID"}`))

			logger.Info("Returning response", "statusCode", statusCode, "reason", "invalid uuid")
			return
		}

		player, err := getAndPersistPlayerWithCache(ctx, uuid)
		if errors.Is(err, domain.ErrPlayerNotFound) {
			hypixelAPIResponseData, err := PlayerToPrismPlayerDataResponseData(nil)
			if err != nil {
				logger.Error("Failed to convert player to hypixel API response", "error", err)
				err = fmt.Errorf("failed to convert player to hypixel API response: %w", err)
				reporting.Report(ctx, err)
				statusCode := writeHypixelStyleErrorResponse(ctx, w, err)
				logger.Info("Returning response", "statusCode", statusCode, "reason", "error")
				return
			}

			statusCode := 404
			logger.Info("Returning response", "statusCode", statusCode, "reason", "success")
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(statusCode)
			w.Write(hypixelAPIResponseData)
			return
		}

		if err != nil {
			// NOTE: GetAndPersistPlayerWithCache implementations handle their own error reporting
			logger.Error("Error getting player data", "error", err)
			statusCode := writeHypixelStyleErrorResponse(ctx, w, err)
			logger.Info("Returning response", "statusCode", statusCode, "reason", "error")
			return
		}

		hypixelAPIResponseData, err := PlayerToPrismPlayerDataResponseData(player)
		if err != nil {
			logger.Error("Failed to convert player to hypixel API response", "error", err)

			err = fmt.Errorf("failed to convert player to hypixel API response: %w", err)
			reporting.Report(ctx, err)

			statusCode := writeHypixelStyleErrorResponse(ctx, w, err)
			logger.Info("Returning response", "statusCode", statusCode, "reason", "error")
			return
		}

		logger.Info("Got minified player data", "contentLength", len(hypixelAPIResponseData), "statusCode", 200)

		statusCode := 200
		logger.Info("Returning response", "statusCode", statusCode, "reason", "success")
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(statusCode)
		w.Write(hypixelAPIResponseData)
	}

	return middleware(handler)
}

func writeHypixelStyleErrorResponse(ctx context.Context, w http.ResponseWriter, responseError error) int {
	w.Header().Set("Content-Type", "application/json")

	errorResponse := HypixelAPIErrorResponse{
		Success: false,
		Cause:   responseError.Error(),
	}
	errorBytes, err := json.Marshal(errorResponse)
	if err != nil {
		logging.FromContext(ctx).Error("Failed to marshal error response", "error", err)
		reporting.Report(ctx, fmt.Errorf("failed to marshal error response: %w", err), map[string]string{
			"responseError": responseError.Error(),
		})
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte(`{"success":false,"cause":"Internal server error (flashlight)"}`))
		return http.StatusInternalServerError
	}

	// Unknown error: default to 500
	statusCode := http.StatusInternalServerError

	if errors.Is(responseError, domain.ErrTemporarilyUnavailable) {
		// TODO: Use a more descriptive status code when most prism clients support it
		statusCode = http.StatusGatewayTimeout
	}

	w.WriteHeader(statusCode)
	// TODO: Sanitize the errors before sending them to the client
	w.Write(errorBytes)

	return statusCode
}
