package ports

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strconv"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

type prestigeResponse struct {
	Success   bool                  `json:"success"`
	Prestiges []prestigeAchievement `json:"prestiges"`
	Cause     string                `json:"cause,omitempty"`
}

type prestigeAchievement struct {
	Stars     int                       `json:"stars"`
	FirstSeen *prestigeAchievementStats `json:"first_seen,omitempty"`
}

type prestigeAchievementStats struct {
	Experience int64     `json:"experience"`
	Stars      int       `json:"stars"`
	QueriedAt  time.Time `json:"queried_at"`
}

func MakeGetPrestigesHandler(
	findMilestoneAchievements app.FindMilestoneAchievements,
	allowedOrigins *DomainSuffixes,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
) http.HandlerFunc {
	ipRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		ratelimiting.NewTokenBucketRateLimiter(
			ratelimiting.RefillPerSecond(4),
			ratelimiting.BurstSize(240),
		),
		ratelimiting.IPKeyFunc,
	)
	userIDRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		ratelimiting.NewTokenBucketRateLimiter(
			ratelimiting.RefillPerSecond(1),
			ratelimiting.BurstSize(60),
		),
		ratelimiting.UserIDKeyFunc,
	)

	makeOnLimitExceeded := func(rateLimiter ratelimiting.RequestRateLimiter) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusTooManyRequests)
			w.Write([]byte(`{"success":false,"cause":"Rate limit exceeded"}`))
		}
	}

	middleware := ComposeMiddlewares(
		logging.NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		reporting.NewAddMetaMiddleware("prestiges"),
		BuildCORSMiddleware(allowedOrigins),
		NewRateLimitMiddleware(ipRateLimiter, makeOnLimitExceeded(ipRateLimiter)),
		NewRateLimitMiddleware(userIDRateLimiter, makeOnLimitExceeded(userIDRateLimiter)),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		rawUUID := r.PathValue("uuid")
		userID := r.Header.Get("X-User-Id")
		ctx = reporting.SetUserIDInContext(ctx, userID)
		if userID == "" {
			userID = "<missing>"
		}
		ctx = logging.AddMetaToContext(ctx,
			slog.String("userId", userID),
			slog.String("uuid", rawUUID),
		)

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
			return
		}

		ctx = reporting.AddExtrasToContext(ctx, map[string]string{
			"uuid": uuid,
		})
		ctx = logging.AddMetaToContext(ctx, slog.String("normalizedUUID", uuid))

		// Generate hardcoded milestones: multiples of 100 up to 10,000
		milestones := make([]int64, 0, 100)
		for i := 100; i <= 10000; i += 100 {
			milestones = append(milestones, int64(i))
		}

		achievements, err := findMilestoneAchievements(ctx, uuid, domain.GamemodeOverall, domain.StatStars, milestones)
		if err != nil {
			// NOTE: FindMilestoneAchievements implementations handle their own error reporting
			statusCode := http.StatusInternalServerError
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(statusCode)
			w.Write([]byte(`{"success":false,"cause":"Failed to get prestiges"}`))
			return
		}

		// Convert achievements to response format
		responseAchievements := make([]prestigeAchievement, 0, len(achievements))
		for _, achievement := range achievements {
			responseAchievements = append(responseAchievements, prestigeAchievement{
				Stars: int(achievement.Milestone),
				FirstSeen: func() *prestigeAchievementStats {
					if achievement.After == nil {
						return nil
					}
					return &prestigeAchievementStats{
						Experience: int64(achievement.After.Player.Experience),
						Stars:      int(achievement.After.Value),
						QueriedAt:  achievement.After.Player.QueriedAt,
					}
				}(),
			})
		}

		response := prestigeResponse{
			Success:   true,
			Prestiges: responseAchievements,
		}

		marshalled, err := json.Marshal(response)
		if err != nil {
			reporting.Report(ctx, fmt.Errorf("failed to marshal prestiges response: %w", err), map[string]string{
				"length": strconv.Itoa(len(responseAchievements)),
			})
			statusCode := http.StatusInternalServerError
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(statusCode)
			w.Write([]byte(`{"success":false,"cause":"Failed to marshal response"}`))
			return
		}

		logging.FromContext(ctx).Info("Returning prestiges data", "achievements", len(achievements))

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(marshalled)
	}

	return middleware(handler)
}
