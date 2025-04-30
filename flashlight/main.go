package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
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
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ports"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
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

	historyIPRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		ratelimiting.NewTokenBucketRateLimiter(
			ratelimiting.RefillPerSecond(1),
			ratelimiting.BurstSize(60),
		),
		ratelimiting.IPKeyFunc,
	)
	historyMiddleware := ports.ComposeMiddlewares(
		logging.NewRequestLoggerMiddleware(logger.With("component", "history")),
		sentryMiddleware,
		ports.BuildCORSMiddleware(allowedOrigins),
		ports.NewRateLimitMiddleware(historyIPRateLimiter),
	)
	http.HandleFunc(
		"OPTIONS /v1/history",
		ports.BuildCORSHandler(allowedOrigins),
	)
	http.HandleFunc(
		"POST /v1/history",
		// TODO: Implement sentry + logging middleware
		historyMiddleware(
			func(w http.ResponseWriter, r *http.Request) {
				defer r.Body.Close()
				body, err := io.ReadAll(r.Body)
				if err != nil {
					http.Error(w, "Failed to read request body", http.StatusBadRequest)
					return
				}
				request := struct {
					UUID  string    `json:"uuid"`
					Start time.Time `json:"start"`
					End   time.Time `json:"end"`
					Limit int       `json:"limit"`
				}{}
				err = json.Unmarshal(body, &request)
				if err != nil {
					http.Error(w, "Failed to parse request body", http.StatusBadRequest)
					return
				}

				normalizedUUID, err := strutils.NormalizeUUID(request.UUID)
				if err != nil {
					http.Error(w, "invalid uuid", http.StatusBadRequest)
					return
				}

				history, err := getHistory(r.Context(), normalizedUUID, request.Start, request.End, request.Limit)
				if err != nil {
					http.Error(w, "Failed to get history", http.StatusInternalServerError)
					return
				}

				marshalled, err := ports.HistoryToRainbowHistoryData(history)
				if err != nil {
					http.Error(w, "Failed to marshal response", http.StatusInternalServerError)
					return
				}

				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusOK)
				w.Write(marshalled)
			},
		),
	)

	getSessionsIPRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		ratelimiting.NewTokenBucketRateLimiter(
			ratelimiting.RefillPerSecond(1),
			ratelimiting.BurstSize(20),
		),
		ratelimiting.IPKeyFunc,
	)
	getSessionsMiddleware := ports.ComposeMiddlewares(
		logging.NewRequestLoggerMiddleware(logger.With("component", "sessions")),
		sentryMiddleware,
		ports.BuildCORSMiddleware(allowedOrigins),
		ports.NewRateLimitMiddleware(getSessionsIPRateLimiter),
	)
	http.HandleFunc(
		"OPTIONS /v1/sessions",
		ports.BuildCORSHandler(allowedOrigins),
	)
	http.HandleFunc(
		"POST /v1/sessions",
		// TODO: Implement sentry + logging middleware
		getSessionsMiddleware(
			func(w http.ResponseWriter, r *http.Request) {
				defer r.Body.Close()
				body, err := io.ReadAll(r.Body)
				if err != nil {
					http.Error(w, "Failed to read request body", http.StatusBadRequest)
					return
				}
				request := struct {
					UUID  string    `json:"uuid"`
					Start time.Time `json:"start"`
					End   time.Time `json:"end"`
				}{}
				err = json.Unmarshal(body, &request)
				if err != nil {
					http.Error(w, "Failed to parse request body", http.StatusBadRequest)
					return
				}

				normalizedUUID, err := strutils.NormalizeUUID(request.UUID)
				if err != nil {
					http.Error(w, "invalid uuid", http.StatusBadRequest)
					return
				}

				sessions, err := getSessions(r.Context(), normalizedUUID, request.Start, request.End)
				if err != nil {
					http.Error(w, "Failed to get sessions", http.StatusInternalServerError)
					return
				}

				marshalled, err := ports.SessionsToRainbowSessionsData(sessions)
				if err != nil {
					http.Error(w, "Failed to marshal response", http.StatusInternalServerError)
					return
				}

				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusOK)
				w.Write(marshalled)
			},
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
