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
	"go.opentelemetry.io/otel"
)

func MakeGetPlayerDataHandler(
	getAndPersistPlayerWithCache app.GetAndPersistPlayerWithCache,
	getTags app.GetTags,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
) http.HandlerFunc {
	tracer := otel.Tracer("flashlight/ports/player_data_v1")

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
		buildMetricsMiddleware("playerdata"),
		logging.NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		reporting.NewAddMetaMiddleware("playerdata"),
		NewRateLimitMiddleware(ipRateLimiter, makeOnLimitExceeded(ipRateLimiter)),
		NewRateLimitMiddleware(userIDRateLimiter, makeOnLimitExceeded(userIDRateLimiter)),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		ctx, span := tracer.Start(ctx, "ports.GetPlayerDataHandler")
		defer span.End()

		rawUUID := r.URL.Query().Get("uuid")
		userID := r.Header.Get("X-User-Id")
		ctx = reporting.SetUserIDInContext(ctx, userID)
		if userID == "" {
			userID = "<missing>"
		}
		ctx = logging.AddMetaToContext(ctx,
			slog.String("userId", userID),
			slog.String("uuid", rawUUID),
		)
		logger := logging.FromContext(ctx)

		ctx = reporting.AddExtrasToContext(ctx,
			map[string]string{
				"rawUUID": rawUUID,
			},
		)

		uuid, err := strutils.NormalizeUUID(rawUUID)
		if err != nil {
			statusCode := http.StatusBadRequest

			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(statusCode)
			w.Write([]byte(`{"success":false,"cause":"Invalid UUID"}`))

			logger.Info("Returning response", "statusCode", statusCode, "reason", "invalid uuid")
			return
		}

		ctx = reporting.AddExtrasToContext(ctx,
			map[string]string{
				"uuid": uuid,
			},
		)

		go getTags(ctx, uuid, nil)

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
