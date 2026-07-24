package ports

import (
	"encoding/json"
	"errors"
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
	getPlayerPITs app.GetPlayerPITs,
	computeSessions app.ComputeSessions,
	registerUserVisit app.RegisterUserVisit,
	allowedOrigins *DomainSuffixes,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
	bearerAuthMiddleware func(http.HandlerFunc) http.HandlerFunc,
	blocklistConfig BlocklistConfig,
) (http.HandlerFunc, func()) {
	ipLimiter, stopIPLimiter := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(4),
		ratelimiting.BurstSize(80),
	)
	ipRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		ipLimiter,
		IPHashKeyFunc,
	)
	userIDLimiter, stopUserIDLimiter := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(1),
		ratelimiting.BurstSize(20),
	)
	userIDRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		// NOTE: Rate limiting based on user controlled value
		userIDLimiter,
		UserIDKeyFunc,
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
		NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		BuildBlocklistMiddleware(blocklistConfig),
		buildMetricsMiddleware("sessions"),
		NewReportingMetaMiddleware("sessions"),
		BuildCORSMiddleware(allowedOrigins),
		NewRateLimitMiddleware(ipRateLimiter, makeOnLimitExceeded(ipRateLimiter)),
		NewRateLimitMiddleware(userIDRateLimiter, makeOnLimitExceeded(userIDRateLimiter)),
		// Behind the rate limiters: validating a bearer opens a
		// SELECT-FOR-UPDATE transaction on the session row, and failed
		// validations aren't cached, so a bad token in front of them would be
		// an unthrottled DB write. Still inside CORS so the 401 keeps its
		// Access-Control-Allow-Origin header.
		bearerAuthMiddleware,
		BuildRegisterUserVisitMiddleware(registerUserVisit),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		defer r.Body.Close()
		body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 4<<10))
		if err != nil {
			var maxBytesErr *http.MaxBytesError
			if errors.As(err, &maxBytesErr) {
				http.Error(w, "Request body too large", http.StatusRequestEntityTooLarge)
				return
			}
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
			logging.FromContext(ctx).WarnContext(ctx, "Failed to parse request body", "error", err)
			http.Error(w, "Failed to parse request body", http.StatusBadRequest)
			return
		}

		ctx = reporting.AddExtrasToContext(ctx, map[string]string{
			"start": request.Start.Format(time.RFC3339),
			"end":   request.End.Format(time.RFC3339),
		})

		uuid, err := strutils.NormalizeUUID(request.UUID)
		if err != nil {
			logging.FromContext(ctx).WarnContext(ctx, "Failed to normalize uuid", "error", err, "rawUUID", request.UUID)
			http.Error(w, "invalid uuid", http.StatusBadRequest)
			return
		}

		logging.FromContext(ctx).InfoContext(ctx, "Handling sessions request",
			slog.String("uuid", uuid),
			slog.String("start", request.Start.Format(time.RFC3339)),
			slog.String("end", request.End.Format(time.RFC3339)),
		)

		ctx = reporting.AddExtrasToContext(ctx, map[string]string{
			"uuid": uuid,
		})
		ctx = logging.AddMetaToContext(ctx,
			slog.String("uuid", uuid),
			slog.String("start", request.Start.Format(time.RFC3339)),
			slog.String("end", request.End.Format(time.RFC3339)),
		)

		if request.Start.After(request.End) {
			logging.FromContext(ctx).WarnContext(ctx, "Start time is after end time")
			http.Error(w, "Start time cannot be after end time", http.StatusBadRequest)
			return
		}

		// Validate interval length
		timespan := request.End.Sub(request.Start)
		// TODO: Revert to max 60 days (when no longer using this for "wrapped" page on website)
		if timespan >= 400*24*time.Hour {
			http.Error(w, "Time interval is too long", http.StatusBadRequest)
			return
		}

		// Add some padding on both sides to try to complete sessions that cross the interval borders
		filterStart := request.Start.Add(-24 * time.Hour)
		filterEnd := request.End.Add(24 * time.Hour)

		stats, err := getPlayerPITs(ctx, uuid, filterStart, filterEnd)
		if err != nil {
			// NOTE: GetPlayerPITs implementations handle their own error reporting
			http.Error(w, "Failed to get player data", http.StatusInternalServerError)
			return
		}

		sessions := computeSessions(ctx, stats, request.Start, request.End)

		marshalled, err := SessionsToRainbowSessionsData(sessions)
		if err != nil {
			reporting.Report(ctx, fmt.Errorf("failed to convert sessions to response: %w", err), map[string]string{
				"length": strconv.Itoa(len(sessions)),
			})
			http.Error(w, "Failed to marshal response", http.StatusInternalServerError)
			return
		}

		logging.FromContext(ctx).InfoContext(ctx, "Returning sessions data")

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(marshalled)
	}

	stop := func() {
		stopIPLimiter()
		stopUserIDLimiter()
	}

	return middleware(handler), stop
}
