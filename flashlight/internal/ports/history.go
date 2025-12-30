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

func MakeGetHistoryHandler(
	getHistory app.GetHistory,
	allowedOrigins *DomainSuffixes,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
) http.HandlerFunc {
	ipLimiter, _ := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(4),
		ratelimiting.BurstSize(240),
	)
	ipRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		ipLimiter,
		ratelimiting.IPKeyFunc,
	)
	userIDLimiter, _ := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(1),
		ratelimiting.BurstSize(60),
	)
	userIDRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		// NOTE: Rate limiting based on user controlled value
		userIDLimiter,
		ratelimiting.UserIDKeyFunc,
	)

	makeOnLimitExceeded := func(rateLimiter ratelimiting.RequestRateLimiter) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			ctx := r.Context()

			statusCode := http.StatusTooManyRequests

			logging.FromContext(ctx).InfoContext(ctx, "Rate limit exceeded", "statusCode", statusCode, "reason", "ratelimit exceeded", "key", rateLimiter.KeyFor(r))

			http.Error(w, "Rate limit exceeded", statusCode)
		}
	}

	middleware := ComposeMiddlewares(
		buildMetricsMiddleware("history"),
		logging.NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		reporting.NewAddMetaMiddleware("history"),
		BuildCORSMiddleware(allowedOrigins),
		NewRateLimitMiddleware(ipRateLimiter, makeOnLimitExceeded(ipRateLimiter)),
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
			Limit int       `json:"limit"`
		}{}
		err = json.Unmarshal(body, &request)
		if err != nil {
			reporting.Report(ctx, fmt.Errorf("failed to parse request body: %w", err), map[string]string{
				"body": string(body),
			})
			http.Error(w, "Failed to parse request body", http.StatusBadRequest)
			return
		}

		ctx = reporting.AddExtrasToContext(ctx, map[string]string{
			"start": request.Start.Format(time.RFC3339),
			"end":   request.End.Format(time.RFC3339),
			"limit": strconv.Itoa(request.Limit),
		})

		uuid, err := strutils.NormalizeUUID(request.UUID)
		if err != nil {
			reporting.Report(ctx, fmt.Errorf("failed to normalize UUID: %w", err), map[string]string{
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
			slog.Int("limit", request.Limit),
		)

		if request.Start.After(request.End) {
			reporting.Report(ctx, fmt.Errorf("start time is after end time"))
			http.Error(w, "Start time cannot be after end time", http.StatusBadRequest)
			return
		}

		if request.Limit < 2 || request.Limit > 100 {
			http.Error(w, "invalid limit", http.StatusBadRequest)
			return
		}

		history, err := getHistory(ctx, uuid, request.Start, request.End, request.Limit)
		if err != nil {
			// NOTE: GetHistory implementations handle their own error reporting
			http.Error(w, "Failed to get history", http.StatusInternalServerError)
			return
		}

		marshalled, err := HistoryToRainbowHistoryData(history)
		if err != nil {
			reporting.Report(ctx, fmt.Errorf("failed to convert history to response: %w", err), map[string]string{
				"length": strconv.Itoa(len(history)),
			})
			http.Error(w, "Failed to marshal response", http.StatusInternalServerError)
			return
		}

		logging.FromContext(ctx).InfoContext(ctx, "Returning history data")

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(marshalled)
	}

	return middleware(handler)
}
