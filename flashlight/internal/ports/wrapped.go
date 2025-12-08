package ports

import (
	"cmp"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strconv"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

type wrappedResponse struct {
	Success                bool                      `json:"success"`
	UUID                   string                    `json:"uuid,omitempty"`
	Year                   int                       `json:"year,omitempty"`
	TotalSessions          int                       `json:"totalSessions"`
	NonConsecutiveSessions int                       `json:"nonConsecutiveSessions"`
	YearStats              *yearBoundaryStatsRainbow `json:"yearStats,omitempty"`
	SessionStats           *sessionStats             `json:"sessionStats,omitempty"`
	Cause                  string                    `json:"cause,omitempty"`
}

// sessionStats contains statistics computed from consecutive sessions
// This field is only present when there is at least one consecutive session
type sessionStats struct {
	SessionLengths       sessionLengthStats        `json:"sessionLengths"`
	SessionsPerMonth     map[int]int               `json:"sessionsPerMonth"`
	BestSessions         bestSessionsStatsRainbow  `json:"bestSessions"`
	Averages             averageStats              `json:"averages"`
	Winstreaks           winstreakStats            `json:"winstreaks"`
	FinalKillStreaks     finalKillStreakStats      `json:"finalKillStreaks"`
	SessionCoverage      coverageStats             `json:"sessionCoverage"`
	FlawlessSessions     flawlessSessionStats      `json:"flawlessSessions"`
	PlaytimeDistribution playtimeDistributionStats `json:"playtimeDistribution"`
}

type sessionLengthStats struct {
	TotalHours    float64 `json:"totalHours"`
	LongestHours  float64 `json:"longestHours"`
	ShortestHours float64 `json:"shortestHours"`
	AverageHours  float64 `json:"averageHours"`
}

type sessionsPerMonth map[time.Month]int

func (s sessionsPerMonth) ToRainbow() map[int]int {
	intKeyed := make(map[int]int, len(s))
	for month, count := range s {
		intKeyed[int(month)] = count
	}
	return intKeyed
}

type bestSessionsStats struct {
	HighestFKDR       domain.Session
	MostKills         domain.Session
	MostFinalKills    domain.Session
	MostWins          domain.Session
	LongestSession    domain.Session
	MostWinsPerHour   *domain.Session
	MostFinalsPerHour *domain.Session
}

func (b bestSessionsStats) ToRainbow() bestSessionsStatsRainbow {
	toRnb := func(s *domain.Session) *rainbowSession {
		if s == nil {
			return nil
		}
		rs := sessionToRainbowSession(s)
		return &rs
	}
	return bestSessionsStatsRainbow{
		HighestFKDR:       *toRnb(&b.HighestFKDR),
		MostKills:         *toRnb(&b.MostKills),
		MostFinalKills:    *toRnb(&b.MostFinalKills),
		MostWins:          *toRnb(&b.MostWins),
		LongestSession:    *toRnb(&b.LongestSession),
		MostWinsPerHour:   toRnb(b.MostWinsPerHour),
		MostFinalsPerHour: toRnb(b.MostFinalsPerHour),
	}
}

type bestSessionsStatsRainbow struct {
	HighestFKDR       rainbowSession  `json:"highestFKDR"`
	MostKills         rainbowSession  `json:"mostKills"`
	MostFinalKills    rainbowSession  `json:"mostFinalKills"`
	MostWins          rainbowSession  `json:"mostWins"`
	LongestSession    rainbowSession  `json:"longestSession"`
	MostWinsPerHour   *rainbowSession `json:"mostWinsPerHour,omitempty"`
	MostFinalsPerHour *rainbowSession `json:"mostFinalsPerHour,omitempty"`
}

type averageStats struct {
	SessionLength float64 `json:"sessionLengthHours"`
	GamesPlayed   float64 `json:"gamesPlayed"`
	Wins          float64 `json:"wins"`
	FinalKills    float64 `json:"finalKills"`
}

type yearBoundaryStats struct {
	Start *domain.PlayerPIT
	End   *domain.PlayerPIT
}

func (y *yearBoundaryStats) ToRainbow() *yearBoundaryStatsRainbow {
	if y == nil {
		return nil
	}
	return &yearBoundaryStatsRainbow{
		Start: playerToRainbowPlayerDataPIT(y.Start),
		End:   playerToRainbowPlayerDataPIT(y.End),
	}
}

type yearBoundaryStatsRainbow struct {
	Start rainbowPlayerDataPIT `json:"start"`
	End   rainbowPlayerDataPIT `json:"end"`
}

type winstreakStats struct {
	Overall *gamemodeWinstreak `json:"overall,omitempty"`
	Solo    *gamemodeWinstreak `json:"solo,omitempty"`
	Doubles *gamemodeWinstreak `json:"doubles,omitempty"`
	Threes  *gamemodeWinstreak `json:"threes,omitempty"`
	Fours   *gamemodeWinstreak `json:"fours,omitempty"`
}

type gamemodeWinstreak struct {
	Highest int       `json:"highest"`
	When    time.Time `json:"when"`
}

type finalKillStreakStats struct {
	Overall *gamemodeFinalKillStreak `json:"overall,omitempty"`
	Solo    *gamemodeFinalKillStreak `json:"solo,omitempty"`
	Doubles *gamemodeFinalKillStreak `json:"doubles,omitempty"`
	Threes  *gamemodeFinalKillStreak `json:"threes,omitempty"`
	Fours   *gamemodeFinalKillStreak `json:"fours,omitempty"`
}

type gamemodeFinalKillStreak struct {
	Highest int       `json:"highest"`
	When    time.Time `json:"when"`
}

type coverageStats struct {
	GamesPlayedPercentage float64 `json:"gamesPlayedPercentage"`
	AdjustedTotalHours    float64 `json:"adjustedTotalHours"`
}

type flawlessSessionStats struct {
	Count      int     `json:"count"`
	Percentage float64 `json:"percentage"`
}

type playtimeDistributionStats struct {
	// HourlyDistribution: Array of 24 elements (index 0-23) for hours in the specified timezone
	// Each element contains the total hours played during that hour
	HourlyDistribution [24]float64 `json:"hourlyDistribution"`

	// DayHourDistribution: Map from weekday name (e.g., "Monday", "Tuesday") to hourly distribution
	// Each value is an array of 24 elements (index 0-23) for hours on that day in the specified timezone
	// Keys are from time.Weekday.String(): "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"
	DayHourDistribution map[string][24]float64 `json:"dayHourDistribution"`
}

func MakeGetWrappedHandler(
	getPlayerPITs app.GetPlayerPITs,
	allowedOrigins *DomainSuffixes,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
) http.HandlerFunc {
	ipLimiter, _ := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(4),
		ratelimiting.BurstSize(240),
	)
	ipRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		ipLimiter,
		ratelimiting.IPKeyFunc,
	)
	userIDLimiter, _ := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(1),
		ratelimiting.BurstSize(60),
	)
	userIDRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		// NOTE: Rate limiting based on user controlled value
		userIDLimiter,
		ratelimiting.UserIDKeyFunc,
	)

	makeOnLimitExceeded := func(rateLimiter ratelimiting.RequestRateLimiter) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusTooManyRequests)
			w.Write([]byte(`{"success":false,"cause":"Rate limit exceeded"}`))
		}
	}

	middleware := ComposeMiddlewares(
		buildMetricsMiddleware("wrapped"),
		logging.NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		reporting.NewAddMetaMiddleware("wrapped"),
		BuildCORSMiddleware(allowedOrigins),
		NewRateLimitMiddleware(ipRateLimiter, makeOnLimitExceeded(ipRateLimiter)),
		NewRateLimitMiddleware(userIDRateLimiter, makeOnLimitExceeded(userIDRateLimiter)),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		rawUUID := r.PathValue("uuid")
		rawYear := r.PathValue("year")
		userID := r.Header.Get("X-User-Id")
		ctx = reporting.SetUserIDInContext(ctx, userID)
		if userID == "" {
			userID = "<missing>"
		}
		ctx = logging.AddMetaToContext(ctx,
			slog.String("userId", userID),
			slog.String("uuid", rawUUID),
			slog.String("year", rawYear),
		)

		ctx = reporting.AddExtrasToContext(ctx,
			map[string]string{
				"rawUUID": rawUUID,
				"year":    rawYear,
			},
		)

		uuid, err := strutils.NormalizeUUID(rawUUID)
		if err != nil {
			statusCode := http.StatusBadRequest
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(statusCode)
			w.Write([]byte(`{"success":false,"cause":"invalid uuid"}`))
			return
		}

		year, err := strconv.Atoi(rawYear)
		if err != nil || year < 2000 || year > 3000 {
			statusCode := http.StatusBadRequest
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(statusCode)
			w.Write([]byte(`{"success":false,"cause":"invalid year"}`))
			return
		}

		// Parse and validate timezone parameter (optional, defaults to UTC)
		timezoneStr := r.URL.Query().Get("timezone")
		if timezoneStr == "" {
			timezoneStr = "UTC"
		}
		location, err := time.LoadLocation(timezoneStr)
		if err != nil {
			logging.FromContext(ctx).WarnContext(ctx, "Invalid timezone", "tzstring", timezoneStr, "err", err)
			statusCode := http.StatusBadRequest
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(statusCode)
			w.Write([]byte(`{"success":false,"cause":"invalid timezone"}`))
			return
		}
		ctx = logging.AddMetaToContext(ctx,
			slog.String("timezone", timezoneStr),
		)

		ctx = reporting.AddExtrasToContext(ctx, map[string]string{
			"uuid": uuid,
		})
		ctx = logging.AddMetaToContext(ctx,
			slog.String("normalizedUUID", uuid),
			slog.Int("parsedYear", year),
		)

		// NOTE: 24-hour padding to ensure we can complete sessions at year boundaries
		playerPITsStart := time.Date(year, 1, 1, 0, 0, 0, 0, time.UTC).Add(-24 * time.Hour)
		playerPITsEnd := time.Date(year+1, 1, 1, 0, 0, 0, 0, time.UTC).Add(-time.Nanosecond).Add(24 * time.Hour)
		playerPITs, err := getPlayerPITs(ctx, uuid, playerPITsStart, playerPITsEnd)
		if err != nil {
			// NOTE: GetPlayerPITs implementations handle their own error reporting
			statusCode := http.StatusInternalServerError
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(statusCode)
			w.Write([]byte(`{"success":false,"cause":"failed to get player data"}`))
			return
		}

		wrappedData := computeWrappedStats(ctx, playerPITs, year, location)
		wrappedData.Success = true
		wrappedData.UUID = uuid

		marshalled, err := json.Marshal(wrappedData)
		if err != nil {
			reporting.Report(ctx, fmt.Errorf("failed to marshal wrapped response: %w", err))
			statusCode := http.StatusInternalServerError
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(statusCode)
			w.Write([]byte(`{"success":false,"cause":"failed to marshal response"}`))
			return
		}

		logging.FromContext(ctx).InfoContext(ctx, "Returning wrapped data")

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(marshalled)
	}

	return middleware(handler)
}

