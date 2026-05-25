package app

import (
	"context"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

// sessionAtBuffer is how far before and after the requested time we look
// for stats to compute the session over.
const sessionAtBuffer = 24 * time.Hour

// GameSegment is a stretch of a session bracketed by two player
// snapshots that saw game-relevant stat movement.
//
// Game is non-nil when the deltas attribute to exactly one game (one
// gamemode advanced by one, FD/BL within {0, 1}). It is nil when stats
// moved but couldn't be pinned to a single game — multi-game jumps,
// simultaneous mode advances, exp drift without games. Adjacent
// heartbeats are merged upstream, so a nil Game always spans the
// entire run of unattributable activity.
type GameSegment struct {
	Start domain.PlayerPIT
	End   domain.PlayerPIT
	Game  *domain.GameResult
}

// SessionAtResult is the result of GetSessionAt.
// Session is nil (and Games empty) if no session overlaps the requested time.
type SessionAtResult struct {
	Session *domain.Session
	Games   []GameSegment
}

type GetSessionAt = func(
	ctx context.Context,
	uuid string,
	at time.Time,
) (SessionAtResult, error)

// BuildGetSessionAt constructs a GetSessionAt that fetches the player's
// stats in a window around the requested time (which transparently
// updates the player's data via UpdatePlayerInInterval inside
// GetPlayerPITs), computes the session that brackets the time, and
// derives the per-game segments inside that session.
func BuildGetSessionAt(
	getPlayerPITs GetPlayerPITs,
	computeSessions ComputeSessions,
) GetSessionAt {
	return func(ctx context.Context, uuid string, at time.Time) (SessionAtResult, error) {
		if !strutils.UUIDIsNormalized(uuid) {
			err := fmt.Errorf("UUID is not normalized")
			reporting.Report(ctx, err)
			return SessionAtResult{}, err
		}

		fetchStart := at.Add(-sessionAtBuffer)
		fetchEnd := at.Add(sessionAtBuffer)

		// GetPlayerPITs also runs UpdatePlayerInInterval so the buffered
		// window is freshly populated before we read it.
		stats, err := getPlayerPITs(ctx, uuid, fetchStart, fetchEnd)
		if err != nil {
			// NOTE: GetPlayerPITs implementations handle their own error reporting
			return SessionAtResult{}, fmt.Errorf("failed to get player pits: %w", err)
		}

		sessions := computeSessions(ctx, stats, fetchStart, fetchEnd)

		var session *domain.Session
		for i := range sessions {
			s := &sessions[i]
			// Remove microseconds: stored in the DB, but not passed by the caller
			startMs := s.Start.QueriedAt.Truncate(time.Millisecond)

			endMs := s.End.QueriedAt
			if s.Ongoing {
				// Ongoing means a fresh stat could still extend the
				// session up to End + sessionInactivityThreshold, so the
				// bracket extends to cover that window. Without this, a
				// caller asking for `at = now` would miss a session whose
				// last snapshot just happened.
				endMs = endMs.Add(sessionInactivityThreshold)
			}

			if !endMs.Before(at) && !startMs.After(at) {
				session = s
				break
			}
		}

		if session == nil {
			return SessionAtResult{Session: nil, Games: nil}, nil
		}

		// If the computed session hugs either buffer edge, it may extend
		// past the window we fetched and we'd be returning partial data.
		// Surface that as a non-fatal report — the caller still gets
		// whatever session we did manage to compute.
		const grace = 1 * time.Hour
		if session.Start.QueriedAt.Sub(fetchStart) < grace {
			reporting.Report(ctx,
				fmt.Errorf("session start within %s of fetch-start, session may be truncated", grace),
				map[string]string{
					"sessionStart": session.Start.QueriedAt.Format(time.RFC3339),
					"fetchStart":   fetchStart.Format(time.RFC3339),
				},
			)
		}
		if fetchEnd.Sub(session.End.QueriedAt) < grace {
			reporting.Report(ctx,
				fmt.Errorf("session end within %s of fetch-end, session may be truncated", grace),
				map[string]string{
					"sessionEnd": session.End.QueriedAt.Format(time.RFC3339),
					"fetchEnd":   fetchEnd.Format(time.RFC3339),
				},
			)
		}

		// Filter down to stats within the session window
		windowed := make([]domain.PlayerPIT, 0, len(stats))
		for _, stat := range stats {
			if stat.QueriedAt.Before(session.Start.QueriedAt) || stat.QueriedAt.After(session.End.QueriedAt) {
				continue
			}
			windowed = append(windowed, stat)
		}

		if len(windowed) < 2 {
			// Unreachable - a session must have at least two stats
			err := fmt.Errorf("session has fewer than 2 stats in window, cannot compute game segments")
			reporting.Report(ctx, err, map[string]string{
				"sessionStart": session.Start.QueriedAt.Format(time.RFC3339),
				"sessionEnd":   session.End.QueriedAt.Format(time.RFC3339),
				"statsCount":   fmt.Sprintf("%d", len(windowed)),
			})
			return SessionAtResult{}, err
		}

		// Add segments for each adjacent pair of stats, then merge consecutive
		// non-game stats. Filter out stats that don't move Experience or GamesPlayed.
		games := make([]GameSegment, 0, len(windowed)-1)
		prev := windowed[0]
		for _, curr := range windowed[1:] {
			if prev.Experience == curr.Experience &&
				prev.Overall.GamesPlayed == curr.Overall.GamesPlayed {
				prev = curr
				continue
			}
			seg := buildGameSegment(ctx, prev, curr)
			if seg.Game == nil && len(games) > 0 && games[len(games)-1].Game == nil {
				games[len(games)-1].End = curr
			} else {
				games = append(games, seg)
			}
			prev = curr
		}

		return SessionAtResult{Session: session, Games: games}, nil
	}
}

func gamesPlayedDelta(prev, curr domain.GamemodeStatsPIT) int {
	return curr.GamesPlayed - prev.GamesPlayed
}

// Return a GameSegment for the stretch between prev and curr
// Game is populated if the stretch can be attributed to a single game
// and nil otherwise (multiple games, no games, strange cases, ...)
func buildGameSegment(ctx context.Context, prev, curr domain.PlayerPIT) GameSegment {
	seg := GameSegment{Start: prev, End: curr, Game: nil}

	var gamemode domain.Gamemode
	var prevStats, currStats *domain.GamemodeStatsPIT
	switch {
	case gamesPlayedDelta(prev.Overall, curr.Overall) != 1:
		// Games played must advance by exactly one for it to be a game.
		return seg
	case gamesPlayedDelta(prev.Solo, curr.Solo) == 1:
		gamemode = domain.GamemodeSolo
		prevStats = &prev.Solo
		currStats = &curr.Solo
	case gamesPlayedDelta(prev.Doubles, curr.Doubles) == 1:
		gamemode = domain.GamemodeDoubles
		prevStats = &prev.Doubles
		currStats = &curr.Doubles
	case gamesPlayedDelta(prev.Threes, curr.Threes) == 1:
		gamemode = domain.GamemodeThrees
		prevStats = &prev.Threes
		currStats = &curr.Threes
	case gamesPlayedDelta(prev.Fours, curr.Fours) == 1:
		gamemode = domain.GamemodeFours
		prevStats = &prev.Fours
		currStats = &curr.Fours
	default:
		// unreachable
		reporting.Report(ctx,
			fmt.Errorf("overall games played advanced by 1 but no mode did"),
			map[string]string{
				"prevQueriedAt": prev.QueriedAt.Format(time.RFC3339),
				"currQueriedAt": curr.QueriedAt.Format(time.RFC3339),
			},
		)
		return seg
	}

	fdDelta := currStats.FinalDeaths - prevStats.FinalDeaths
	blDelta := currStats.BedsLost - prevStats.BedsLost

	// Handle weird stat deltas
	if fdDelta < 0 ||
		fdDelta > 1 ||
		blDelta < 0 ||
		blDelta > 1 {
		// unreachable
		reporting.Report(ctx,
			fmt.Errorf("weird FinalDeaths/BedsLost delta for single-game segment"),
			map[string]string{
				"prevQueriedAt": prev.QueriedAt.Format(time.RFC3339),
				"currQueriedAt": curr.QueriedAt.Format(time.RFC3339),
				"gamemode":      string(gamemode),
				"fdDelta":       fmt.Sprintf("%d", fdDelta),
				"blDelta":       fmt.Sprintf("%d", blDelta),
			},
		)
		return seg
	}

	seg.Game = &domain.GameResult{
		Gamemode:   gamemode,
		Won:        currStats.Wins > prevStats.Wins,
		FinalKills: currStats.FinalKills - prevStats.FinalKills,
		FinalDeath: fdDelta == 1,
		BedsBroken: currStats.BedsBroken - prevStats.BedsBroken,
		BedLost:    blDelta == 1,
		Kills:      currStats.Kills - prevStats.Kills,
		Deaths:     currStats.Deaths - prevStats.Deaths,
		Experience: curr.Experience - prev.Experience,
	}

	return seg
}
