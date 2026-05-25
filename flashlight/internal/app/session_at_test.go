package app_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
)

func TestBuildGetSessionAt(t *testing.T) {
	t.Parallel()

	uuid := "01234567-89ab-cdef-0123-456789abcdef"
	at := time.Date(2024, 6, 15, 20, 30, 0, 0, time.UTC)

	// fixedStats hands the configured PIT slice straight to the
	// caller. Sessions are computed by the real BuildComputeSessions so
	// these tests exercise the real boundary/Ongoing logic end-to-end.
	fixedStats := func(stats []domain.PlayerPIT) app.GetPlayerPITs {
		return func(ctx context.Context, _ string, _, _ time.Time) ([]domain.PlayerPIT, error) {
			return stats, nil
		}
	}
	// nowFarFuture pushes ComputeSessions's `now` past every test's
	// data so sessions are never flagged Ongoing. The two ongoing-
	// specific tests build their own ComputeSessions inline with a
	// `now` inside the inactivity buffer of the last stat.
	nowFarFuture := func() time.Time { return at.Add(365 * 24 * time.Hour) }
	computeSessions := app.BuildComputeSessions(nowFarFuture)

	t.Run("fetches stats ±24h around the requested time", func(t *testing.T) {
		t.Parallel()

		var gotUUID string
		var gotStart, gotEnd time.Time
		getPlayerPITs := func(ctx context.Context, u string, start, end time.Time) ([]domain.PlayerPIT, error) {
			gotUUID = u
			gotStart = start
			gotEnd = end
			return nil, nil
		}
		getSessionAt := app.BuildGetSessionAt(getPlayerPITs, computeSessions)

		result, err := getSessionAt(t.Context(), uuid, at)
		require.NoError(t, err)
		require.Equal(t, app.SessionAtResult{}, result)
		require.Equal(t, uuid, gotUUID)
		require.Equal(t, at.Add(-24*time.Hour), gotStart)
		require.Equal(t, at.Add(24*time.Hour), gotEnd)
	})

	t.Run("derives one game per snapshot pair when a single mode advanced by one", func(t *testing.T) {
		t.Parallel()

		// Three doubles games over four snapshots.
		b := domaintest.NewPlayerBuilder(uuid).
			WithExperience(1000).FromDB().
			Doubles().
			WithGamesPlayed(10).WithWins(5).WithLosses(5).
			WithBedsBroken(4).WithBedsLost(3).
			WithFinalKills(20).WithFinalDeaths(10).
			WithKills(50).WithDeaths(30)
		p0 := b.Build(at.Add(-30 * time.Minute))

		// doubles +1, won
		p1 := b.
			WithExperience(1300).
			Doubles().
			WithGamesPlayed(11).WithWins(6).
			WithBedsBroken(5).
			WithFinalKills(24).
			WithKills(58).WithDeaths(32).Build(at.Add(-15 * time.Minute))

		// doubles +1, lost, final-died, bed-lost
		p2 := b.
			WithExperience(1500).
			Doubles().
			WithGamesPlayed(12).WithLosses(6).
			WithBedsLost(4).
			WithFinalKills(26).WithFinalDeaths(11).
			WithKills(62).WithDeaths(36).Build(at.Add(15 * time.Minute))

		// doubles +1, won
		p3 := b.
			WithExperience(1800).
			Doubles().
			WithGamesPlayed(13).WithWins(7).
			WithBedsBroken(6).
			WithFinalKills(30).
			WithKills(70).WithDeaths(38).Build(at.Add(30 * time.Minute))

		getSessionAt := app.BuildGetSessionAt(
			fixedStats([]domain.PlayerPIT{p0, p1, p2, p3}),
			computeSessions,
		)

		result, err := getSessionAt(t.Context(), uuid, at)
		require.NoError(t, err)
		require.Equal(t, app.SessionAtResult{
			Session: &domain.Session{Start: p0, End: p3, Consecutive: true},
			Games: []app.GameSegment{
				{Start: p0, End: p1, Game: &domain.GameResult{
					Gamemode:   domain.GamemodeDoubles,
					Won:        true,
					FinalKills: 4,
					FinalDeath: false,
					BedsBroken: 1,
					BedLost:    false,
					Kills:      8,
					Deaths:     2,
					Experience: 300,
				}},
				{Start: p1, End: p2, Game: &domain.GameResult{
					Gamemode:   domain.GamemodeDoubles,
					Won:        false,
					FinalKills: 2,
					FinalDeath: true,
					BedsBroken: 0,
					BedLost:    true,
					Kills:      4,
					Deaths:     4,
					Experience: 200,
				}},
				{Start: p2, End: p3, Game: &domain.GameResult{
					Gamemode:   domain.GamemodeDoubles,
					Won:        true,
					FinalKills: 4,
					FinalDeath: false,
					BedsBroken: 1,
					BedLost:    false,
					Kills:      8,
					Deaths:     2,
					Experience: 300,
				}},
			},
		}, result)
	})

	t.Run("Game is nil when GamesPlayed jumps by more than one in a single mode", func(t *testing.T) {
		t.Parallel()

		// Doubles jumps from 10 -> 12 between snapshots — two games at once,
		// can't be split, so Game should be nil but the segment still emitted.
		b := domaintest.NewPlayerBuilder(uuid).
			WithExperience(1000).FromDB().
			Doubles().
			WithGamesPlayed(10).WithWins(5).WithLosses(5).
			WithBedsBroken(4).WithBedsLost(3).
			WithFinalKills(20).WithFinalDeaths(10).
			WithKills(50).WithDeaths(30)
		p0 := b.Build(at.Add(-15 * time.Minute))

		p1 := b.
			WithExperience(1600).
			Doubles().
			WithGamesPlayed(12).WithWins(6).WithLosses(6).
			WithBedsBroken(6).WithBedsLost(4).
			WithFinalKills(28).WithFinalDeaths(12).
			WithKills(66).WithDeaths(36).Build(at)

		getSessionAt := app.BuildGetSessionAt(
			fixedStats([]domain.PlayerPIT{p0, p1}),
			computeSessions,
		)

		result, err := getSessionAt(t.Context(), uuid, at)
		require.NoError(t, err)
		require.Equal(t, app.SessionAtResult{
			Session: &domain.Session{Start: p0, End: p1, Consecutive: true},
			Games: []app.GameSegment{
				{Start: p0, End: p1, Game: nil},
			},
		}, result)
	})

	t.Run("Game is nil when multiple modes advanced between the same snapshot pair", func(t *testing.T) {
		t.Parallel()

		// Both solo AND doubles each advanced by 1 — ambiguous.
		b := domaintest.NewPlayerBuilder(uuid).
			WithExperience(1000).FromDB().
			Solo().
			WithGamesPlayed(5).WithWins(2).WithLosses(3).
			WithBedsBroken(2).WithBedsLost(1).
			WithFinalKills(10).WithFinalDeaths(5).
			WithKills(20).WithDeaths(12).
			Doubles().
			WithGamesPlayed(10).WithWins(5).WithLosses(5).
			WithBedsBroken(4).WithBedsLost(3).
			WithFinalKills(20).WithFinalDeaths(10).
			WithKills(50).WithDeaths(30)
		p0 := b.Build(at.Add(-15 * time.Minute))

		p1 := b.
			WithExperience(1500).
			Solo().
			WithGamesPlayed(6).WithWins(3).
			WithBedsBroken(3).
			WithFinalKills(12).
			WithKills(24).WithDeaths(13).
			Doubles().
			WithGamesPlayed(11).WithLosses(6).
			WithBedsLost(4).
			WithFinalKills(22).WithFinalDeaths(11).
			WithKills(54).WithDeaths(33).Build(at)

		getSessionAt := app.BuildGetSessionAt(
			fixedStats([]domain.PlayerPIT{p0, p1}),
			computeSessions,
		)

		result, err := getSessionAt(t.Context(), uuid, at)
		require.NoError(t, err)
		require.Equal(t, app.SessionAtResult{
			Session: &domain.Session{Start: p0, End: p1, Consecutive: true},
			Games: []app.GameSegment{
				{Start: p0, End: p1, Game: nil},
			},
		}, result)
	})

	t.Run("blocks of identical-stat snapshots between games yield one segment per game", func(t *testing.T) {
		t.Parallel()

		// Four blocks of three identical snapshots, one won doubles game
		// between each adjacent pair of blocks. ComputeSessions trims
		// the leading and trailing idle blocks to {p2, p9}; session_at
		// must still collapse the middle blocks so the output is one
		// segment per real game. Wins progress 10→11→12→13 across the
		// four blocks. Stats span across `at` so the resulting session
		// brackets it.
		b := domaintest.NewPlayerBuilder(uuid).
			WithExperience(1000).FromDB().
			Doubles().
			WithGamesPlayed(15).WithWins(10).WithLosses(5).
			WithBedsBroken(6).WithBedsLost(2).
			WithFinalKills(30).WithFinalDeaths(8).
			WithKills(50).WithDeaths(20)

		// Block 1
		p0 := b.Build(at.Add(-8 * time.Minute))
		p1 := b.Build(at.Add(-7 * time.Minute))
		p2 := b.Build(at.Add(-6 * time.Minute))

		// Block 2: won doubles game
		b.WithExperience(1300).
			Doubles().
			WithGamesPlayed(16).WithWins(11).
			WithBedsBroken(7).
			WithFinalKills(34).
			WithKills(60).WithDeaths(22)
		p3 := b.Build(at.Add(-5 * time.Minute))
		p4 := b.Build(at.Add(-4 * time.Minute))
		p5 := b.Build(at.Add(-3 * time.Minute))

		// Block 3: won doubles game
		b.WithExperience(1600).
			Doubles().
			WithGamesPlayed(17).WithWins(12).
			WithBedsBroken(8).
			WithFinalKills(38).
			WithKills(70).WithDeaths(24)
		p6 := b.Build(at.Add(-2 * time.Minute))
		p7 := b.Build(at.Add(-1 * time.Minute))
		p8 := b.Build(at)

		// Block 4: won doubles game
		b.WithExperience(1900).
			Doubles().
			WithGamesPlayed(18).WithWins(13).
			WithBedsBroken(9).
			WithFinalKills(42).
			WithKills(80).WithDeaths(26)
		p9 := b.Build(at.Add(1 * time.Minute))
		p10 := b.Build(at.Add(2 * time.Minute))
		p11 := b.Build(at.Add(3 * time.Minute))

		getSessionAt := app.BuildGetSessionAt(
			fixedStats([]domain.PlayerPIT{p0, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11}),
			computeSessions,
		)

		wonGame := &domain.GameResult{
			Gamemode:   domain.GamemodeDoubles,
			Won:        true,
			FinalKills: 4,
			FinalDeath: false,
			BedsBroken: 1,
			BedLost:    false,
			Kills:      10,
			Deaths:     2,
			Experience: 300,
		}

		result, err := getSessionAt(t.Context(), uuid, at)
		require.NoError(t, err)
		require.Equal(t, app.SessionAtResult{
			Session: &domain.Session{Start: p2, End: p9, Consecutive: true},
			Games: []app.GameSegment{
				{Start: p2, End: p3, Game: wonGame},
				{Start: p5, End: p6, Game: wonGame},
				{Start: p8, End: p9, Game: wonGame},
			},
		}, result)
	})

	t.Run("two adjacent +2-games pairs merge into a single heartbeat segment", func(t *testing.T) {
		t.Parallel()

		// Each adjacent pair shows gamesPlayed jumping by 2 — both
		// produce a Game=nil segment. Output should be a single merged
		// heartbeat spanning all three snapshots, not two heartbeats in
		// a row.
		b := domaintest.NewPlayerBuilder(uuid).
			WithExperience(1000).FromDB().
			Doubles().
			WithGamesPlayed(10).WithWins(5).WithLosses(5).
			WithBedsBroken(4).WithBedsLost(3).
			WithFinalKills(20).WithFinalDeaths(10).
			WithKills(50).WithDeaths(30)
		p0 := b.Build(at.Add(-30 * time.Minute))

		p1 := b.
			WithExperience(1500).
			Doubles().
			WithGamesPlayed(12).WithWins(6).WithLosses(6).
			WithBedsBroken(5).WithBedsLost(4).
			WithFinalKills(26).WithFinalDeaths(11).
			WithKills(60).WithDeaths(34).Build(at.Add(-15 * time.Minute))

		p2 := b.
			WithExperience(2000).
			Doubles().
			WithGamesPlayed(14).WithWins(8).
			WithBedsBroken(6).WithBedsLost(5).
			WithFinalKills(32).WithFinalDeaths(12).
			WithKills(70).WithDeaths(38).Build(at)

		getSessionAt := app.BuildGetSessionAt(
			fixedStats([]domain.PlayerPIT{p0, p1, p2}),
			computeSessions,
		)

		result, err := getSessionAt(t.Context(), uuid, at)
		require.NoError(t, err)
		require.Equal(t, app.SessionAtResult{
			Session: &domain.Session{Start: p0, End: p2, Consecutive: true},
			Games: []app.GameSegment{
				{Start: p0, End: p2, Game: nil},
			},
		}, result)
	})

	t.Run("an ambiguous-stat pair next to a game does NOT merge", func(t *testing.T) {
		t.Parallel()

		// Pair 1: +1 game (clean game). Pair 2: +2 games (ambiguous
		// heartbeat). The heartbeat sits next to a game segment so the
		// merge rule does not apply — we get [game, heartbeat].
		b := domaintest.NewPlayerBuilder(uuid).
			WithExperience(1000).FromDB().
			Doubles().
			WithGamesPlayed(10).WithWins(5).WithLosses(5).
			WithBedsBroken(4).WithBedsLost(3).
			WithFinalKills(20).WithFinalDeaths(10).
			WithKills(50).WithDeaths(30)
		p0 := b.Build(at.Add(-30 * time.Minute))

		p1 := b.
			WithExperience(1300).
			Doubles().
			WithGamesPlayed(11).WithWins(6).
			WithBedsBroken(5).
			WithFinalKills(24).
			WithKills(58).WithDeaths(32).Build(at.Add(-15 * time.Minute))

		p2 := b.
			WithExperience(1800).
			Doubles().
			WithGamesPlayed(13).WithWins(7).WithLosses(6).
			WithBedsBroken(7).WithBedsLost(4).
			WithFinalKills(30).WithFinalDeaths(11).
			WithKills(70).WithDeaths(36).Build(at)

		getSessionAt := app.BuildGetSessionAt(
			fixedStats([]domain.PlayerPIT{p0, p1, p2}),
			computeSessions,
		)

		result, err := getSessionAt(t.Context(), uuid, at)
		require.NoError(t, err)
		require.Equal(t, app.SessionAtResult{
			Session: &domain.Session{Start: p0, End: p2, Consecutive: true},
			Games: []app.GameSegment{
				{Start: p0, End: p1, Game: &domain.GameResult{
					Gamemode:   domain.GamemodeDoubles,
					Won:        true,
					FinalKills: 4,
					FinalDeath: false,
					BedsBroken: 1,
					BedLost:    false,
					Kills:      8,
					Deaths:     2,
					Experience: 300,
				}},
				{Start: p1, End: p2, Game: nil},
			},
		}, result)
	})

	t.Run("experience moves but no game finishes — still a heartbeat", func(t *testing.T) {
		t.Parallel()

		// Experience drifted upward but no gamesPlayed changed in any
		// mode. That's the "almost-finished a game" or "weird tracker
		// state" case: we still owe the caller a segment so they know
		// something happened between these snapshots.
		b := domaintest.NewPlayerBuilder(uuid).
			WithExperience(1000).FromDB().
			Doubles().
			WithGamesPlayed(10).WithWins(5).WithLosses(5).
			WithBedsBroken(4).WithBedsLost(3).
			WithFinalKills(20).WithFinalDeaths(10).
			WithKills(50).WithDeaths(30)
		p0 := b.Build(at.Add(-30 * time.Minute))

		// experience drifts, no other stats change
		p1 := b.
			WithExperience(1200).Build(at.Add(-15 * time.Minute))

		// doubles +1, won
		p2 := b.
			WithExperience(1500).
			Doubles().
			WithGamesPlayed(11).WithWins(6).
			WithBedsBroken(5).
			WithFinalKills(24).
			WithKills(58).WithDeaths(32).Build(at)

		getSessionAt := app.BuildGetSessionAt(
			fixedStats([]domain.PlayerPIT{p0, p1, p2}),
			computeSessions,
		)

		result, err := getSessionAt(t.Context(), uuid, at)
		require.NoError(t, err)
		require.Equal(t, app.SessionAtResult{
			Session: &domain.Session{Start: p0, End: p2, Consecutive: true},
			Games: []app.GameSegment{
				{Start: p0, End: p1, Game: nil},
				{Start: p1, End: p2, Game: &domain.GameResult{
					Gamemode:   domain.GamemodeDoubles,
					Won:        true,
					FinalKills: 4,
					FinalDeath: false,
					BedsBroken: 1,
					BedLost:    false,
					Kills:      8,
					Deaths:     2,
					Experience: 300,
				}},
			},
		}, result)
	})

	t.Run("matches a session whose start sits within the same millisecond as `at`", func(t *testing.T) {
		t.Parallel()

		// Mirrors the production case: the DB stores PIT timestamps at
		// microsecond precision but `at` comes in from a URL that's been
		// round-tripped through Date.toISOString() (millisecond precision).
		// The session's start sits 726us after the user's `at`, but
		// truncated to ms they're identical.
		sessionStart := time.Date(2026, 5, 8, 19, 44, 37, 115_726_000, time.UTC)
		atFromURL := time.Date(2026, 5, 8, 19, 44, 37, 115_000_000, time.UTC)
		require.True(
			t,
			sessionStart.After(atFromURL),
			"sanity: session.start should be after `at` at us precision",
		)

		b := domaintest.NewPlayerBuilder(uuid).
			WithExperience(1000).FromDB().
			Doubles().
			WithGamesPlayed(10).WithWins(5).WithLosses(5).
			WithBedsBroken(4).WithBedsLost(3).
			WithFinalKills(20).WithFinalDeaths(10).
			WithKills(50).WithDeaths(30)
		p0 := b.Build(sessionStart)

		p1 := b.
			WithExperience(1300).
			Doubles().
			WithGamesPlayed(11).WithWins(6).
			WithBedsBroken(5).
			WithFinalKills(24).
			WithKills(58).WithDeaths(32).Build(sessionStart.Add(15 * time.Minute))

		getSessionAt := app.BuildGetSessionAt(
			fixedStats([]domain.PlayerPIT{p0, p1}),
			computeSessions,
		)

		result, err := getSessionAt(t.Context(), uuid, atFromURL)
		require.NoError(t, err)
		require.Equal(t, app.SessionAtResult{
			Session: &domain.Session{Start: p0, End: p1, Consecutive: true},
			Games: []app.GameSegment{
				{Start: p0, End: p1, Game: &domain.GameResult{
					Gamemode:   domain.GamemodeDoubles,
					Won:        true,
					FinalKills: 4,
					FinalDeath: false,
					BedsBroken: 1,
					BedLost:    false,
					Kills:      8,
					Deaths:     2,
					Experience: 300,
				}},
			},
		}, result)
	})

	t.Run("matches an ongoing session whose last snapshot is before `at`", func(t *testing.T) {
		t.Parallel()

		// Modelling: caller asks for `at = now`. The player's last
		// snapshot is 10 minutes before `at` and the session is still
		// within the 1h inactivity buffer, so ComputeSessions marks it
		// Ongoing. The bracket check should match it despite `at`
		// sitting past session.End.
		b := domaintest.NewPlayerBuilder(uuid).
			WithExperience(1000).FromDB().
			Doubles().
			WithGamesPlayed(10).WithWins(5).WithLosses(5).
			WithBedsBroken(4).WithBedsLost(3).
			WithFinalKills(20).WithFinalDeaths(10).
			WithKills(50).WithDeaths(30)
		p0 := b.Build(at.Add(-30 * time.Minute))

		p1 := b.
			WithExperience(1300).
			Doubles().
			WithGamesPlayed(11).WithWins(6).
			WithBedsBroken(5).
			WithFinalKills(24).
			WithKills(58).WithDeaths(32).Build(at.Add(-10 * time.Minute))

		// `now == at` puts ComputeSessions inside the inactivity buffer
		// of p1, so it marks the session Ongoing.
		nowAt := func() time.Time { return at }
		ongoingCompute := app.BuildComputeSessions(nowAt)
		getSessionAt := app.BuildGetSessionAt(
			fixedStats([]domain.PlayerPIT{p0, p1}),
			ongoingCompute,
		)

		result, err := getSessionAt(t.Context(), uuid, at)
		require.NoError(t, err)
		require.Equal(t, app.SessionAtResult{
			Session: &domain.Session{Start: p0, End: p1, Consecutive: true, Ongoing: true},
			Games: []app.GameSegment{
				{Start: p0, End: p1, Game: &domain.GameResult{
					Gamemode:   domain.GamemodeDoubles,
					Won:        true,
					FinalKills: 4,
					FinalDeath: false,
					BedsBroken: 1,
					BedLost:    false,
					Kills:      8,
					Deaths:     2,
					Experience: 300,
				}},
			},
		}, result)
	})

	t.Run("does not match an ongoing session past the inactivity buffer", func(t *testing.T) {
		t.Parallel()

		// `at` sits more than sessionInactivityThreshold (1h) past the
		// session's end. ComputeSessions's `now` is inside the buffer
		// so the session is Ongoing, but the bracket check must cap at
		// end + threshold and refuse to return a stale session.
		b := domaintest.NewPlayerBuilder(uuid).
			WithExperience(1000).FromDB().
			Doubles().
			WithGamesPlayed(10).WithWins(5).WithLosses(5).
			WithBedsBroken(4).WithBedsLost(3).
			WithFinalKills(20).WithFinalDeaths(10).
			WithKills(50).WithDeaths(30)
		p0 := b.Build(at.Add(-130 * time.Minute))

		p1 := b.
			WithExperience(1300).
			Doubles().
			WithGamesPlayed(11).WithWins(6).
			WithBedsBroken(5).
			WithFinalKills(24).
			WithKills(58).WithDeaths(32).Build(at.Add(-70 * time.Minute))

		// Put `now` 65 minutes before `at` so it sits inside [-130, -10]
		// — the Ongoing buffer for p1.
		nowBefore := func() time.Time { return at.Add(-65 * time.Minute) }
		ongoingCompute := app.BuildComputeSessions(nowBefore)
		getSessionAt := app.BuildGetSessionAt(
			fixedStats([]domain.PlayerPIT{p0, p1}),
			ongoingCompute,
		)

		result, err := getSessionAt(t.Context(), uuid, at)
		require.NoError(t, err)
		require.Equal(t, app.SessionAtResult{}, result)
	})

	t.Run("returns nil session and empty games when no session overlaps", func(t *testing.T) {
		t.Parallel()

		b := domaintest.NewPlayerBuilder(uuid).
			WithExperience(1000).FromDB().
			Doubles().
			WithGamesPlayed(10).WithWins(5).WithLosses(5).
			WithBedsBroken(4).WithBedsLost(3).
			WithFinalKills(20).WithFinalDeaths(10).
			WithKills(50).WithDeaths(30)
		p0 := b.Build(at.Add(-10 * time.Hour))

		p1 := b.
			WithExperience(1300).
			Doubles().
			WithGamesPlayed(11).WithWins(6).
			WithBedsBroken(5).
			WithFinalKills(24).
			WithKills(58).WithDeaths(32).Build(at.Add(-9 * time.Hour))

		getSessionAt := app.BuildGetSessionAt(
			fixedStats([]domain.PlayerPIT{p0, p1}),
			computeSessions,
		)

		result, err := getSessionAt(t.Context(), uuid, at)
		require.NoError(t, err)
		require.Equal(t, app.SessionAtResult{}, result)
	})

	t.Run("strange stats change -> game is nil", func(t *testing.T) {
		t.Run("FinalDeaths jumps by more than one between snapshots", func(t *testing.T) {
			t.Parallel()

			b := domaintest.NewPlayerBuilder(uuid).
				WithExperience(1000).FromDB().
				Doubles().
				WithGamesPlayed(10).WithWins(5).WithLosses(5).
				WithBedsBroken(4).WithBedsLost(3).
				WithFinalKills(20).WithFinalDeaths(10).
				WithKills(50).WithDeaths(30)
			p0 := b.Build(at.Add(-15 * time.Minute))

			// Doubles advances by exactly one game, but final deaths
			// jumped by 2 — impossible in a real game.
			p1 := b.
				WithExperience(1100).
				Doubles().
				WithGamesPlayed(11).WithLosses(6).
				WithBedsBroken(5).
				WithFinalKills(22).WithFinalDeaths(12).
				WithKills(55).WithDeaths(32).Build(at)

			getSessionAt := app.BuildGetSessionAt(
				fixedStats([]domain.PlayerPIT{p0, p1}),
				computeSessions,
			)

			result, err := getSessionAt(t.Context(), uuid, at)
			require.NoError(t, err)
			require.Equal(t, app.SessionAtResult{
				Session: &domain.Session{Start: p0, End: p1, Consecutive: true},
				Games: []app.GameSegment{
					{Start: p0, End: p1, Game: nil},
				},
			}, result)
		})

		t.Run("BedsLost jumps by more than one between snapshots", func(t *testing.T) {
			t.Parallel()

			b := domaintest.NewPlayerBuilder(uuid).
				WithExperience(1000).FromDB().
				Doubles().
				WithGamesPlayed(10).WithWins(5).WithLosses(5).
				WithBedsBroken(4).WithBedsLost(3).
				WithFinalKills(20).WithFinalDeaths(10).
				WithKills(50).WithDeaths(30)
			p0 := b.Build(at.Add(-15 * time.Minute))

			// Doubles advances by exactly one game, but beds lost
			// jumped by 2 — impossible in a real game.
			p1 := b.
				WithExperience(1100).
				Doubles().
				WithGamesPlayed(11).WithLosses(6).
				WithBedsLost(5).
				WithFinalKills(22).
				WithKills(55).WithDeaths(32).Build(at)

			getSessionAt := app.BuildGetSessionAt(
				fixedStats([]domain.PlayerPIT{p0, p1}),
				computeSessions,
			)

			result, err := getSessionAt(t.Context(), uuid, at)
			require.NoError(t, err)
			require.Equal(t, app.SessionAtResult{
				Session: &domain.Session{Start: p0, End: p1, Consecutive: true},
				Games: []app.GameSegment{
					{Start: p0, End: p1, Game: nil},
				},
			}, result)
		})
	})

	t.Run("getPlayerPITs error is propagated", func(t *testing.T) {
		t.Parallel()

		boom := errors.New("boom")
		getPlayerPITs := func(ctx context.Context, _ string, _, _ time.Time) ([]domain.PlayerPIT, error) {
			return nil, boom
		}
		getSessionAt := app.BuildGetSessionAt(getPlayerPITs, computeSessions)

		_, err := getSessionAt(t.Context(), uuid, at)
		require.Error(t, err)
		require.ErrorIs(t, err, boom)
	})

	t.Run("non-normalized uuid is rejected without hitting getPlayerPITs", func(t *testing.T) {
		t.Parallel()

		getPlayerPITs := func(ctx context.Context, _ string, _, _ time.Time) ([]domain.PlayerPIT, error) {
			t.Helper()
			t.Fatal("getPlayerPITs should not be called when UUID is not normalized")
			return nil, nil
		}
		getSessionAt := app.BuildGetSessionAt(getPlayerPITs, computeSessions)

		_, err := getSessionAt(t.Context(), "0123456789abcdef0123456789abcdef", at)
		require.Error(t, err)
	})

	t.Run("game result computation per gamemode", func(t *testing.T) {
		t.Parallel()

		tests := []struct {
			gamemode domain.Gamemode
			b        *domaintest.StatsBuilder
		}{
			{gamemode: domain.GamemodeSolo, b: domaintest.NewPlayerBuilder(uuid).FromDB().Solo()},
			{gamemode: domain.GamemodeDoubles, b: domaintest.NewPlayerBuilder(uuid).FromDB().Doubles()},
			{gamemode: domain.GamemodeThrees, b: domaintest.NewPlayerBuilder(uuid).FromDB().Threes()},
			{gamemode: domain.GamemodeFours, b: domaintest.NewPlayerBuilder(uuid).FromDB().Fours()},
		}

		for _, tc := range tests {
			t.Run(string(tc.gamemode), func(t *testing.T) {
				t.Parallel()

				// Leaves share tc.b, so they run sequentially within this
				// parent goroutine (no t.Parallel() on the leaves).

				t.Run("win", func(t *testing.T) {
					tc.b.WithGamesPlayed(10).WithWins(5).WithLosses(5).
						WithBedsBroken(4).WithBedsLost(3).
						WithFinalKills(20).WithFinalDeaths(10).
						WithKills(50).WithDeaths(30).
						WithExperience(1000)
					prev := tc.b.Build(at.Add(-15 * time.Minute))

					// +1 game, won, no FD/BL
					tc.b.WithGamesPlayed(11).WithWins(6).
						WithBedsBroken(5).
						WithFinalKills(24).
						WithKills(58).WithDeaths(32).
						WithExperience(1300)
					curr := tc.b.Build(at)

					getSessionAt := app.BuildGetSessionAt(
						fixedStats([]domain.PlayerPIT{prev, curr}),
						computeSessions,
					)

					result, err := getSessionAt(t.Context(), uuid, at)
					require.NoError(t, err)
					require.Equal(t, app.SessionAtResult{
						Session: &domain.Session{Start: prev, End: curr, Consecutive: true},
						Games: []app.GameSegment{
							{Start: prev, End: curr, Game: &domain.GameResult{
								Gamemode:   tc.gamemode,
								Won:        true,
								FinalKills: 4,
								FinalDeath: false,
								BedsBroken: 1,
								BedLost:    false,
								Kills:      8,
								Deaths:     2,
								Experience: 300,
							}},
						},
					}, result)
				})

				t.Run("loss", func(t *testing.T) {
					tc.b.WithGamesPlayed(10).WithWins(5).WithLosses(5).
						WithBedsBroken(4).WithBedsLost(3).
						WithFinalKills(20).WithFinalDeaths(10).
						WithKills(50).WithDeaths(30).
						WithExperience(1000)
					prev := tc.b.Build(at.Add(-15 * time.Minute))

					// +1 game, lost, final-died, bed-lost
					tc.b.WithGamesPlayed(11).WithLosses(6).
						WithBedsLost(4).
						WithFinalKills(22).WithFinalDeaths(11).
						WithKills(54).WithDeaths(34).
						WithExperience(1200)
					curr := tc.b.Build(at)

					getSessionAt := app.BuildGetSessionAt(
						fixedStats([]domain.PlayerPIT{prev, curr}),
						computeSessions,
					)

					result, err := getSessionAt(t.Context(), uuid, at)
					require.NoError(t, err)
					require.Equal(t, app.SessionAtResult{
						Session: &domain.Session{Start: prev, End: curr, Consecutive: true},
						Games: []app.GameSegment{
							{Start: prev, End: curr, Game: &domain.GameResult{
								Gamemode:   tc.gamemode,
								Won:        false,
								FinalKills: 2,
								FinalDeath: true,
								BedsBroken: 0,
								BedLost:    true,
								Kills:      4,
								Deaths:     4,
								Experience: 200,
							}},
						},
					}, result)
				})
			})
		}
	})
}
