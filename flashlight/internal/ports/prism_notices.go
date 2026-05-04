package ports

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"slices"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/version"
)

type severity string

const (
	noticeSeverityInfo     severity = "info"
	noticeSeverityUpdate   severity = "update"
	noticeSeverityWarning  severity = "warning"
	noticeSeverityCritical severity = "critical"
)

// latestPrism is the most recent released prism version. Bump this when
// cutting a new prism release; clients running an older version will be told
// (via the prism-notices endpoint) that an update is available.
var latestPrism = version.MustParse("v1.11.0")

// firstPrismVersionWithoutLocalChecker is the first prism release that does
// not include the in-process GitHub update checker — those clients rely on
// flashlight to surface update notices. Older clients still poll GitHub
// themselves, so flashlight must not duplicate the notice for them.
var firstPrismVersionWithoutLocalChecker = version.MustParse("v1.12.0")

// latestPrismReleaseURL is the link clients are sent to when an update notice
// is shown.
const latestPrismReleaseURL = "https://github.com/Amund211/prism/releases/latest/"

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

		includeVersionUpdates := r.URL.Query().Get("includeVersionUpdates")

		ctx = logging.AddMetaToContext(ctx,
			slog.String("prismVersion", prismVersion),
			slog.String("includeVersionUpdates", includeVersionUpdates),
		)
		ctx = reporting.AddExtrasToContext(ctx,
			map[string]string{
				"prismVersion":          prismVersion,
				"includeVersionUpdates": includeVersionUpdates,
			},
		)

		notices, err := noticesForCall(ctx, userIDType(userID), prismVersionType(prismVersion), includeVersionUpdates, time.Now())
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
	"b3c71ddfb808414d80e932110dae5716",
	"9c90ae7b927347a787ddb9c9e85cca16",
	"a3ec8094a2bb427f81c11faadb33c2ba",
	"ea2aa5221a614dc1a502f01e33f4ceaa",
	"47e7859bb33246ef8494fb81a9ac4e01",
	"426d836cdc7740bd9ff887d1d8a358f3",

	"3eedaf7ed5964d8981835b8f0de2c9d4",
	"bb683d98dc634a5783be9a4895ab75af",
	"a55dfa5ddaa7426b87f2a5dbc3ad5254",
}

func versionUpdateNotices(ctx context.Context, prismVersion prismVersionType, includeVersionUpdates string) []prismNotice {
	var includePatchUpdates bool
	switch includeVersionUpdates {
	case "none":
		return nil
	case "minor":
		includePatchUpdates = false
	case "all":
		includePatchUpdates = true
	default:
		logging.FromContext(ctx).WarnContext(ctx, "Unrecognized includeVersionUpdates value, defaulting to all", "includeVersionUpdates", includeVersionUpdates)
		includePatchUpdates = true
	}

	current, err := version.Parse(string(prismVersion))
	if err != nil {
		logging.FromContext(ctx).WarnContext(ctx, "Failed to parse prism version", "error", err, "prismVersion", string(prismVersion))
		return nil
	}

	if !current.IsAtLeast(firstPrismVersionWithoutLocalChecker) {
		// This client still has its own GitHub update checker.
		return nil
	}

	if !current.UpdateAvailable(latestPrism, !includePatchUpdates) {
		return nil
	}

	logging.FromContext(ctx).InfoContext(ctx, "Adding prism update notice", "prismVersion", string(prismVersion), "latest", latestPrism)
	duration := 60.0
	return []prismNotice{{
		Message:         "New update available! Click here to download.",
		URL:             latestPrismReleaseURL,
		Severity:        noticeSeverityUpdate,
		DurationSeconds: &duration,
	}}
}

func noticesForCall(ctx context.Context, userID userIDType, prismVersion prismVersionType, includeVersionUpdates string, now time.Time) ([]prismNotice, error) {
	notices := []prismNotice{}

	now = now.UTC()

	notices = append(notices, versionUpdateNotices(ctx, prismVersion, includeVersionUpdates)...)

	if slices.Contains(unicodeReplacementCharacterUsers, string(userID)) {
		// These users sometimes include a unicode replacement character at the end of
		// usernames sent to the account endpoint, causing issues.
		// https://prism-overlay.sentry.io/issues/7078120764/?project=4506886744768512
		duration := 120.0
		logging.FromContext(ctx).InfoContext(ctx, "Adding critical notice for user with known unicode replacement character issue", "userID", userID)
		notices = append(notices, prismNotice{
			Message:         "We've detected a potential issue with your Prism client.\nPlease click here to create a ticket in the discord server",
			URL:             "https://discord.gg/NGpRrdh6Fx",
			Severity:        noticeSeverityWarning,
			DurationSeconds: &duration,
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
