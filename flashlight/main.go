package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/Amund211/flashlight/internal/cache"
	"github.com/Amund211/flashlight/internal/config"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/getstats"
	"github.com/Amund211/flashlight/internal/hypixel"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/server"
	"github.com/Amund211/flashlight/internal/storage"
	"github.com/google/uuid"
)

// TODO: Put in config
const PROD_URL = "https://prismoverlay.com"
const STAGING_URL_SUFFIX = ".rainbow-ctx.pages.dev"

func corsMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		if origin == PROD_URL || strings.HasSuffix(origin, STAGING_URL_SUFFIX) {
			w.Header().Set("Access-Control-Allow-Origin", origin)
		}

		if r.Method == http.MethodOptions {
			w.Header().Set("Access-Control-Allow-Methods", "GET,POST")
			w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
			// TODO: Add longer max age (default 5s) when it works well
			// w.Header().Set("Access-Control-Max-Age", "3600")
			w.WriteHeader(http.StatusNoContent)
			return
		}

		next(w, r)
	}
}

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

	playerCache := cache.NewPlayerCache(1 * time.Minute)

	httpClient := &http.Client{
		Timeout: 10 * time.Second,
	}
	hypixelAPI, err := hypixel.NewHypixelAPIOrMock(config, httpClient)
	if err != nil {
		fail("Failed to initialize Hypixel API", "error", err.Error())
	}
	logger.Info("Initialized Hypixel API")

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
		fail("Failed to initialize Sentry", "error", err.Error())
	}
	defer flush()
	logger.Info("Initialized Sentry middleware")

	persistor, err := storage.NewPostgresStatsPersistorOrMock(config, logger)
	if err != nil {
		fail("Failed to initialize PostgresStatsPersistor", "error", err.Error())
	}
	logger.Info("Initialized StatsPersistor")

	middleware := server.ComposeMiddlewares(
		logging.NewRequestLoggerMiddleware(logger.With("component", "getPlayerData")),
		sentryMiddleware,
		server.NewRateLimitMiddleware(ipRateLimiter),
		server.NewRateLimitMiddleware(userIdRateLimiter),
	)

	http.HandleFunc(
		"GET /v1/playerdata",
		middleware(
			server.MakeGetPlayerDataHandler(
				func(ctx context.Context, uuid string) ([]byte, int, error) {
					return getstats.GetOrCreateProcessedPlayerData(ctx, playerCache, hypixelAPI, persistor, uuid)
				},
			),
		),
	)

	historyIPRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		ratelimiting.NewTokenBucketRateLimiter(
			ratelimiting.RefillPerSecond(1),
			ratelimiting.BurstSize(60),
		),
		ratelimiting.IPKeyFunc,
	)
	historyMiddleware := server.ComposeMiddlewares(
		corsMiddleware,
		logging.NewRequestLoggerMiddleware(logger.With("component", "history")),
		server.NewRateLimitMiddleware(historyIPRateLimiter),
	)
	http.HandleFunc(
		"OPTIONS /v1/history",
		historyMiddleware(func(w http.ResponseWriter, r *http.Request) {}),
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

				history, err := persistor.GetHistory(r.Context(), request.UUID, request.Start, request.End, request.Limit)
				if err != nil {
					http.Error(w, "Failed to get history", http.StatusInternalServerError)
					return
				}

				type statsResponse struct {
					Winstreak   *int `json:"winstreak"`
					GamesPlayed int  `json:"gamesPlayed"`
					Wins        int  `json:"wins"`
					Losses      int  `json:"losses"`
					BedsBroken  int  `json:"bedsBroken"`
					BedsLost    int  `json:"bedsLost"`
					FinalKills  int  `json:"finalKills"`
					FinalDeaths int  `json:"finalDeaths"`
					Kills       int  `json:"kills"`
					Deaths      int  `json:"deaths"`
				}

				type playerDataResponse struct {
					UUID       string        `json:"uuid"`
					QueriedAt  time.Time     `json:"queriedAt"`
					Experience float64       `json:"experience"`
					Solo       statsResponse `json:"solo"`
					Doubles    statsResponse `json:"doubles"`
					Threes     statsResponse `json:"threes"`
					Fours      statsResponse `json:"fours"`
					Overall    statsResponse `json:"overall"`
				}

				pitStatsToResponse := func(stats domain.GamemodeStatsPIT) statsResponse {
					return statsResponse{
						Winstreak:   stats.Winstreak,
						GamesPlayed: stats.GamesPlayed,
						Wins:        stats.Wins,
						Losses:      stats.Losses,
						BedsBroken:  stats.BedsBroken,
						BedsLost:    stats.BedsLost,
						FinalKills:  stats.FinalKills,
						FinalDeaths: stats.FinalDeaths,
						Kills:       stats.Kills,
						Deaths:      stats.Deaths,
					}
				}

				responseData := make([]playerDataResponse, 0, len(history))

				for _, data := range history {
					responseData = append(responseData, playerDataResponse{
						UUID:       data.UUID,
						QueriedAt:  data.QueriedAt,
						Experience: data.Experience,
						Solo:       pitStatsToResponse(data.Solo),
						Doubles:    pitStatsToResponse(data.Doubles),
						Threes:     pitStatsToResponse(data.Threes),
						Fours:      pitStatsToResponse(data.Fours),
						Overall:    pitStatsToResponse(data.Overall),
					})
				}

				marshalled, err := json.Marshal(responseData)
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
	getSessionsMiddleware := server.ComposeMiddlewares(
		corsMiddleware,
		logging.NewRequestLoggerMiddleware(logger.With("component", "history")),
		server.NewRateLimitMiddleware(getSessionsIPRateLimiter),
	)
	http.HandleFunc(
		"OPTIONS /v1/sessions",
		getSessionsMiddleware(func(w http.ResponseWriter, r *http.Request) {}),
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

				sessions, err := persistor.GetSessions(r.Context(), request.UUID, request.Start, request.End)
				if err != nil {
					http.Error(w, "Failed to get sessions", http.StatusInternalServerError)
					return
				}

				type statsResponse struct {
					Winstreak   *int `json:"winstreak"`
					GamesPlayed int  `json:"gamesPlayed"`
					Wins        int  `json:"wins"`
					Losses      int  `json:"losses"`
					BedsBroken  int  `json:"bedsBroken"`
					BedsLost    int  `json:"bedsLost"`
					FinalKills  int  `json:"finalKills"`
					FinalDeaths int  `json:"finalDeaths"`
					Kills       int  `json:"kills"`
					Deaths      int  `json:"deaths"`
				}

				type playerDataResponse struct {
					ID                string        `json:"id"`
					DataFormatVersion int           `json:"dataFormatVersion"`
					UUID              string        `json:"uuid"`
					QueriedAt         time.Time     `json:"queriedAt"`
					Experience        float64       `json:"experience"`
					Solo              statsResponse `json:"solo"`
					Doubles           statsResponse `json:"doubles"`
					Threes            statsResponse `json:"threes"`
					Fours             statsResponse `json:"fours"`
					Overall           statsResponse `json:"overall"`
				}

				type sessionResponse struct {
					Start       playerDataResponse `json:"start"`
					End         playerDataResponse `json:"end"`
					Consecutive bool               `json:"consecutive"`
				}

				pitStatsToResponse := func(stats domain.GamemodeStatsPIT) statsResponse {
					return statsResponse{
						Winstreak:   stats.Winstreak,
						GamesPlayed: stats.GamesPlayed,
						Wins:        stats.Wins,
						Losses:      stats.Losses,
						BedsBroken:  stats.BedsBroken,
						BedsLost:    stats.BedsLost,
						FinalKills:  stats.FinalKills,
						FinalDeaths: stats.FinalDeaths,
						Kills:       stats.Kills,
						Deaths:      stats.Deaths,
					}
				}

				playerDataToResponse := func(data domain.PlayerPIT) playerDataResponse {
					return playerDataResponse{
						UUID:       data.UUID,
						QueriedAt:  data.QueriedAt,
						Experience: data.Experience,
						Solo:       pitStatsToResponse(data.Solo),
						Doubles:    pitStatsToResponse(data.Doubles),
						Threes:     pitStatsToResponse(data.Threes),
						Fours:      pitStatsToResponse(data.Fours),
						Overall:    pitStatsToResponse(data.Overall),
					}
				}

				responseData := make([]sessionResponse, 0, len(sessions))

				for _, session := range sessions {
					responseData = append(responseData, sessionResponse{
						Start:       playerDataToResponse(session.Start),
						End:         playerDataToResponse(session.End),
						Consecutive: session.Consecutive,
					})
				}

				marshalled, err := json.Marshal(responseData)
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
		middleware(
			server.MakeGetPlayerDataHandler(
				func(ctx context.Context, uuid string) ([]byte, int, error) {
					return getstats.GetOrCreateProcessedPlayerData(ctx, playerCache, hypixelAPI, persistor, uuid)
				},
			),
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
