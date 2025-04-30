package ports

import (
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
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
		NewRateLimitMiddleware(ipRatelimiter),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()
		body, err := io.ReadAll(r.Body)
		if err != nil {
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
			http.Error(w, "Failed to parse request body", http.StatusBadRequest)
			return
		}

		normalizedUUID, err := strutils.NormalizeUUID(request.UUID)
		if err != nil {
			http.Error(w, "invalid uuid", http.StatusBadRequest)
			return
		}

		history, err := getHistory(r.Context(), normalizedUUID, request.Start, request.End, request.Limit)
		if err != nil {
			http.Error(w, "Failed to get history", http.StatusInternalServerError)
			return
		}

		marshalled, err := HistoryToRainbowHistoryData(history)
		if err != nil {
			http.Error(w, "Failed to marshal response", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(marshalled)
	}

	return middleware(handler)
}
