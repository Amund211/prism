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
)

type tagsResponseObject struct {
	UUID string       `json:"uuid"`
	Tags tagsResponse `json:"tags"`
}

const (
	tagSeverityNone   = "none"
	tagSeverityMedium = "medium"
	tagSeverityHigh   = "high"
)

type tagsResponse struct {
	Cheating string `json:"cheating"`
	Sniping  string `json:"sniping"`
}

func MakeGetTagsHandler(
	getTags app.GetTags,
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

			logging.FromContext(ctx).Info("Rate limit exceeded", "statusCode", statusCode, "reason", "ratelimit exceeded", "key", rateLimiter.KeyFor(r))

			http.Error(w, "Rate limit exceeded", statusCode)
		}
	}

	middleware := ComposeMiddlewares(
		buildMetricsMiddleware("tags"),
		logging.NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		reporting.NewAddMetaMiddleware("tags"),
		NewRateLimitMiddleware(ipRateLimiter, makeOnLimitExceeded(ipRateLimiter)),
		NewRateLimitMiddleware(userIDRateLimiter, makeOnLimitExceeded(userIDRateLimiter)),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		rawUUID := r.PathValue("uuid")

		userID := r.Header.Get("X-User-Id")
		if userID == "" {
			userID = "<missing>"
		}
		ctx = reporting.SetUserIDInContext(ctx, userID)
		ctx = logging.AddMetaToContext(ctx,
			slog.String("userId", userID),
			slog.String("rawUUID", rawUUID),
		)
		ctx = reporting.AddExtrasToContext(ctx,
			map[string]string{
				"rawUUID": rawUUID,
			},
		)

		uuid, err := strutils.NormalizeUUID(rawUUID)
		if err != nil {
			statusCode := http.StatusBadRequest
			logging.FromContext(ctx).Info("Invalid uuid. Returning error", "statusCode", statusCode, "reason", "invalid uuid")
			http.Error(w, "Invalid uuid", statusCode)
			return
		}

		ctx = reporting.AddExtrasToContext(ctx,
			map[string]string{
				"uuid": uuid,
			},
		)
		ctx = logging.AddMetaToContext(ctx, slog.String("uuid", uuid))

		tags, err := getTags(ctx, uuid, nil)
		if errors.Is(err, domain.ErrTemporarilyUnavailable) {
			logging.FromContext(ctx).Error("Tags temporarily unavailable", "error", err)
			http.Error(w, "Temporarily unavailable", http.StatusServiceUnavailable)
			return
		} else if err != nil {
			logging.FromContext(ctx).Error("Error getting tags", "error", err)
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

		responseData, err := tagsToResponse(ctx, uuid, tags)
		if err != nil {
			logging.FromContext(ctx).Error("Failed to convert tags to response", "error", err)

			err = fmt.Errorf("failed to convert tags to response: %w", err)
			reporting.Report(ctx, err)

			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		if _, err = w.Write(responseData); err != nil {
			logging.FromContext(ctx).Error("Failed to write response", "error", err)
			reporting.Report(ctx, fmt.Errorf("failed to write tags response: %w", err))

			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

	}

	return middleware(handler)
}

func tagSeverityToString(severity domain.TagSeverity) (string, error) {
	switch severity {
	case domain.TagSeverityNone:
		return tagSeverityNone, nil
	case domain.TagSeverityMedium:
		return tagSeverityMedium, nil
	case domain.TagSeverityHigh:
		return tagSeverityHigh, nil
	}
	return tagSeverityNone, fmt.Errorf("unknown tag severity: %v", severity)
}

func tagsToResponse(ctx context.Context, uuid string, tags domain.Tags) ([]byte, error) {
	cheatingStr, err := tagSeverityToString(tags.Cheating)
	if err != nil {
		return nil, fmt.Errorf("failed to convert cheating tag severity to string: %w", err)
	}
	snipingStr, err := tagSeverityToString(tags.Sniping)
	if err != nil {
		return nil, fmt.Errorf("failed to convert sniping tag severity to string: %w", err)
	}

	response := tagsResponseObject{
		UUID: uuid,
		Tags: tagsResponse{
			Cheating: cheatingStr,
			Sniping:  snipingStr,
		},
	}

	data, err := json.Marshal(response)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal tags response: %w", err)
	}

	return data, nil
}
