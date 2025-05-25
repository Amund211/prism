package ports

import (
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

func MakeGetSessionsHandler(
	getSessions app.GetSessions,
	allowedOrigins *DomainSuffixes,
	logger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
) http.HandlerFunc {
	ipRatelimiter := ratelimiting.NewRequestBasedRateLimiter(
		ratelimiting.NewTokenBucketRateLimiter(
			ratelimiting.RefillPerSecond(4),
			ratelimiting.BurstSize(80),
		),
		ratelimiting.IPKeyFunc,
	)
	userIDRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		// NOTE: Rate limiting based on user controlled value
		ratelimiting.NewTokenBucketRateLimiter(
			ratelimiting.RefillPerSecond(1),
			ratelimiting.BurstSize(20),
		),
		ratelimiting.UserIDKeyFunc,
	)

	makeOnLimitExceeded := func(rateLimiter ratelimiting.RequestRateLimiter) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			ctx := r.Context()
			logger := logging.FromContext(ctx)

			statusCode := http.StatusTooManyRequests

			logger.Info("Rate limit exceeded", "statusCode", statusCode, "reason", "ratelimit exceeded", "key", rateLimiter.KeyFor(r))

			http.Error(w, "Rate limit exceeded", statusCode)
		}
	}

	middleware := ComposeMiddlewares(
		logging.NewRequestLoggerMiddleware(logger),
		sentryMiddleware,
		reporting.NewAddMetaMiddleware("sessions"),
		BuildCORSMiddleware(allowedOrigins),
		NewRateLimitMiddleware(ipRatelimiter, makeOnLimitExceeded(ipRatelimiter)),
		NewRateLimitMiddleware(userIDRateLimiter, makeOnLimitExceeded(userIDRateLimiter)),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		userID := r.Header.Get("X-User-Id")
		if userID == "" {
			userID = "<missing>"
		}
		ctx = reporting.SetUserIDInContext(ctx, userID)
		ctx = logging.AddMetaToContext(ctx, slog.String("userId", userID))

		defer r.Body.Close()
		body, err := io.ReadAll(r.Body)
		if err != nil {
			reporting.Report(ctx, fmt.Errorf("failed to read request body: %w", err))
			http.Error(w, "Failed to read request body", http.StatusBadRequest)
			return
		}
		request := struct {
			UUID  string    `json:"uuid"`
			Start time.Time `json:"start"`
			End   time.Time `json:"end"`
		}{}
		err = json.Unmarshal(body, &request)
		if err != nil {
			reporting.Report(ctx, fmt.Errorf("failed to parse request body: %w", err))
			http.Error(w, "Failed to parse request body", http.StatusBadRequest)
			return
		}

		ctx = reporting.AddExtrasToContext(ctx, map[string]string{
			"start": request.Start.Format(time.RFC3339),
			"end":   request.End.Format(time.RFC3339),
		})

		uuid, err := strutils.NormalizeUUID(request.UUID)
		if err != nil {
			reporting.Report(ctx, fmt.Errorf("failed to normalize uuid: %w", err), map[string]string{
				"rawUUID": request.UUID,
			})
			http.Error(w, "invalid uuid", http.StatusBadRequest)
			return
		}

		ctx = reporting.AddExtrasToContext(ctx, map[string]string{
			"uuid": uuid,
		})
		ctx = logging.AddMetaToContext(ctx,
			slog.String("uuid", uuid),
			slog.String("start", request.Start.Format(time.RFC3339)),
			slog.String("end", request.End.Format(time.RFC3339)),
		)

		sessions, err := getSessions(ctx, uuid, request.Start, request.End)
		if err != nil {
			// NOTE: GetSessions implementations handle their own error reporting
			http.Error(w, "Failed to get sessions", http.StatusInternalServerError)
			return
		}

		marshalled, err := SessionsToRainbowSessionsData(sessions)
		if err != nil {
			reporting.Report(ctx, fmt.Errorf("failed to convert sessions to response: %w", err), map[string]string{
				"length": strconv.Itoa(len(sessions)),
			})
			http.Error(w, "Failed to marshal response", http.StatusInternalServerError)
			return
		}

		logger.Info("Returning sessions data")

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(marshalled)
	}

	return middleware(handler)
}