func computeWrappedStats(ctx context.Context, playerPITs []domain.PlayerPIT, year int, location *time.Location) wrappedResponse {
	yearStart := time.Date(year, 1, 1, 0, 0, 0, 0, time.UTC)
	yearEnd := time.Date(year+1, 1, 1, 0, 0, 0, 0, time.UTC).Add(-time.Nanosecond)
	sessions := app.ComputeSessions(ctx, playerPITs, yearStart, yearEnd)

	// Filter to consecutive sessions only
	consecutiveSessions := make([]domain.Session, 0, len(sessions))
	nonConsecutiveCount := 0

	for _, session := range sessions {
		if session.Consecutive {
			consecutiveSessions = append(consecutiveSessions, session)
		} else {
			nonConsecutiveCount++
		}
	}

	yearBoundaryStats := computeYearBoundaryStats(ctx, playerPITs, year)

	response := wrappedResponse{
		Year:                   year,
		TotalSessions:          len(consecutiveSessions),
		NonConsecutiveSessions: nonConsecutiveCount,
		YearStats:              yearBoundaryStats.ToRainbow(),
	}

	if len(consecutiveSessions) == 0 {
		return response
	}

	sessionLengths := computeSessionLengths(ctx, consecutiveSessions)

	// Compute all session-dependent statistics
	response.SessionStats = &sessionStats{
		SessionLengths:       sessionLengths,
		SessionsPerMonth:     computeSessionsPerMonth(ctx, consecutiveSessions, year).ToRainbow(),
		BestSessions:         computeBestSessions(ctx, consecutiveSessions).ToRainbow(),
		Averages:             computeAverages(ctx, consecutiveSessions),
		Winstreaks:           computeWinstreaks(ctx, playerPITs),
		FinalKillStreaks:     computeFinalKillStreaks(ctx, playerPITs),
		SessionCoverage:      computeCoverage(ctx, consecutiveSessions, yearBoundaryStats, sessionLengths.TotalHours),
		FlawlessSessions:     computeFlawlessSessions(ctx, consecutiveSessions),
		PlaytimeDistribution: computePlaytimeDistribution(ctx, consecutiveSessions, location),
	}

	return response
}

