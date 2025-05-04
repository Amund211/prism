package ports

import (
	"fmt"
	"log/slog"
	"net/http"

	"github.com/Amund211/flashlight/internal/app"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
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

	middleware := ComposeMiddlewares(
		logging.NewRequestLoggerMiddleware(logger),
		sentryMiddleware,
		NewRateLimitMiddleware(ipRateLimiter),
		NewRateLimitMiddleware(userIdRateLimiter),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		logger := logging.FromContext(ctx)
		uuid := r.URL.Query().Get("uuid")

		player, err := getAndPersistPlayerWithCache(r.Context(), uuid)

		if err != nil {
			logger.Error("Error getting player data", "error", err)
			statusCode := writeHypixelStyleErrorResponse(r.Context(), w, err)
			logger.Info("Returning response", "statusCode", statusCode, "reason", "error")
			return
		}

		hypixelAPIResponseData, err := PlayerToPrismPlayerDataResponseData(player)
		if err != nil {
			logger.Error("Failed to convert player to hypixel API response", "error", err)

			err = fmt.Errorf("%w: failed to convert player to hypixel API response: %w", e.APIServerError, err)
			reporting.Report(ctx, err)

			statusCode := writeHypixelStyleErrorResponse(r.Context(), w, err)
			logger.Info("Returning response", "statusCode", statusCode, "reason", "error")
			return
		}

		logger.Info("Got minified player data", "contentLength", len(hypixelAPIResponseData), "statusCode", 200)

		statusCode := 200
		if player == nil {
			statusCode = 404
		}
		logger.Info("Returning response", "statusCode", statusCode, "reason", "success")
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(statusCode)
		w.Write(hypixelAPIResponseData)
	}

	return middleware(handler)
}
