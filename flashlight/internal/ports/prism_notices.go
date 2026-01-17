package ports

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"slices"
	"time"

	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
)

type severity string

const (
	noticeSeverityInfo     severity = "info"
	noticeSeverityWarning  severity = "warning"
	noticeSeverityCritical severity = "critical"
)

type prismNotice struct {
	Message         string   `json:"message"`
	URL             string   `json:"url,omitempty"`
	Severity        severity `json:"severity"`
	DurationSeconds *float64 `json:"duration_seconds,omitempty"`
}

type noticesResponse struct {
	Notices []prismNotice `json:"notices"`
}

type userIDType string
type prismVersionType string

func MakePrismNoticesHandler(
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
			ctx := r.Context()

			statusCode := http.StatusTooManyRequests

			logging.FromContext(ctx).InfoContext(ctx, "Rate limit exceeded", "statusCode", statusCode, "reason", "ratelimit exceeded", "key", rateLimiter.KeyFor(r))

			http.Error(w, "Rate limit exceeded", statusCode)
		}
	}

	middleware := ComposeMiddlewares(
		buildMetricsMiddleware("prism-notices"),
		logging.NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		reporting.NewAddMetaMiddleware("prism-notices"),
		NewRateLimitMiddleware(ipRateLimiter, makeOnLimitExceeded(ipRateLimiter)),
		NewRateLimitMiddleware(userIDRateLimiter, makeOnLimitExceeded(userIDRateLimiter)),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		userID := r.Header.Get("X-User-Id")
		if userID == "" {
			userID = "<missing>"
		}

		prismVersion := r.Header.Get("X-Prism-Version")
		if prismVersion == "" {
			prismVersion = "<missing>"
		}

		ctx = reporting.SetUserIDInContext(ctx, userID)
		ctx = logging.AddMetaToContext(ctx,
			slog.String("userId", userID),
			slog.String("prismVersion", prismVersion),
		)
		ctx = reporting.AddExtrasToContext(ctx,
			map[string]string{
				"prismVersion": prismVersion,
			},
		)

		notices, err := noticesForCall(ctx, userIDType(userID), prismVersionType(prismVersion), time.Now())
		if err != nil {
			logging.FromContext(ctx).ErrorContext(ctx, "Failed to get notices for call", "error", err)

			err = fmt.Errorf("failed to get notices for call: %w", err)
			reporting.Report(ctx, err)

			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

		responseData, err := json.Marshal(noticesResponse{Notices: notices})
		if err != nil {
			logging.FromContext(ctx).ErrorContext(ctx, "Failed to marshal notices", "error", err)
			reporting.Report(ctx, fmt.Errorf("failed to marshal notices: %w", err))
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		if _, err := w.Write(responseData); err != nil {
			logging.FromContext(ctx).ErrorContext(ctx, "Failed to write response", "error", err)
			reporting.Report(ctx, fmt.Errorf("failed to write notices response: %w", err))

			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

	}

	return middleware(handler)
}

var unicodeReplacementCharacterUsers = []string{
	"b1b6ead3b357467298c0a186a891940f",
	"e104fb8b4b8a4a40ba70334e8239c0e1",
	"3eedaf7ed5964d8981835b8f0de2c9d4",
	"bb683d98dc634a5783be9a4895ab75af",
	"a55dfa5ddaa7426b87f2a5dbc3ad5254",
}

func noticesForCall(ctx context.Context, userID userIDType, prismVersion prismVersionType, now time.Time) ([]prismNotice, error) {
	notices := []prismNotice{}

	now = now.UTC()

	if slices.Contains(unicodeReplacementCharacterUsers, string(userID)) {
		// These users sometimes include a unicode replacement character at the end of
		// usernames sent to the account endpoint, causing issues.
		// https://prism-overlay.sentry.io/issues/7078120764/?project=4506886744768512
		logging.FromContext(ctx).InfoContext(ctx, "Adding critical notice for user with known unicode replacement character issue", "userID", userID)
		notices = append(notices, prismNotice{
			Message:  "We've detected a potential issue with your Prism client.\nPlease click here to create a ticket in the discord server",
			URL:      "https://discord.gg/NGpRrdh6Fx",
			Severity: noticeSeverityWarning,
		})
	}

	if now.Month() == time.December || now.Month() == time.January {
		duration := 60.0
		year := now.Year()
		if now.Month() == time.January {
			year = year - 1
		}
		notices = append(notices, prismNotice{
			Message:         fmt.Sprintf("Click here to view your Prism Wrapped %d", year),
			URL:             "https://prismoverlay.com/wrapped",
			Severity:        noticeSeverityInfo,
			DurationSeconds: &duration,
		})
	}

	return notices, nil
}