// computeSessionLengths calculates session length statistics
// Assumes at least one session exists
func computeSessionLengths(ctx context.Context, sessions []domain.Session) sessionLengthStats {
	var total, longest, shortest float64
	shortest = -1

	for _, session := range sessions {
		duration := session.End.QueriedAt.Sub(session.Start.QueriedAt).Hours()
		total += duration
		if duration > longest {
			longest = duration
		}
		if shortest < 0 || duration < shortest {
			shortest = duration
		}
	}

	return sessionLengthStats{
		TotalHours:    total,
		LongestHours:  longest,
		ShortestHours: shortest,
		AverageHours:  total / float64(len(sessions)),
	}
}

func computeSessionsPerMonth(ctx context.Context, sessions []domain.Session, year int) sessionsPerMonth {
	counts := make(map[time.Month]int, 12)

	for _, session := range sessions {
		month := session.Start.QueriedAt.Month()

		if session.Start.QueriedAt.Year() != year {
			// This session started in a different year
			// If it is a session started december last year and ending january this year, count it for january
			if session.End.QueriedAt.Year() != year ||
				session.Start.QueriedAt.Month() != time.December ||
				session.End.QueriedAt.Month() != time.January {
				continue
			}

			month = session.End.QueriedAt.Month()
		}

		counts[month]++
	}

	return counts
}

