package function

import (
	"context"
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

func init() {
	localOnly := os.Getenv("LOCAL_ONLY") == "true"

	apiKey := os.Getenv("HYPIXEL_API_KEY")
	if apiKey == "" {
		log.Fatalln("Missing Hypixel API key")
	}

	sentryDSN := os.Getenv("SENTRY_DSN")
	if sentryDSN == "" && !localOnly {
		log.Fatalln("Missing Sentry DSN")
	}

	httpClient := &http.Client{
		Timeout: 10 * time.Second,
	}

	playerCache := cache.NewPlayerCache(1 * time.Minute)

	hypixelAPI := hypixel.NewHypixelAPI(httpClient, apiKey)

	ipRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		ratelimiting.NewKeyBasedRateLimiter(2, 120), ratelimiting.IPKeyFunc,
	)
	userIdRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		// NOTE: Rate limiting based on user controlled value
		ratelimiting.NewKeyBasedRateLimiter(2, 120), ratelimiting.UserIdKeyFunc,
	)

	var sentryMiddleware func(http.HandlerFunc) http.HandlerFunc
	if localOnly && sentryDSN == "" {
		sentryMiddleware = func(next http.HandlerFunc) http.HandlerFunc {
			return next
		}
	} else {
		realSentryMiddleware, flush, err := reporting.InitSentryMiddleware(sentryDSN)
		if err != nil {
			log.Fatalf("Failed to initialize sentry: %v", err)
		}
		sentryMiddleware = realSentryMiddleware

		defer flush()
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
