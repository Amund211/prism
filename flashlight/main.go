package main

import (
	"context"
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
	"github.com/Amund211/flashlight/internal/adapters/tagprovider"
	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/config"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ports"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/telemetry"
	"github.com/google/uuid"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/codes"

	_ "golang.org/x/crypto/x509roots/fallback" // Add fallback certs (for running in docker scratch image without ca-certificates)
)

// TODO: Put in config
const PROD_DOMAIN_SUFFIX = "prismoverlay.com"
const STAGING_DOMAIN_SUFFIX = "rainbow-ctx.pages.dev"

func main() {
	ctx := context.Background()
	instanceID := uuid.New().String()

	jsonHandler := slog.NewJSONHandler(os.Stdout, nil)
	handler := logging.NewGoogleCloudTracingLogHandler(jsonHandler, "prism-overlay")
	logger := slog.New(handler).With("instanceID", instanceID)

	fail := func(msg string, args ...any) {
		logger.ErrorContext(ctx, msg, args...)
		os.Exit(1)
	}

	config, err := config.ConfigFromEnv()
	if err != nil {
		fail("Failed to load config", "error", err.Error())
	}
	logger.InfoContext(ctx, "Loaded config", "config", config.NonSensitiveString())

	serviceName := "flashlight"
	if config.IsStaging() {
		serviceName = "flashlight-test"
	} else if config.IsDevelopment() {
		serviceName = "flashlight-dev"
	}

	otelShutdown, err := telemetry.SetupOTelSDK(ctx, serviceName)
	if err != nil {
		fail("Failed to initialize OpenTelemetry SDK", "error", err.Error())
	}
	defer func() {
		err := otelShutdown(ctx)
		if err != nil {
			logger.ErrorContext(ctx, "Failed to shutdown OpenTelemetry SDK", "error", err.Error())
		}
	}()

	ctx, span := otel.Tracer("flashlight/main").Start(ctx, "startup")
	defer span.End()

	originalFail := fail
	fail = func(msg string, args ...any) {
		span.SetStatus(codes.Error, msg)
		originalFail(msg, args...)
	}

	playerCache := cache.NewTTLCache[*domain.PlayerPIT](1 * time.Minute)

	accountByUsernameCache := cache.NewTTLCache[domain.Account](24 * time.Hour)
	accountByUUIDCache := cache.NewTTLCache[domain.Account](1 * time.Minute) // Low TTL to quickly show name changes

	tagsCache := cache.NewTTLCache[domain.Tags](1 * time.Minute)

	httpClient := &http.Client{
		Timeout: 10 * time.Second,
	}
	hypixelAPI, err := playerprovider.NewHypixelAPIOrMock(config, httpClient, time.Now, time.After)
	if err != nil {
		fail("Failed to initialize Hypixel API", "error", err.Error())
	}
	logger.InfoContext(ctx, "Initialized Hypixel API")

	playerProvider, err := playerprovider.NewHypixelPlayerProvider(hypixelAPI)
	if err != nil {
		fail("Failed to initialize HypixelPlayerProvider", "error", err.Error())
	}

	accountProvider := accountprovider.NewMojang(httpClient, time.Now, time.After)

	tagProvider, err := tagprovider.NewUrchin(httpClient, time.Now, time.After)
	if err != nil {
		fail("Failed to initialize Urchin tag provider", "error", err.Error())
	}

	sentryMiddleware, flush, err := reporting.NewSentryMiddlewareOrMock(config)
	if err != nil {
		fail("Failed to initialize Sentry", "error", err.Error())
	}
	defer flush()
	logger.InfoContext(ctx, "Initialized Sentry middleware")

	logger.InfoContext(ctx, "Initializing database connection")
	db, err := database.NewCloudsqlPostgresDatabase(config)
	if err != nil {
		fail("Failed to initialize PostgresPlayerRepository", "error", err.Error())
	}
	if config.IsProduction() {
		// Current cloud sql database has a connection limit of 25, and 3 reserved for superusers
		db.DB.SetMaxOpenConns(16)
	} else {
		// Fewer connections in staging to prevent interfering with prod
		db.DB.SetMaxOpenConns(2)
	}
	logger.InfoContext(ctx, "Initialized database connection")

	repositorySchemaName := database.GetSchemaName(!config.IsProduction())

	err = database.NewDatabaseMigrator(db, logger.With("component", "migrator")).Migrate(ctx, repositorySchemaName)
	if err != nil {
		fail("Failed to migrate database", "error", err.Error())
	}

	playerRepo := playerrepository.NewPostgresPlayerRepository(db, repositorySchemaName)
	logger.InfoContext(ctx, "Initialized PlayerRepository")

	accountRepo := accountrepository.NewPostgres(db, repositorySchemaName)

	allowedOrigins, err := ports.NewDomainSuffixes(PROD_DOMAIN_SUFFIX, STAGING_DOMAIN_SUFFIX)
	if err != nil {
		fail("Failed to initialize allowed origins", "error", err.Error())
	}

	getAndPersistPlayerWithCache, err := app.BuildGetAndPersistPlayerWithCache(playerCache, playerProvider, playerRepo)
	if err != nil {
		fail("Failed to initialize GetAndPersistPlayerWithCache", "error", err.Error())
	}
	updatePlayerInInterval := app.BuildUpdatePlayerInInterval(getAndPersistPlayerWithCache, time.Now)

	getAccountByUsernameWithCache, err := app.BuildGetAccountByUsernameWithCache(accountByUsernameCache, accountProvider, accountRepo, time.Now)
	if err != nil {
		fail("Failed to initialize GetAccountByUsernameWithCache", "error", err.Error())
	}
	getAccountByUUIDWithCache, err := app.BuildGetAccountByUUIDWithCache(accountByUUIDCache, accountProvider, accountRepo, time.Now)
	if err != nil {
		fail("Failed to initialize GetAccountByUUIDWithCache", "error", err.Error())
	}

	getTags, err := app.BuildGetTagsWithCache(tagsCache, tagProvider)
	if err != nil {
		fail("Failed to initialize GetTagsWithCache", "error", err.Error())
	}

	getHistory := app.BuildGetHistory(playerRepo, updatePlayerInInterval)

	getSessions := app.BuildGetSessions(playerRepo, updatePlayerInInterval)

	findMilestoneAchievements := app.BuildFindMilestoneAchievements(
		playerRepo,
		getAndPersistPlayerWithCache,
	)

	mux := http.NewServeMux()

	handleFunc := func(pattern string, handlerFunc http.HandlerFunc) {
		innerHandler := otelhttp.WithRouteTag(pattern, handlerFunc)
		outerHandler := otelhttp.NewHandler(innerHandler, pattern)
		mux.Handle(pattern, outerHandler)
	}

	handleFunc(
		"GET /v1/playerdata",
		ports.MakeGetPlayerDataHandler(
			getAndPersistPlayerWithCache,
			getTags,
			logger.With("port", "playerdata"),
			sentryMiddleware,
		),
	)

	handleFunc(
		"GET /v1/tags/{uuid}",
		ports.MakeGetTagsHandler(
			getTags,
			logger.With("port", "tags"),
			sentryMiddleware,
		),
	)

	handleFunc(
		"OPTIONS /v1/account/username/{username}",
		ports.BuildCORSHandler(allowedOrigins),
	)
	handleFunc(
		"GET /v1/account/username/{username}",
		ports.MakeGetAccountByUsernameHandler(
			getAccountByUsernameWithCache,
			allowedOrigins,
			logger.With("port", "getaccountbyusername"),
			sentryMiddleware,
		),
	)

	handleFunc(
		"OPTIONS /v1/account/uuid/{uuid}",
		ports.BuildCORSHandler(allowedOrigins),
	)
	handleFunc(
		"GET /v1/account/uuid/{uuid}",
		ports.MakeGetAccountByUUIDHandler(
			getAccountByUUIDWithCache,
			allowedOrigins,
			logger.With("port", "getaccountbyuuid"),
			sentryMiddleware,
		),
	)

	handleFunc(
		"OPTIONS /v1/history",
		ports.BuildCORSHandler(allowedOrigins),
	)
	handleFunc(
		"POST /v1/history",
		ports.MakeGetHistoryHandler(
			getHistory,
			allowedOrigins,
			logger.With("port", "history"),
			sentryMiddleware,
		),
	)

	handleFunc(
		"OPTIONS /v1/sessions",
		ports.BuildCORSHandler(allowedOrigins),
	)
	handleFunc(
		"POST /v1/sessions",
		ports.MakeGetSessionsHandler(
			getSessions,
			allowedOrigins,
			logger.With("port", "sessions"),
			sentryMiddleware,
		),
	)

	handleFunc(
		"OPTIONS /v1/prestiges/{uuid}",
		ports.BuildCORSHandler(allowedOrigins),
	)
	handleFunc(
		"GET /v1/prestiges/{uuid}",
		ports.MakeGetPrestigesHandler(
			findMilestoneAchievements,
			allowedOrigins,
			logger.With("port", "prestiges"),
			sentryMiddleware,
		),
	)

	// TODO: Remove
	handleFunc(
		"GET /playerdata",
		ports.MakeGetPlayerDataHandler(
			getAndPersistPlayerWithCache,
			getTags,
			logger.With("port", "playerdata"),
			sentryMiddleware,
		),
	)

	httpServer := &http.Server{
		Addr:         fmt.Sprintf(":%s", config.Port()),
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	span.SetStatus(codes.Ok, "Initialization complete")
	span.End()
	logger.InfoContext(ctx, "Init complete")

	err = httpServer.ListenAndServe()
	if errors.Is(err, http.ErrServerClosed) {
		logger.InfoContext(ctx, "Server shutdown")
	} else {
		fail("Server error", "error", err.Error())
	}
}
