package function

import (
	"context"
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"os"
	"time"

	"github.com/Amund211/flashlight/internal/cache"
	"github.com/Amund211/flashlight/internal/getstats"
	"github.com/Amund211/flashlight/internal/hypixel"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/server"

	"github.com/GoogleCloudPlatform/functions-framework-go/functions"
)

type mockedHypixelAPI struct{}

func (hypixelAPI *mockedHypixelAPI) GetPlayerData(ctx context.Context, uuid string) ([]byte, int, error) {
	return []byte(fmt.Sprintf(`{"success":true,"player":{"uuid":"%s"}}`, uuid)), 200, nil
}

func init() {
	localOnly := os.Getenv("LOCAL_ONLY") == "true"

	httpClient := &http.Client{
		Timeout: 10 * time.Second,
	}

	playerCache := cache.NewPlayerCache(1 * time.Minute)

	hypixelApiKey := os.Getenv("HYPIXEL_API_KEY")
	var hypixelAPI hypixel.HypixelAPI
	if hypixelApiKey != "" {
		hypixelAPI = hypixel.NewHypixelAPI(httpClient, hypixelApiKey)
	} else {
		if !localOnly {
			log.Fatalln("Missing Hypixel API key")
		}
		hypixelAPI = &mockedHypixelAPI{}
	}

	ipRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		ratelimiting.NewTokenBucketRateLimiter(
			ratelimiting.RefillPerSecond(8),
			ratelimiting.BurstSize(480),
		),
		ratelimiting.IPKeyFunc,
	)
	userIdRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		// NOTE: Rate limiting based on user controlled value
		ratelimiting.NewTokenBucketRateLimiter(
			ratelimiting.RefillPerSecond(2),
			ratelimiting.BurstSize(120),
		),
		ratelimiting.UserIdKeyFunc,
	)

	sentryDSN := os.Getenv("SENTRY_DSN")
	var sentryMiddleware func(http.HandlerFunc) http.HandlerFunc
	if sentryDSN != "" {
		realSentryMiddleware, flush, err := reporting.InitSentryMiddleware(sentryDSN)
		if err != nil {
			log.Fatalf("Failed to initialize sentry: %v", err)
		}
		sentryMiddleware = realSentryMiddleware

		defer flush()
	} else {
		if !localOnly {
			log.Fatalln("Missing Sentry DSN")
		}
		sentryMiddleware = func(next http.HandlerFunc) http.HandlerFunc {
			return next
		}
	}

	rootLogger := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	middleware := server.ComposeMiddlewares(
		logging.NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		server.NewRateLimitMiddleware(ipRateLimiter),
		server.NewRateLimitMiddleware(userIdRateLimiter),
	)

	functions.HTTP(
		"flashlight",
		middleware(
			server.MakeServeGetPlayerData(
				func(ctx context.Context, uuid string) ([]byte, int, error) {
					return getstats.GetOrCreateMinifiedPlayerData(ctx, playerCache, hypixelAPI, uuid)
				},
			),
		),
	)

	rootLogger.Info("Init complete")
}
