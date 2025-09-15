package main

import (
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/accountprovider"
	"github.com/Amund211/flashlight/internal/adapters/accountrepository"
	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/adapters/database"
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

	accountByUsernameCache := cache.NewTTLCache[domain.Account](24 * time.Hour)
	accountByUUIDCache := cache.NewTTLCache[domain.Account](1 * time.Minute) // Low TTL to quickly show name changes

	httpClient := &http.Client{
		Timeout: 10 * time.Second,
	}
	hypixelAPI, err := playerprovider.NewHypixelAPIOrMock(config, httpClient)
	if err != nil {
		fail("Failed to initialize Hypixel API", "error", err.Error())
	}
	logger.Info("Initialized Hypixel API")

	playerProvider := playerprovider.NewHypixelPlayerProvider(hypixelAPI)

	accountProvider := accountprovider.NewMojang(httpClient, time.Now, time.After)

	sentryMiddleware, flush, err := reporting.NewSentryMiddlewareOrMock(config)
	if err != nil {
		fail("Failed to initialize Sentry", "error", err.Error())
	}
	defer flush()
	logger.Info("Initialized Sentry middleware")

	logger.Info("Initializing database connection")
	db, err := database.NewCloudsqlPostgresDatabase(config)
	if err != nil {
		fail("Failed to initialize PostgresPlayerRepository", "error", err.Error())
	}
	logger.Info("Initialized database connection")

	repositorySchemaName := database.GetSchemaName(!config.IsProduction())

	err = database.NewDatabaseMigrator(db, logger.With("component", "migrator")).Migrate(repositorySchemaName)
	if err != nil {
		fail("Failed to migrate database", "error", err.Error())
	}

	playerRepo := playerrepository.NewPostgresPlayerRepository(db, repositorySchemaName)
	logger.Info("Initialized PlayerRepository")

	accountRepo := accountrepository.NewPostgres(db, repositorySchemaName)

	allowedOrigins, err := ports.NewDomainSuffixes(PROD_DOMAIN_SUFFIX, STAGING_DOMAIN_SUFFIX)
	if err != nil {
		fail("Failed to initialize allowed origins", "error", err.Error())
	}

	getAndPersistPlayerWithCache := app.BuildGetAndPersistPlayerWithCache(playerCache, playerProvider, playerRepo)
	updatePlayerInInterval := app.BuildUpdatePlayerInInterval(getAndPersistPlayerWithCache, time.Now)

	getAccountByUsernameWithCache := app.BuildGetAccountByUsernameWithCache(accountByUsernameCache, accountProvider, accountRepo, time.Now)
	getAccountByUUIDWithCache := app.BuildGetAccountByUUIDWithCache(accountByUUIDCache, accountProvider, accountRepo, time.Now)

	getHistory := app.BuildGetHistory(playerRepo, updatePlayerInInterval)

	getSessions := app.BuildGetSessions(playerRepo, updatePlayerInInterval)

	findMilestoneAchievements := app.BuildFindMilestoneAchievements(
		playerRepo,
		getAndPersistPlayerWithCache,
	)

	http.HandleFunc(
		"GET /v1/playerdata",
		ports.MakeGetPlayerDataHandler(
			getAndPersistPlayerWithCache,
			logger.With("port", "playerdata"),
			sentryMiddleware,
		),
	)

	http.HandleFunc(
		"OPTIONS /v1/account/username/{username}",
		ports.BuildCORSHandler(allowedOrigins),
	)
	http.HandleFunc(
		"GET /v1/account/username/{username}",
		ports.MakeGetAccountByUsernameHandler(
			getAccountByUsernameWithCache,
			allowedOrigins,
			logger.With("port", "getaccountbyusername"),
			sentryMiddleware,
		),
	)

	http.HandleFunc(
		"OPTIONS /v1/account/uuid/{uuid}",
		ports.BuildCORSHandler(allowedOrigins),
	)
	http.HandleFunc(
		"GET /v1/account/uuid/{uuid}",
		ports.MakeGetAccountByUUIDHandler(
			getAccountByUUIDWithCache,
			allowedOrigins,
			logger.With("port", "getaccountbyuuid"),
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
			logger.With("port", "history"),
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
			logger.With("port", "sessions"),
			sentryMiddleware,
		),
	)

	http.HandleFunc(
		"OPTIONS /v1/prestiges/{uuid}",
		ports.BuildCORSHandler(allowedOrigins),
	)
	http.HandleFunc(
		"GET /v1/prestiges/{uuid}",
		ports.MakeGetPrestigesHandler(
			findMilestoneAchievements,
			allowedOrigins,
			logger.With("port", "prestiges"),
			sentryMiddleware,
		),
	)

	// TODO: Remove
	http.HandleFunc(
		"GET /playerdata",
		ports.MakeGetPlayerDataHandler(
			getAndPersistPlayerWithCache,
			logger.With("port", "playerdata"),
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
