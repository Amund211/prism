package ports

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

type rainbowGameResult struct {
	Gamemode   string `json:"gamemode"`
	Won        bool   `json:"won"`
	FinalKills int    `json:"finalKills"`
	FinalDeath bool   `json:"finalDeath"`
	BedsBroken int    `json:"bedsBroken"`
	BedLost    bool   `json:"bedLost"`
	Kills      int    `json:"kills"`
	Deaths     int    `json:"deaths"`
	Experience int64  `json:"experience"`
}

type rainbowGameSegment struct {
	Start rainbowPlayerDataPIT `json:"start"`
	End   rainbowPlayerDataPIT `json:"end"`
	// Game is nil when the snapshot pair represents more than one game
	// (gamesPlayed jumped >1, or multiple modes advanced).
	Game *rainbowGameResult `json:"game"`
}

type rainbowSessionAtResponse struct {
	Session *rainbowSession      `json:"session"`
	Games   []rainbowGameSegment `json:"games"`
}

func MakeGetSessionAtHandler(
	getSessionAt app.GetSessionAt,
	registerUserVisit app.RegisterUserVisit,
	allowedOrigins *DomainSuffixes,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
	blocklistConfig BlocklistConfig,
) http.HandlerFunc {
	ipLimiter, _ := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(4),
		ratelimiting.BurstSize(80),
	)
	ipRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		ipLimiter,
		IPHashKeyFunc,
	)
	userIDLimiter, _ := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(1),
		ratelimiting.BurstSize(20),
	)
	userIDRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		userIDLimiter,
		UserIDKeyFunc,
	)

	makeOnLimitExceeded := func(rateLimiter ratelimiting.RequestRateLimiter) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			ctx := r.Context()

			statusCode := http.StatusTooManyRequests

			logging.FromContext(ctx).InfoContext(ctx, "Rate limit exceeded", "statusCode", statusCode, "reason", "ratelimit exceeded", "key", rateLimiter.KeyFor(r))

			http.Error(w, "Rate limit exceeded", statusCode)
		}
	}

	middleware := ComposeMiddlewares(
		NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		BuildBlocklistMiddleware(blocklistConfig),
		buildMetricsMiddleware("session-at"),
		NewReportingMetaMiddleware("session-at"),
		BuildCORSMiddleware(allowedOrigins),
		NewRateLimitMiddleware(ipRateLimiter, makeOnLimitExceeded(ipRateLimiter)),
		NewRateLimitMiddleware(userIDRateLimiter, makeOnLimitExceeded(userIDRateLimiter)),
		BuildRegisterUserVisitMiddleware(registerUserVisit),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		defer r.Body.Close()
		body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 4<<10))
		if err != nil {
			var maxBytesErr *http.MaxBytesError
			if errors.As(err, &maxBytesErr) {
				http.Error(w, "Request body too large", http.StatusRequestEntityTooLarge)
				return
			}
			reporting.Report(ctx, fmt.Errorf("failed to read request body: %w", err))
			http.Error(w, "Failed to read request body", http.StatusBadRequest)
			return
		}
		request := struct {
			UUID string    `json:"uuid"`
			Time time.Time `json:"time"`
		}{}
		err = json.Unmarshal(body, &request)
		if err != nil {
			reporting.Report(ctx, fmt.Errorf("failed to parse request body: %w", err))
			http.Error(w, "Failed to parse request body", http.StatusBadRequest)
			return
		}

		ctx = reporting.AddExtrasToContext(ctx, map[string]string{
			"time": request.Time.Format(time.RFC3339),
		})

		uuid, err := strutils.NormalizeUUID(request.UUID)
		if err != nil {
			reporting.Report(ctx, fmt.Errorf("failed to normalize uuid: %w", err), map[string]string{
				"rawUUID": request.UUID,
			})
			http.Error(w, "invalid uuid", http.StatusBadRequest)
			return
		}

		if request.Time.IsZero() {
			http.Error(w, "missing time", http.StatusBadRequest)
			return
		}

		ctx = reporting.AddExtrasToContext(ctx, map[string]string{
			"uuid": uuid,
		})
		ctx = logging.AddMetaToContext(ctx,
			slog.String("uuid", uuid),
			slog.String("time", request.Time.Format(time.RFC3339)),
		)

		result, err := getSessionAt(ctx, uuid, request.Time)
		if err != nil {
			// NOTE: GetSessionAt implementations handle their own error reporting
			http.Error(w, "Failed to get session", http.StatusInternalServerError)
			return
		}

		response := rainbowSessionAtResponse{
			Session: nil,
			Games:   make([]rainbowGameSegment, 0, len(result.Games)),
		}
		if result.Session != nil {
			rbSession := sessionToRainbowSession(result.Session)
			response.Session = &rbSession
		}
		for _, seg := range result.Games {
			var game *rainbowGameResult
			if seg.Game != nil {
				rainbowGamemode, gErr := gamemodeToRainbowGamemode(seg.Game.Gamemode)
				if gErr != nil {
					reporting.Report(ctx, fmt.Errorf("failed to convert gamemode: %w", gErr))
					http.Error(w, "Failed to serialise response", http.StatusInternalServerError)
					return
				}
				game = &rainbowGameResult{
					Gamemode:   rainbowGamemode,
					Won:        seg.Game.Won,
					FinalKills: seg.Game.FinalKills,
					FinalDeath: seg.Game.FinalDeath,
					BedsBroken: seg.Game.BedsBroken,
					BedLost:    seg.Game.BedLost,
					Kills:      seg.Game.Kills,
					Deaths:     seg.Game.Deaths,
					Experience: seg.Game.Experience,
				}
			}
			response.Games = append(response.Games, rainbowGameSegment{
				Start: playerToRainbowPlayerDataPIT(&seg.Start),
				End:   playerToRainbowPlayerDataPIT(&seg.End),
				Game:  game,
			})
		}

		marshalled, err := json.Marshal(response)
		if err != nil {
			reporting.Report(ctx, fmt.Errorf("failed to marshal response: %w", err))
			http.Error(w, "Failed to marshal response", http.StatusInternalServerError)
			return
		}

		logging.FromContext(ctx).InfoContext(ctx, "Returning session at",
			"hasSession", result.Session != nil,
			"gamesLength", len(response.Games),
		)

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(marshalled)
	}

	return middleware(handler)
}