func maxSession[T cmp.Ordered](sessions []domain.Session, getValue func(*domain.Session) T, include func(*domain.Session) bool) *domain.Session {
	var bestSession *domain.Session
	var bestValue T

	for i := range sessions {
		session := &sessions[i]
		if include != nil && !include(session) {
			continue
		}
		value := getValue(session)
		if bestSession == nil || value > bestValue {
			bestSession = session
			bestValue = value
		}
	}

	return bestSession
}

// Assumes at least one session exists
func computeBestSessions(ctx context.Context, sessions []domain.Session) bestSessionsStats {
	minSessionDuration := 15 * time.Minute
	minWins := 2
	minFinals := 10

	bestKills := maxSession(sessions, func(s *domain.Session) int {
		return s.End.Overall.Kills - s.Start.Overall.Kills
	}, nil)
	bestFinals := maxSession(sessions, func(s *domain.Session) int {
		return s.End.Overall.FinalKills - s.Start.Overall.FinalKills
	}, nil)
	bestWins := maxSession(sessions, func(s *domain.Session) int {
		return s.End.Overall.Wins - s.Start.Overall.Wins
	}, nil)
	bestLongest := maxSession(sessions, func(s *domain.Session) time.Duration {
		return s.End.QueriedAt.Sub(s.Start.QueriedAt)
	}, nil)
	bestFKDR := maxSession(sessions, func(s *domain.Session) float64 {
		finals := s.End.Overall.FinalKills - s.Start.Overall.FinalKills
		deaths := s.End.Overall.FinalDeaths - s.Start.Overall.FinalDeaths

		// If no final deaths, use final kills as FKDR
		fkdr := float64(finals)
		if deaths > 0 {
			fkdr = float64(finals) / float64(deaths)
		}
		return fkdr
	}, nil)
	bestWinsPerHour := maxSession(sessions, func(s *domain.Session) float64 {
		duration := s.End.QueriedAt.Sub(s.Start.QueriedAt)
		durationHours := duration.Hours()
		wins := s.End.Overall.Wins - s.Start.Overall.Wins
		return float64(wins) / durationHours
	}, func(s *domain.Session) bool {
		duration := s.End.QueriedAt.Sub(s.Start.QueriedAt)
		wins := s.End.Overall.Wins - s.Start.Overall.Wins
		return duration >= minSessionDuration && wins >= minWins
	})
	bestFinalsPerHour := maxSession(sessions, func(s *domain.Session) float64 {
		duration := s.End.QueriedAt.Sub(s.Start.QueriedAt)
		durationHours := duration.Hours()
		finals := s.End.Overall.FinalKills - s.Start.Overall.FinalKills
		return float64(finals) / durationHours
	}, func(s *domain.Session) bool {
		duration := s.End.QueriedAt.Sub(s.Start.QueriedAt)
		finals := s.End.Overall.FinalKills - s.Start.Overall.FinalKills
		return duration >= minSessionDuration && finals >= minFinals
	})

	return bestSessionsStats{
		HighestFKDR:       *bestFKDR,
		MostKills:         *bestKills,
		MostFinalKills:    *bestFinals,
		MostWins:          *bestWins,
		LongestSession:    *bestLongest,
		MostWinsPerHour:   bestWinsPerHour,
		MostFinalsPerHour: bestFinalsPerHour,
	}
}

