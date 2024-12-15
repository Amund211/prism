package function

import (
	"context"
	"log"
	"log/slog"
	"net/http"
	"os"
	"time"

	"github.com/Amund211/flashlight/internal/cache"
	"github.com/Amund211/flashlight/internal/config"
	"github.com/Amund211/flashlight/internal/getstats"
	"github.com/Amund211/flashlight/internal/hypixel"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/server"
	"github.com/Amund211/flashlight/internal/storage"

	"github.com/GoogleCloudPlatform/functions-framework-go/functions"
)

func init() {
	config, err := config.ConfigFromEnv()
	if err != nil {
		log.Fatalf("Failed to load config: %s", err.Error())
	}
	log.Printf("Starting with %s", config.NonSensitiveString())

	playerCache := cache.NewPlayerCache(1 * time.Minute)

	httpClient := &http.Client{
		Timeout: 10 * time.Second,
	}
	hypixelAPI, err := hypixel.NewHypixelAPIOrMock(config, httpClient)
	if err != nil {
		log.Fatalf("Failed to initialize Hypixel API: %s", err.Error())
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

	sentryMiddleware, flush, err := reporting.NewSentryMiddlewareOrMock(config)
	if err != nil {
		log.Fatalf("Failed to initialize Sentry: %s", err.Error())
	}
	defer flush()

	rootLogger := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	var persistor storage.StatsPersistor

	var connectionString string
	if config.IsDevelopment() {
		connectionString = storage.LOCAL_CONNECTION_STRING
	} else {
		connectionString = storage.GetCloudSQLConnectionString(config.DBUsername(), config.DBPassword(), config.CloudSQLUnixSocketPath())
	}

	persistorSchemaName := storage.GetSchemaName(!config.IsProduction())

	rootLogger.Info("Initializing database connection")
	db, err := storage.NewPostgresDatabase(connectionString)
	if err != nil {
		if config.IsDevelopment() {
			log.Printf("Failed to connect to database: %s. Falling back to stub persistor.", err.Error())
			persistor = storage.NewStubPersistor()
		} else {
			log.Fatalf("Failed to connect to database: %v", err)
		}
	} else {
		storage.NewDatabaseMigrator(db, rootLogger.With("component", "migrator")).Migrate(persistorSchemaName)
		persistor = storage.NewPostgresStatsPersistor(db, persistorSchemaName)
	}

	middleware := server.ComposeMiddlewares(
		logging.NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		server.NewRateLimitMiddleware(ipRateLimiter),
		server.NewRateLimitMiddleware(userIdRateLimiter),
	)

	functions.HTTP(
		"flashlight",
		middleware(
			server.MakeGetPlayerDataHandler(
				func(ctx context.Context, uuid string) ([]byte, int, error) {
					return getstats.GetOrCreateProcessedPlayerData(ctx, playerCache, hypixelAPI, persistor, uuid)
				},
			),
		),
	)

	rootLogger.Info("Init complete")
}
