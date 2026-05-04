package ports

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
)

// Wire-format types for the prism-notices endpoint. The HTTP contract is
// the handler's responsibility, so the JSON-tagged structs live here and
// the handler converts from app-layer types before serializing.

type severity string

const (
	noticeSeverityInfo     severity = "info"
	noticeSeverityUpdate   severity = "update"
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

func severityFromApp(s app.Severity) (severity, error) {
	switch s {
	case app.SeverityInfo:
		return noticeSeverityInfo, nil
	case app.SeverityUpdate:
		return noticeSeverityUpdate, nil
	case app.SeverityWarning:
		return noticeSeverityWarning, nil
	case app.SeverityCritical:
		return noticeSeverityCritical, nil
	default:
		return "", fmt.Errorf("unknown app.Severity %q", string(s))
	}
}

func MakePrismNoticesHandler(
	getPrismNotices app.GetPrismNotices,
	registerUserVisit app.RegisterUserVisit,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
	blocklistConfig BlocklistConfig,
) http.HandlerFunc {
	ipLimiter, _ := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(8),
		ratelimiting.BurstSize(480),
	)
	ipRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		ipLimiter,
		IPHashKeyFunc,
	)
	userIDLimiter, _ := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(2),
		ratelimiting.BurstSize(120),
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
		buildMetricsMiddleware("prism-notices"),
		NewReportingMetaMiddleware("prism-notices"),
		NewRateLimitMiddleware(ipRateLimiter, makeOnLimitExceeded(ipRateLimiter)),
		NewRateLimitMiddleware(userIDRateLimiter, makeOnLimitExceeded(userIDRateLimiter)),
		BuildRegisterUserVisitMiddleware(registerUserVisit),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		userID := GetUserID(r)

		prismVersion := r.Header.Get("X-Prism-Version")
		if prismVersion == "" {
			prismVersion = "<missing>"
		}

		rawSelection := r.URL.Query().Get("includeVersionUpdates")

		ctx = logging.AddMetaToContext(ctx,
			slog.String("prismVersion", prismVersion),
			slog.String("includeVersionUpdates", rawSelection),
		)
		ctx = reporting.AddExtrasToContext(ctx,
			map[string]string{
				"prismVersion":          prismVersion,
				"includeVersionUpdates": rawSelection,
			},
		)

		var updateSelection app.UpdateSelection
		switch rawSelection {
		case "none":
			updateSelection = app.UpdateSelectionNone
		case "minor":
			updateSelection = app.UpdateSelectionMinor
		case "all":
			updateSelection = app.UpdateSelectionAll
		default:
			logging.FromContext(ctx).WarnContext(ctx, "Unrecognized includeVersionUpdates value, defaulting to all", "includeVersionUpdates", rawSelection)
			updateSelection = app.UpdateSelectionAll
		}

		appNotices := getPrismNotices(ctx, string(userID), prismVersion, updateSelection)
		wireNotices := make([]prismNotice, 0, len(appNotices))
		for _, n := range appNotices {
			wireSeverity, err := severityFromApp(n.Severity)
			if err != nil {
				logging.FromContext(ctx).ErrorContext(ctx, "Failed to convert severity for wire format", "error", err)
				reporting.Report(ctx, fmt.Errorf("failed to convert severity: %w", err))
				http.Error(w, "Internal server error", http.StatusInternalServerError)
				return
			}
			wireNotices = append(wireNotices, prismNotice{
				Message:         n.Message,
				URL:             n.URL,
				Severity:        wireSeverity,
				DurationSeconds: n.DurationSeconds,
			})
		}

		responseData, err := json.Marshal(noticesResponse{Notices: wireNotices})
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