// computeAverages calculates average statistics across all sessions
// Assumes at least one session exists
func computeAverages(ctx context.Context, sessions []domain.Session) averageStats {
	var totalDuration float64
	var totalGames, totalWins, totalFinalKills int

	for _, session := range sessions {
		duration := session.End.QueriedAt.Sub(session.Start.QueriedAt).Hours()
		totalDuration += duration
		totalGames += session.End.Overall.GamesPlayed - session.Start.Overall.GamesPlayed
		totalWins += session.End.Overall.Wins - session.Start.Overall.Wins
		totalFinalKills += session.End.Overall.FinalKills - session.Start.Overall.FinalKills
	}

	numSessions := float64(len(sessions))
	return averageStats{
		SessionLength: totalDuration / numSessions,
		GamesPlayed:   float64(totalGames) / numSessions,
		Wins:          float64(totalWins) / numSessions,
		FinalKills:    float64(totalFinalKills) / numSessions,
	}
}

// computeYearBoundaryStats finds the first and last player stats in the year
func computeYearBoundaryStats(ctx context.Context, playerPITs []domain.PlayerPIT, year int) *yearBoundaryStats {
	if len(playerPITs) == 0 {
		return nil
	}

	yearStart := time.Date(year, 1, 1, 0, 0, 0, 0, time.UTC)
	yearEnd := time.Date(year+1, 1, 1, 0, 0, 0, 0, time.UTC).Add(-time.Nanosecond)

	var firstPIT, lastPIT *domain.PlayerPIT

	for i := range playerPITs {
		pit := &playerPITs[i]
		if pit.QueriedAt.Before(yearStart) || pit.QueriedAt.After(yearEnd) {
			continue
		}

		if firstPIT == nil || pit.QueriedAt.Before(firstPIT.QueriedAt) {
			firstPIT = pit
		}
		if lastPIT == nil || pit.QueriedAt.After(lastPIT.QueriedAt) {
			lastPIT = pit
		}
	}

	if firstPIT == nil && lastPIT == nil {
		return nil
	}

	return &yearBoundaryStats{
		Start: firstPIT,
		End:   lastPIT,
	}
}

