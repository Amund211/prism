package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"time"

	"github.com/google/uuid"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/codes"

	"github.com/Amund211/flashlight/internal/adapters/accountprovider"
	"github.com/Amund211/flashlight/internal/adapters/accountrepository"
	"github.com/Amund211/flashlight/internal/adapters/authsessionrepository"
	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/adapters/database"
	"github.com/Amund211/flashlight/internal/adapters/playerprovider"
	"github.com/Amund211/flashlight/internal/adapters/playerrepository"
	"github.com/Amund211/flashlight/internal/adapters/tagprovider"
	"github.com/Amund211/flashlight/internal/adapters/userrepository"
	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/config"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ports"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/telemetry"
)

// TODO: Put in config
const prodDomainSuffix = "prismoverlay.com"
const stagingDomainSuffix = "rainbow-ctx.pages.dev"

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

	blocklistConfig := ports.BlocklistConfig{
		IPs:          config.BlockedIPs(),
		UserAgents:   config.BlockedUserAgents(),
		UserIDs:      config.BlockedUserIDs(),
		SHA256HexIPs: config.BlockedIPsSHA256Hex(),
	}
	logger.InfoContext(ctx, "Initialized blocklist config",
		"amtIPs", len(blocklistConfig.IPs),
		"amtUserAgents", len(blocklistConfig.UserAgents),
		"amtUserIDs", len(blocklistConfig.UserIDs),
		"amtIPHashes", len(blocklistConfig.SHA256HexIPs),
	)

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

	// Bound every cache so unbounded key growth can't OOM the 128Mi service.
	// Limits sit far above the distinct keys a single instance sees within
	// each TTL, so normal traffic never hits eviction. PlayerPIT is the
	// largest value (~1KB), so its cache is kept smaller than the others.
	playerCache := cache.NewTTLCacheWithMaxSize[*domain.PlayerPIT](1*time.Minute, 20_000)

	accountByUsernameCache := cache.NewTTLCacheWithMaxSize[domain.Account](24*time.Hour, 50_000)
	accountByUUIDCache := cache.NewTTLCacheWithMaxSize[domain.Account](1*time.Minute, 50_000) // Low TTL to quickly show name changes

	tagsCache := cache.NewTTLCacheWithMaxSize[domain.Tags](1*time.Minute, 50_000)

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

	tagProvider, err := tagprovider.NewUrchin(httpClient, time.Now, time.After, config.UrchinAPIKey())
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
		db.SetMaxOpenConns(16)
	} else {
		// Fewer connections in staging to prevent interfering with prod
		db.SetMaxOpenConns(2)
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

	userRepo := userrepository.NewPostgres(db, repositorySchemaName, time.Now)
	logger.InfoContext(ctx, "Initialized UserRepository")

	authSessionRepo := authsessionrepository.NewPostgres(db, repositorySchemaName)
	logger.InfoContext(ctx, "Initialized AuthSessionRepository")

	validateSessionCache := cache.NewTTLCacheWithMaxSize[domain.AuthSession](1*time.Minute, 50_000)

	anonymousLogin := app.BuildAnonymousLogin(authSessionRepo, time.Now, app.GenerateAuthSessionID)
	refreshSession := app.BuildRefreshSession(authSessionRepo, time.Now)
	validateSession := app.BuildValidateSession(authSessionRepo, time.Now, validateSessionCache)
	bearerAuthMiddleware := ports.NewBearerAuthMiddleware(validateSession)

	allowedOrigins, err := ports.NewDomainSuffixes(prodDomainSuffix, stagingDomainSuffix)
	if err != nil {
		fail("Failed to initialize allowed origins", "error", err.Error())
	}

	getAccountByUsernameWithCache, err := app.BuildGetAccountByUsernameWithCache(accountByUsernameCache, accountProvider, accountRepo, time.Now)
	if err != nil {
		fail("Failed to initialize GetAccountByUsernameWithCache", "error", err.Error())
	}
	getAccountByUUIDWithCache, err := app.BuildGetAccountByUUIDWithCache(accountByUUIDCache, accountProvider, accountRepo, time.Now)
	if err != nil {
		fail("Failed to initialize GetAccountByUUIDWithCache", "error", err.Error())
	}

	// Long TTL: the well-known requester check only uses FirstSeenAt, which
	// never changes, and SeenCount, which is just a coarse spam guard.
	userCache := cache.NewTTLCacheWithMaxSize[domain.User](24*time.Hour, 10_000)
	getUserWithCache, err := app.BuildGetUserWithCache(userCache, userRepo)
	if err != nil {
		fail("Failed to initialize GetUserWithCache", "error", err.Error())
	}

	getAndPersistPlayerWithCache, err := app.BuildGetAndPersistPlayerWithCache(playerCache, playerProvider, playerRepo, accountRepo, getAccountByUUIDWithCache, getUserWithCache)
	if err != nil {
		fail("Failed to initialize GetAndPersistPlayerWithCache", "error", err.Error())
	}
	updatePlayerInInterval := app.BuildUpdatePlayerInInterval(getAndPersistPlayerWithCache, time.Now)

	getTags, err := app.BuildGetTagsWithCache(tagsCache, tagProvider)
	if err != nil {
		fail("Failed to initialize GetTagsWithCache", "error", err.Error())
	}

	getHistory := app.BuildGetHistory(playerRepo, updatePlayerInInterval)

	getPlayerPITs := app.BuildGetPlayerPITs(playerRepo, updatePlayerInInterval)

	computeSessions := app.BuildComputeSessions(time.Now)

	getSessionAt := app.BuildGetSessionAt(getPlayerPITs, computeSessions)

	findMilestoneAchievements := app.BuildFindMilestoneAchievements(
		playerRepo,
		getAndPersistPlayerWithCache,
	)

	registerUserVisit := app.BuildRegisterUserVisit(userRepo)

	getPrismNotices := app.BuildGetPrismNotices(time.Now)

	mux := http.NewServeMux()

	// Handler constructors start background rate-limiter eviction goroutines
	// and return a stop func to shut them down. These handlers live for the
	// whole process lifetime, so stopping them only actually matters in tests
	// (via t.Cleanup); in production the goroutines are reclaimed when the
	// process exits. We still collect and defer the stops so a clean main()
	// return tears them down, but note this defer does NOT run on the Cloud Run
	// SIGTERM path (ListenAndServe blocks, main never returns) nor via fail()
	// (os.Exit skips defers) — which is fine, since process exit reclaims them.
	var handlerStops []func()
	defer func() {
		for _, stop := range handlerStops {
			stop()
		}
	}()

	// stops are the rate-limiter eviction-goroutine cleanups for the handler,
	// collected here so a handler can't be registered without also collecting
	// them (handlers without rate limiters pass none).
	handleFunc := func(pattern string, handlerFunc http.HandlerFunc, stops ...func()) {
		handlerStops = append(handlerStops, stops...)
		handler := otelhttp.NewHandler(handlerFunc, pattern)
		mux.Handle(pattern, handler)
	}

	prismNoticesHandler, stopPrismNotices := ports.MakePrismNoticesHandler(
		getPrismNotices,
		registerUserVisit,
		logger.With("port", "prism-notices"),
		sentryMiddleware,
		bearerAuthMiddleware,
		blocklistConfig,
	)
	handleFunc("GET /v1/prism-notices", prismNoticesHandler, stopPrismNotices)

	playerDataHandler, stopPlayerData := ports.MakeGetPlayerDataHandler(
		getAndPersistPlayerWithCache,
		registerUserVisit,
		logger.With("port", "playerdata"),
		sentryMiddleware,
		bearerAuthMiddleware,
		blocklistConfig,
		false,
	)
	handleFunc("GET /v1/playerdata", playerDataHandler, stopPlayerData)

	tagsHandler, stopTags := ports.MakeGetTagsHandler(
		getTags,
		registerUserVisit,
		logger.With("port", "tags"),
		sentryMiddleware,
		bearerAuthMiddleware,
		blocklistConfig,
	)
	handleFunc("GET /v1/tags/{uuid}", tagsHandler, stopTags)

	handleFunc(
		"POST /v1/auth/anonymous/login",
		ports.MakeAnonymousLoginHandler(
			anonymousLogin,
			time.Now,
			logger.With("port", "auth-anonymous-login"),
			sentryMiddleware,
			blocklistConfig,
		),
	)

	handleFunc(
		"POST /v1/auth/refresh",
		ports.MakeAuthRefreshHandler(
			refreshSession,
			time.Now,
			logger.With("port", "auth-refresh"),
			sentryMiddleware,
			blocklistConfig,
		),
	)

	handleFunc(
		"OPTIONS /v1/account/username/{username}",
		ports.BuildCORSHandler(allowedOrigins),
	)
	accountByUsernameHandler, stopAccountByUsername := ports.MakeGetAccountByUsernameHandler(
		getAccountByUsernameWithCache,
		registerUserVisit,
		allowedOrigins,
		logger.With("port", "getaccountbyusername"),
		sentryMiddleware,
		blocklistConfig,
	)
	handleFunc("GET /v1/account/username/{username}", accountByUsernameHandler, stopAccountByUsername)

	handleFunc(
		"OPTIONS /v1/account/uuid/{uuid}",
		ports.BuildCORSHandler(allowedOrigins),
	)
	accountByUUIDHandler, stopAccountByUUID := ports.MakeGetAccountByUUIDHandler(
		getAccountByUUIDWithCache,
		registerUserVisit,
		allowedOrigins,
		logger.With("port", "getaccountbyuuid"),
		sentryMiddleware,
		blocklistConfig,
	)
	handleFunc("GET /v1/account/uuid/{uuid}", accountByUUIDHandler, stopAccountByUUID)

	handleFunc(
		"OPTIONS /v1/history",
		ports.BuildCORSHandler(allowedOrigins),
	)
	historyHandler, stopHistory := ports.MakeGetHistoryHandler(
		getHistory,
		registerUserVisit,
		allowedOrigins,
		logger.With("port", "history"),
		sentryMiddleware,
		blocklistConfig,
	)
	handleFunc("POST /v1/history", historyHandler, stopHistory)

	handleFunc(
		"OPTIONS /v1/sessions",
		ports.BuildCORSHandler(allowedOrigins),
	)
	sessionsHandler, stopSessions := ports.MakeGetSessionsHandler(
		getPlayerPITs,
		computeSessions,
		registerUserVisit,
		allowedOrigins,
		logger.With("port", "sessions"),
		sentryMiddleware,
		blocklistConfig,
	)
	handleFunc("POST /v1/sessions", sessionsHandler, stopSessions)

	handleFunc(
		"OPTIONS /v1/session-at",
		ports.BuildCORSHandler(allowedOrigins),
	)
	sessionAtHandler, stopSessionAt := ports.MakeGetSessionAtHandler(
		getSessionAt,
		registerUserVisit,
		allowedOrigins,
		logger.With("port", "session-at"),
		sentryMiddleware,
		blocklistConfig,
	)
	handleFunc("POST /v1/session-at", sessionAtHandler, stopSessionAt)

	handleFunc(
		"OPTIONS /v1/prestiges/{uuid}",
		ports.BuildCORSHandler(allowedOrigins),
	)
	prestigesHandler, stopPrestiges := ports.MakeGetPrestigesHandler(
		findMilestoneAchievements,
		registerUserVisit,
		allowedOrigins,
		logger.With("port", "prestiges"),
		sentryMiddleware,
		blocklistConfig,
	)
	handleFunc("GET /v1/prestiges/{uuid}", prestigesHandler, stopPrestiges)

	handleFunc(
		"OPTIONS /v1/wrapped/{uuid}/{year}",
		ports.BuildCORSHandler(allowedOrigins),
	)
	wrappedHandler, stopWrapped := ports.MakeGetWrappedHandler(
		getPlayerPITs,
		computeSessions,
		registerUserVisit,
		allowedOrigins,
		logger.With("port", "wrapped"),
		sentryMiddleware,
		blocklistConfig,
	)
	handleFunc("GET /v1/wrapped/{uuid}/{year}", wrappedHandler, stopWrapped)

	// TODO: Remove deprecated non-versioned endpoint. Hits are logged with a
	// "Deprecated endpoint hit" WARN so we can confirm it's safe to drop.
	legacyPlayerDataHandler, stopLegacyPlayerData := ports.MakeGetPlayerDataHandler(
		getAndPersistPlayerWithCache,
		registerUserVisit,
		logger.With("port", "playerdata"),
		sentryMiddleware,
		bearerAuthMiddleware,
		blocklistConfig,
		true,
	)
	handleFunc("GET /playerdata", legacyPlayerDataHandler, stopLegacyPlayerData)

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
