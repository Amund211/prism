package main

import (
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/adapters/playerprovider"
	"github.com/Amund211/flashlight/internal/adapters/playerrepository"
	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/config"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ports"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/google/uuid"
)

// TODO: Put in config
const PROD_DOMAIN_SUFFIX = "prismoverlay.com"
const STAGING_DOMAIN_SUFFIX = "rainbow-ctx.pages.dev"

func main() {
	instanceID := uuid.New().String()
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil)).With("instanceID", instanceID)

	fail := func(msg string, args ...any) {
		logger.Error(msg, args...)
		os.Exit(1)
	}

	config, err := config.ConfigFromEnv()
	if err != nil {
		fail("Failed to load config", "error", err.Error())
	}
	logger.Info("Loaded config", "config", config.NonSensitiveString())

	playerCache := cache.NewTTLCache[*domain.PlayerPIT](1 * time.Minute)

	httpClient := &http.Client{
		Timeout: 10 * time.Second,
	}
	hypixelAPI, err := playerprovider.NewHypixelAPIOrMock(config, httpClient)
	if err != nil {
		fail("Failed to initialize Hypixel API", "error", err.Error())
	}
	logger.Info("Initialized Hypixel API")

	provider := playerprovider.NewHypixelPlayerProvider(hypixelAPI)

	sentryMiddleware, flush, err := reporting.NewSentryMiddlewareOrMock(config)
	if err != nil {
		fail("Failed to initialize Sentry", "error", err.Error())
	}
	defer flush()
	logger.Info("Initialized Sentry middleware")

	repo, err := playerrepository.NewPostgresPlayerRepositoryOrMock(config, logger)
	if err != nil {
		fail("Failed to initialize PostgresPlayerRepository", "error", err.Error())
	}
	logger.Info("Initialized PlayerRepository")

	allowedOrigins, err := ports.NewDomainSuffixes(PROD_DOMAIN_SUFFIX, STAGING_DOMAIN_SUFFIX)
	if err != nil {
		fail("Failed to initialize allowed origins", "error", err.Error())
	}

	getAndPersistPlayerWithCache := app.BuildGetAndPersistPlayerWithCache(playerCache, provider, repo)

	getHistory := app.BuildGetHistory(repo, getAndPersistPlayerWithCache, time.Now)

	getSessions := app.BuildGetSessions(repo, getAndPersistPlayerWithCache, time.Now)

	http.HandleFunc(
		"GET /v1/playerdata",
		ports.MakeGetPlayerDataHandler(
			getAndPersistPlayerWithCache,
			logger.With("component", "getPlayerData"),
			sentryMiddleware,
		),
	)

	http.HandleFunc(
		"OPTIONS /v1/history",
		ports.BuildCORSHandler(allowedOrigins),
	)
	http.HandleFunc(
		"POST /v1/history",
		ports.MakeGetHistoryHandler(
			getHistory,
			allowedOrigins,
			logger.With("component", "history"),
			sentryMiddleware,
		),
	)

	http.HandleFunc(
		"OPTIONS /v1/sessions",
		ports.BuildCORSHandler(allowedOrigins),
	)
	http.HandleFunc(
		"POST /v1/sessions",
		ports.MakeGetSessionsHandler(
			getSessions,
			allowedOrigins,
			logger.With("component", "sessions"),
			sentryMiddleware,
		),
	)

	// TODO: Remove
	http.HandleFunc(
		"GET /playerdata",
		ports.MakeGetPlayerDataHandler(
			getAndPersistPlayerWithCache,
			logger.With("component", "getPlayerData"),
			sentryMiddleware,
		),
	)

	logger.Info("Init complete")
	err = http.ListenAndServe(fmt.Sprintf(":%s", config.Port()), nil)
	if errors.Is(err, http.ErrServerClosed) {
		logger.Info("Server shutdown")
	} else {
		fail("Server error", "error", err.Error())
	}
}