// computeWinstreaks calculates the highest ended winstreak for each gamemode during the year
// Assumes at least one playerPIT exists
func computeWinstreaks(ctx context.Context, playerPITs []domain.PlayerPIT) winstreakStats {
	result := winstreakStats{}

	// Helper to compute winstreak for a gamemode
	computeGamemodeWinstreak := func(getStats func(*domain.PlayerPIT) domain.GamemodeStatsPIT) *gamemodeWinstreak {
		firstPlayer := &playerPITs[0]
		firstStats := getStats(firstPlayer)

		maxEndedStreak := 0
		maxStreakLastHeld := firstPlayer.QueriedAt

		currentStreak := 0
		prevWins := firstStats.Wins
		prevLosses := firstStats.Losses
		prevQueriedAt := firstPlayer.QueriedAt

		for i := range playerPITs {
			pit := &playerPITs[i]
			stats := getStats(pit)

			wins := stats.Wins
			losses := stats.Losses

			winsGained := wins - prevWins
			lossesGained := losses - prevLosses

			if lossesGained > 0 {
				// Streak broken

				// Don't count ongoing streaks
				if currentStreak > maxEndedStreak {
					maxEndedStreak = currentStreak
					maxStreakLastHeld = prevQueriedAt
				}

				currentStreak = 0
			} else if winsGained > 0 {
				// Streak continues/starts
				currentStreak += winsGained
			}

			prevWins = wins
			prevLosses = losses
			prevQueriedAt = pit.QueriedAt
		}

		return &gamemodeWinstreak{
			Highest: maxEndedStreak,
			When:    maxStreakLastHeld,
		}
	}

	result.Overall = computeGamemodeWinstreak(func(p *domain.PlayerPIT) domain.GamemodeStatsPIT { return p.Overall })
	result.Solo = computeGamemodeWinstreak(func(p *domain.PlayerPIT) domain.GamemodeStatsPIT { return p.Solo })
	result.Doubles = computeGamemodeWinstreak(func(p *domain.PlayerPIT) domain.GamemodeStatsPIT { return p.Doubles })
	result.Threes = computeGamemodeWinstreak(func(p *domain.PlayerPIT) domain.GamemodeStatsPIT { return p.Threes })
	result.Fours = computeGamemodeWinstreak(func(p *domain.PlayerPIT) domain.GamemodeStatsPIT { return p.Fours })

	return result
}

// computeFinalKillStreaks calculates the highest final kill streak for each gamemode during the year
// Assumes at least one playerPIT exists
func computeFinalKillStreaks(ctx context.Context, playerPITs []domain.PlayerPIT) finalKillStreakStats {
	result := finalKillStreakStats{}

	// Helper to compute final kill streak for a gamemode
	computeGamemodeFKStreak := func(getStats func(*domain.PlayerPIT) domain.GamemodeStatsPIT) *gamemodeFinalKillStreak {
		firstPlayer := &playerPITs[0]
		firstStats := getStats(firstPlayer)

		maxEndedStreak := 0
		maxStreakEndedAt := firstPlayer.QueriedAt

		currentStreak := 0
		prevFKills := firstStats.FinalKills
		prevFDeaths := firstStats.FinalDeaths
		prevQueriedAt := firstPlayer.QueriedAt

		for i := range playerPITs {
			pit := &playerPITs[i]
			stats := getStats(pit)

			fkills := stats.FinalKills
			fdeaths := stats.FinalDeaths

			fkillsGained := fkills - prevFKills
			fdeathsGained := fdeaths - prevFDeaths

			if fdeathsGained > 0 {
				// Streak broken

				// Don't count ongoing streaks
				if currentStreak > maxEndedStreak {
					maxEndedStreak = currentStreak
					maxStreakEndedAt = prevQueriedAt
				}

				currentStreak = 0
			} else if fkillsGained > 0 {
				// Streak continues/starts
				currentStreak += fkillsGained
			}

			prevFKills = fkills
			prevFDeaths = fdeaths
			prevQueriedAt = pit.QueriedAt
		}

		return &gamemodeFinalKillStreak{
			Highest: maxEndedStreak,
			When:    maxStreakEndedAt,
		}
	}

	result.Overall = computeGamemodeFKStreak(func(p *domain.PlayerPIT) domain.GamemodeStatsPIT { return p.Overall })
	result.Solo = computeGamemodeFKStreak(func(p *domain.PlayerPIT) domain.GamemodeStatsPIT { return p.Solo })
	result.Doubles = computeGamemodeFKStreak(func(p *domain.PlayerPIT) domain.GamemodeStatsPIT { return p.Doubles })
	result.Threes = computeGamemodeFKStreak(func(p *domain.PlayerPIT) domain.GamemodeStatsPIT { return p.Threes })
	result.Fours = computeGamemodeFKStreak(func(p *domain.PlayerPIT) domain.GamemodeStatsPIT { return p.Fours })

	return result
}

