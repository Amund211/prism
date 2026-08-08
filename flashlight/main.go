package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"math/rand/v2"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
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
	"github.com/Amund211/flashlight/internal/proofofwork"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/telemetry"
)

// TODO: Put in config
const prodDomainSuffix = "prismoverlay.com"
const stagingDomainSuffix = "rainbow-ctx.pages.dev"

func main() {
	// rootCtx is cancelled when Cloud Run sends SIGTERM (or on a local SIGINT),
	// which drives the graceful-shutdown sequence at the end of main. It is
	// deliberately kept separate from the startup ctx below: a signal arriving
	// mid-startup must not cancel the in-progress DB migration or OTel setup
	// (that would abort them and log a spurious init error on what is really a
	// normal shutdown) — it is handled once init completes and we reach the
	// serve/select. Tradeoff: a genuinely hung startup won't react to the first
	// SIGTERM and waits for Cloud Run's SIGKILL, but startup is normally
	// sub-second, so avoiding false init errors on every shutdown wins.
	rootCtx, stopSignals := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stopSignals()
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
	// otelShutdown is invoked from the graceful-shutdown sequence at the end of
	// main rather than deferred, so it also runs on the SIGTERM path.

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
	// flush is invoked from the graceful-shutdown sequence at the end of main
	// rather than deferred, so buffered events are flushed on the SIGTERM path.
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

	// Proof-of-work on anonymous login. Mandatory handshake, difficulty 0:
	// the mechanism has to be in every client from the first auth release,
	// because prism's upgrade tail means a no-proof path added later would
	// have to stay open for months — and a no-proof path attackers can use
	// is the same as having no proof-of-work at all. What it buys today is
	// the ability to raise the price of an anonymous identity from the
	// server, with no client release.
	signingKeys := config.AuthChallengeSigningKeys()
	if len(signingKeys) == 0 && config.IsDevelopment() {
		// Gated on the environment, not just on the empty list: config
		// rejects an empty value in production and staging, and this branch
		// must not be the thing that papers over it if that check ever
		// loosens. An ephemeral key boots green and then fails every
		// challenge minted by the previous revision, which is a much worse
		// failure than refusing to start.
		generatedKey, err := proofofwork.GenerateSigningKey()
		if err != nil {
			fail("Failed to generate auth challenge signing key", "error", err.Error())
		}
		logger.WarnContext(ctx, "No auth challenge signing keys configured, generated an ephemeral one")
		signingKeys = []string{generatedKey}
	}
	authChallengeKeys, err := proofofwork.ParseSigningKeys(signingKeys)
	if err != nil {
		fail("Failed to parse auth challenge signing keys", "error", err.Error())
	}
	difficultyFor, err := proofofwork.BuildDifficultyFunc(proofofwork.DefaultDifficulty)
	if err != nil {
		fail("Failed to initialize proof-of-work difficulty", "error", err.Error())
	}
	issueChallenge, err := proofofwork.BuildIssueChallenge(authChallengeKeys, difficultyFor, time.Now)
	if err != nil {
		fail("Failed to initialize proof-of-work challenges", "error", err.Error())
	}
	verifySolution, err := proofofwork.BuildVerifySolution(authChallengeKeys, time.Now)
	if err != nil {
		fail("Failed to initialize proof-of-work verification", "error", err.Error())
	}
	logger.InfoContext(ctx, "Initialized anonymous login proof-of-work", "difficulty", proofofwork.DefaultDifficulty)

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

	getAndPersistPlayerWithCache, err := app.BuildGetAndPersistPlayerWithCache(playerCache, playerProvider, playerRepo, accountRepo, getAccountByUUIDWithCache, getUserWithCache, rand.Float64)
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
	// whole process lifetime; the collected stops are invoked from the
	// graceful-shutdown sequence at the end of main so the eviction goroutines
	// are torn down cleanly on the SIGTERM path.
	var handlerStops []func()

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
		"OPTIONS /v1/auth/anonymous/challenge",
		ports.BuildCORSHandler(allowedOrigins),
	)
	anonymousChallengeHandler, stopAnonymousChallenge := ports.MakeAnonymousChallengeHandler(
		issueChallenge,
		allowedOrigins,
		logger.With("port", "auth-anonymous-challenge"),
		sentryMiddleware,
		blocklistConfig,
	)
	handleFunc("POST /v1/auth/anonymous/challenge", anonymousChallengeHandler, stopAnonymousChallenge)

	handleFunc(
		"OPTIONS /v1/auth/anonymous/login",
		ports.BuildCORSHandler(allowedOrigins),
	)
	anonymousLoginHandler, stopAnonymousLogin := ports.MakeAnonymousLoginHandler(
		anonymousLogin,
		verifySolution,
		time.Now,
		allowedOrigins,
		logger.With("port", "auth-anonymous-login"),
		sentryMiddleware,
		blocklistConfig,
	)
	handleFunc("POST /v1/auth/anonymous/login", anonymousLoginHandler, stopAnonymousLogin)

	handleFunc(
		"OPTIONS /v1/auth/refresh",
		ports.BuildCORSHandler(allowedOrigins),
	)
	authRefreshHandler, stopAuthRefresh := ports.MakeAuthRefreshHandler(
		refreshSession,
		time.Now,
		allowedOrigins,
		logger.With("port", "auth-refresh"),
		sentryMiddleware,
		blocklistConfig,
	)
	handleFunc("POST /v1/auth/refresh", authRefreshHandler, stopAuthRefresh)

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
		bearerAuthMiddleware,
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
		bearerAuthMiddleware,
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
		bearerAuthMiddleware,
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
		bearerAuthMiddleware,
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
		bearerAuthMiddleware,
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
		bearerAuthMiddleware,
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

	// Serve in a goroutine so main can wait for either a fatal server error or
	// a shutdown signal (SIGTERM from Cloud Run, SIGINT locally) and then drive
	// a graceful shutdown. Cloud Run sends SIGTERM and then SIGKILLs the
	// container after a fixed 10s grace period, so the teardown below is
	// budgeted to finish comfortably within that window.
	serverErr := make(chan error, 1)
	go func() {
		if err := httpServer.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
			serverErr <- err
		}
	}()

	select {
	case err := <-serverErr:
		// The server stopped before we asked it to — a genuine failure such as
		// the port already being in use. Nothing is serving, so exit.
		fail("Server error", "error", err.Error())
	case <-rootCtx.Done():
	}

	// Restore default signal handling so a second SIGTERM/SIGINT during a slow
	// or stuck shutdown force-terminates the process instead of being swallowed
	// by the NotifyContext channel.
	stopSignals()

	// The startup span has ended; use a fresh, uncancelled context for the
	// shutdown phase so its logs and bounded steps aren't tied to the finished
	// startup trace or to the already-cancelled rootCtx.
	ctx = context.Background()
	logger.InfoContext(ctx, "Shutdown signal received, shutting down gracefully")

	// Graceful teardown, in reverse order of initialization. Cloud Run SIGKILLs
	// the container 10s after SIGTERM, so the per-step budgets below are sized
	// to sum to at most ~9s in the worst case, leaving margin before the kill.

	// 1. Stop accepting new connections and let in-flight requests drain (5s).
	shutdownCtx, cancelShutdown := context.WithTimeout(ctx, 5*time.Second)
	defer cancelShutdown()
	if err := httpServer.Shutdown(shutdownCtx); err != nil {
		logger.ErrorContext(ctx, "Graceful shutdown failed, forcing connections closed", "error", err.Error())
		if closeErr := httpServer.Close(); closeErr != nil {
			logger.ErrorContext(ctx, "Forced server close failed", "error", closeErr.Error())
		}
	}

	// 2. Stop the background rate-limiter eviction goroutines.
	for _, stop := range handlerStops {
		stop()
	}

	// 3. Close the database pool now that in-flight queries have drained.
	//    Bounded (1s) because db.Close waits for in-flight queries to finish,
	//    so a wedged connection must not eat into the telemetry-flush budget.
	dbClosed := make(chan error, 1)
	go func() { dbClosed <- db.Close() }()
	select {
	case err := <-dbClosed:
		if err != nil {
			logger.ErrorContext(ctx, "Failed to close database connection", "error", err.Error())
		}
	case <-time.After(1 * time.Second):
		logger.ErrorContext(ctx, "Timed out closing database connection")
	}

	// 4. Flush telemetry LAST so shutdown spans/metrics and buffered Sentry
	//    events are exported before the process exits. The OTel and Sentry
	//    exporters are independent, so flush them concurrently (1.5s each) to
	//    cap telemetry teardown at ~1.5s rather than 3s, leaving more margin
	//    before SIGKILL.
	flushCtx, cancelFlush := context.WithTimeout(ctx, 1500*time.Millisecond)
	defer cancelFlush()
	var flushWG sync.WaitGroup
	flushWG.Add(2)
	go func() {
		defer flushWG.Done()
		if err := otelShutdown(flushCtx); err != nil {
			logger.ErrorContext(ctx, "Failed to shut down OpenTelemetry SDK", "error", err.Error())
		}
	}()
	go func() {
		defer flushWG.Done()
		flush(1500 * time.Millisecond)
	}()
	flushWG.Wait()

	logger.InfoContext(ctx, "Shutdown complete")
}
