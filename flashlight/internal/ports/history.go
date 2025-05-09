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
	logger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
) http.HandlerFunc {
	ipRatelimiter := ratelimiting.NewRequestBasedRateLimiter(
		ratelimiting.NewTokenBucketRateLimiter(
			ratelimiting.RefillPerSecond(1),
			ratelimiting.BurstSize(60),
		),
		ratelimiting.IPKeyFunc,
	)
	middleware := ComposeMiddlewares(
		logging.NewRequestLoggerMiddleware(logger),
		sentryMiddleware,
		BuildCORSMiddleware(allowedOrigins),
		NewRateLimitMiddleware(
			ipRatelimiter,
			func(w http.ResponseWriter, r *http.Request) {
				http.Error(w, "Rate limit exceeded", http.StatusTooManyRequests)
			},
		),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
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

		uuid, err := strutils.NormalizeUUID(request.UUID)
		if err != nil {
			reporting.Report(ctx, fmt.Errorf("failed to normalize UUID: %w", err), map[string]string{
				"uuid": request.UUID,
			})
			http.Error(w, "invalid uuid", http.StatusBadRequest)
			return
		}

		ctx = logging.AddMetaToContext(ctx,
			slog.String("uuid", uuid),
			slog.String("start", request.Start.Format(time.RFC3339)),
			slog.String("end", request.End.Format(time.RFC3339)),
			slog.Int("limit", request.Limit),
		)

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

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(marshalled)
	}

	return middleware(handler)
}