// computeCoverage calculates what percentage of games played were covered by sessions
func computeCoverage(ctx context.Context, sessions []domain.Session, boundaryStats *yearBoundaryStats, totalHours float64) coverageStats {
	if boundaryStats == nil {
		return coverageStats{
			GamesPlayedPercentage: 0,
			AdjustedTotalHours:    totalHours,
		}
	}

	// Total games played in year
	totalGames := boundaryStats.End.Overall.GamesPlayed - boundaryStats.Start.Overall.GamesPlayed
	if totalGames <= 0 {
		return coverageStats{
			GamesPlayedPercentage: 0,
			AdjustedTotalHours:    totalHours,
		}
	}

	// Games covered by sessions
	sessionGames := 0
	for _, session := range sessions {
		sessionGames += session.End.Overall.GamesPlayed - session.Start.Overall.GamesPlayed
	}

	coverage := float64(sessionGames) / float64(totalGames)

	if coverage == 0 {
		return coverageStats{
			GamesPlayedPercentage: 0,
			AdjustedTotalHours:    totalHours,
		}
	}

	// Adjust total session time based on coverage
	if coverage < 0 || coverage > 1 {
		// Invalid coverage, set to 100%
		coverage = 1
	}

	adjustedHours := totalHours / coverage

	return coverageStats{
		GamesPlayedPercentage: coverage * 100,
		AdjustedTotalHours:    adjustedHours,
	}
}

// computeFlawlessSessions counts sessions with no losses and no final deaths
// Assumes at least one session exists
func computeFlawlessSessions(ctx context.Context, sessions []domain.Session) flawlessSessionStats {
	flawlessCount := 0
	for _, session := range sessions {
		losses := session.End.Overall.Losses - session.Start.Overall.Losses
		finalDeaths := session.End.Overall.FinalDeaths - session.Start.Overall.FinalDeaths
		wins := session.End.Overall.Wins - session.Start.Overall.Wins
		if losses == 0 && finalDeaths == 0 && wins > 0 {
			flawlessCount++
		}
	}

	percentage := float64(flawlessCount) / float64(len(sessions)) * 100

	return flawlessSessionStats{
		Count:      flawlessCount,
		Percentage: percentage,
	}
}

// computePlaytimeDistribution calculates the distribution of playtime across hours and day-hours in the specified timezone
// Assumes at least one session exists
func computePlaytimeDistribution(ctx context.Context, sessions []domain.Session, location *time.Location) playtimeDistributionStats {
	var hourlyDistribution [24]float64
	dayHourDistribution := make(map[string][24]float64)
	for day := time.Sunday; day <= time.Saturday; day++ {
		dayHourDistribution[day.String()] = [24]float64{}
	}

	for _, session := range sessions {
		// Convert UTC times to the specified timezone
		start := session.Start.QueriedAt.In(location)
		end := session.End.QueriedAt.In(location)

		// Distribute session time across hour buckets
		currentTime := start
		for currentTime.Before(end) {
			hour := currentTime.Hour()
			weekdayName := currentTime.Weekday().String()

			// Calculate the end of the current hour
			nextHour := currentTime.Truncate(time.Hour).Add(time.Hour)

			// Determine how much time to add for this hour bucket
			var hoursToAdd float64
			if end.Before(nextHour) {
				// Session ends before the next hour boundary
				hoursToAdd = end.Sub(currentTime).Hours()
			} else {
				// Session continues into next hour
				hoursToAdd = nextHour.Sub(currentTime).Hours()
			}

			hourlyDistribution[hour] += hoursToAdd

			// Get or create the hourly distribution for this weekday
			dayHours := dayHourDistribution[weekdayName]
			dayHours[hour] += hoursToAdd
			dayHourDistribution[weekdayName] = dayHours

			// Move to the next hour boundary
			currentTime = nextHour
		}
	}

	return playtimeDistributionStats{
		HourlyDistribution:  hourlyDistribution,
		DayHourDistribution: dayHourDistribution,
	}
}
