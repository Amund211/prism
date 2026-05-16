package app_test

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
)

func TestComputeSessions(t *testing.T) {
	t.Parallel()

	// nowFarFuture is used by tests that don't care about the Ongoing field —
	// it pushes `now` so far past every session that nothing is ever ongoing.
	nowFarFuture := func() time.Time {
		return time.Date(3000, 1, 1, 0, 0, 0, 0, time.UTC)
	}

	requireEqualSessions := func(t *testing.T, expected, actual []domain.Session) {
		t.Helper()

		type normalizedPlayerPIT struct {
			queriedAtISO  string
			uuid          string
			experience    int64
			gamesPlayed   int
			soloWinstreak int
		}

		type normalizedSession struct {
			start       normalizedPlayerPIT
			end         normalizedPlayerPIT
			consecutive bool
			ongoing     bool
		}

		normalizePlayerData := func(player *domain.PlayerPIT) normalizedPlayerPIT {
			soloWinstreak := -1
			if player.Solo.Winstreak != nil {
				soloWinstreak = *player.Solo.Winstreak
			}
			return normalizedPlayerPIT{
				queriedAtISO:  player.QueriedAt.Format(time.RFC3339),
				uuid:          player.UUID,
				experience:    player.Experience,
				gamesPlayed:   player.Overall.GamesPlayed,
				soloWinstreak: soloWinstreak,
			}

		}

		normalizeSessions := func(sessions []domain.Session) []normalizedSession {
			normalized := make([]normalizedSession, len(sessions))
			for i, session := range sessions {
				normalized[i] = normalizedSession{
					start:       normalizePlayerData(&session.Start),
					end:         normalizePlayerData(&session.End),
					consecutive: session.Consecutive,
					ongoing:     session.Ongoing,
				}
			}
			return normalized
		}

		require.Equal(t, normalizeSessions(expected), normalizeSessions(actual))
	}

	t.Run("random clusters", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		computeSessions := app.BuildComputeSessions(nowFarFuture)
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2022, time.February, 14, 0, 0, 0, 0, time.FixedZone("UTC", 3600*1))

		players := make([]domain.PlayerPIT, 26)
		// Ended session before the start
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-8*time.Hour).Add(-1*time.Minute)).WithExperience(1_000).FromDB().Fours().WithGamesPlayed(10).Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-8*time.Hour).Add(7*time.Minute)).WithExperience(1_300).FromDB().Fours().WithGamesPlayed(11).Build()
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-8*time.Hour).Add(17*time.Minute)).WithExperience(1_600).FromDB().Fours().WithGamesPlayed(12).Build()

		// Session starting just before the start
		// Some inactivity at the start of the session
		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(-37*time.Minute)).WithExperience(1_600).FromDB().Fours().WithGamesPlayed(12).Build()
		players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(-27*time.Minute)).WithExperience(1_600).FromDB().Fours().WithGamesPlayed(12).Build()
		players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(-17*time.Minute)).WithExperience(1_600).FromDB().Fours().WithGamesPlayed(12).Build()
		players[6] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(-12*time.Minute)).WithExperience(1_900).FromDB().Fours().WithGamesPlayed(13).Build()
		players[7] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(2*time.Minute)).WithExperience(2_200).FromDB().Fours().WithGamesPlayed(14).Build()
		// One hour space between entries
		players[8] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(38*time.Minute)).WithExperience(7_200).FromDB().Fours().WithGamesPlayed(15).Build()
		players[9] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(38*time.Minute)).WithExperience(7_900).FromDB().Fours().WithGamesPlayed(16).Build()
		// One hour space between stat change, with some inactivity events in between
		players[10] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(45*time.Minute)).WithExperience(8_900).FromDB().Fours().WithGamesPlayed(17).Build()
		players[11] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(55*time.Minute)).WithExperience(8_900).FromDB().Fours().WithGamesPlayed(17).Build()
		players[12] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(5*time.Minute)).WithExperience(8_900).FromDB().Fours().WithGamesPlayed(17).Build()
		players[13] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(15*time.Minute)).WithExperience(8_900).FromDB().Fours().WithGamesPlayed(17).Build()
		players[14] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(25*time.Minute)).WithExperience(8_900).FromDB().Fours().WithGamesPlayed(17).Build()
		players[15] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(35*time.Minute)).WithExperience(8_900).FromDB().Fours().WithGamesPlayed(17).Build()
		players[16] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(45*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(18).Build()
		// Some inactivity at the end
		players[17] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(55*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(18).Build()
		players[18] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(5*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(18).Build()
		players[19] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(15*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(18).Build()
		players[20] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(25*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(18).Build()
		players[21] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(35*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(18).Build()
		players[22] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(45*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(18).Build()
		players[23] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(55*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(18).Build()

		// New activity 71 minutes after the last entry -> new session
		players[24] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(56*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(18).Build()
		players[25] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(16*time.Minute)).WithExperience(10_800).FromDB().Fours().WithGamesPlayed(19).Build()

		sessions := computeSessions(ctx, players, start, start.Add(24*time.Hour))

		expectedSessions := []domain.Session{
			{
				Start:       players[5],
				End:         players[16],
				Consecutive: true,
			},
			{
				Start:       players[24],
				End:         players[25],
				Consecutive: true,
			},
		}
		requireEqualSessions(t, expectedSessions, sessions)
	})

	t.Run("Single stat", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		computeSessions := app.BuildComputeSessions(nowFarFuture)
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))

		players := make([]domain.PlayerPIT, 1)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(6*time.Hour).Add(7*time.Minute)).WithExperience(1_300).FromDB().Fours().WithGamesPlayed(11).Build()

		sessions := computeSessions(ctx, players, start, start.Add(24*time.Hour))

		require.Len(t, sessions, 0)
	})

	t.Run("Single stat at the start", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		computeSessions := app.BuildComputeSessions(nowFarFuture)
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))

		players := make([]domain.PlayerPIT, 3)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(6*time.Hour).Add(7*time.Minute)).WithExperience(1_000).FromDB().Fours().WithGamesPlayed(9).Build()

		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(8*time.Hour).Add(-1*time.Minute)).WithExperience(1_100).FromDB().Fours().WithGamesPlayed(10).Build()
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(8*time.Hour).Add(7*time.Minute)).WithExperience(1_300).FromDB().Fours().WithGamesPlayed(11).Build()

		sessions := computeSessions(ctx, players, start, start.Add(24*time.Hour))

		expectedSessions := []domain.Session{
			{
				Start:       players[1],
				End:         players[2],
				Consecutive: true,
			},
		}
		requireEqualSessions(t, expectedSessions, sessions)
	})

	t.Run("Single stat at the end", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		computeSessions := app.BuildComputeSessions(nowFarFuture)
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))

		players := make([]domain.PlayerPIT, 3)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(6*time.Hour).Add(-1*time.Minute)).WithExperience(1_000).FromDB().Fours().WithGamesPlayed(10).Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(6*time.Hour).Add(7*time.Minute)).WithExperience(1_300).FromDB().Fours().WithGamesPlayed(11).Build()

		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(8*time.Hour).Add(7*time.Minute)).WithExperience(1_600).FromDB().Fours().WithGamesPlayed(12).Build()

		sessions := computeSessions(ctx, players, start, start.Add(24*time.Hour))

		expectedSessions := []domain.Session{
			{
				Start:       players[0],
				End:         players[1],
				Consecutive: true,
			},
		}
		requireEqualSessions(t, expectedSessions, sessions)
	})

	t.Run("Single stat at start and end", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		computeSessions := app.BuildComputeSessions(nowFarFuture)
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

		players := make([]domain.PlayerPIT, 4)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(5*time.Hour).Add(7*time.Minute)).WithExperience(1_000).FromDB().Fours().WithGamesPlayed(9).Build()

		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(8*time.Hour).Add(-1*time.Minute)).WithExperience(1_000).FromDB().Fours().WithGamesPlayed(10).Build()
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(8*time.Hour).Add(7*time.Minute)).WithExperience(1_300).FromDB().Fours().WithGamesPlayed(11).Build()

		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(10*time.Hour).Add(7*time.Minute)).WithExperience(1_600).FromDB().Fours().WithGamesPlayed(12).Build()

		sessions := computeSessions(ctx, players, start, start.Add(24*time.Hour))

		expectedSessions := []domain.Session{
			{
				Start:       players[1],
				End:         players[2],
				Consecutive: true,
			},
		}
		requireEqualSessions(t, expectedSessions, sessions)
	})

	t.Run("No stats", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		computeSessions := app.BuildComputeSessions(nowFarFuture)
		start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*10))

		players := make([]domain.PlayerPIT, 0)

		sessions := computeSessions(ctx, players, start, start.Add(24*time.Hour))

		require.Len(t, sessions, 0)
	})

	t.Run("inactivity between sessions", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		computeSessions := app.BuildComputeSessions(nowFarFuture)
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

		players := make([]domain.PlayerPIT, 13)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(30*time.Minute)).WithExperience(9_200).FromDB().Fours().WithGamesPlayed(16).Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(35*time.Minute)).WithExperience(9_200).FromDB().Fours().WithGamesPlayed(16).Build()
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(45*time.Minute)).WithExperience(9_400).FromDB().Fours().WithGamesPlayed(17).Build()
		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(55*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(18).Build()
		players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(5*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(18).Build()
		players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(15*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(18).Build()
		players[6] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(25*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(18).Build()
		players[7] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(35*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(18).Build()
		players[8] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(45*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(18).Build()
		players[9] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(55*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(18).Build()
		players[10] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(56*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(18).Build()
		players[11] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(16*time.Minute)).WithExperience(10_800).FromDB().Fours().WithGamesPlayed(19).Build()
		players[12] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(20*time.Minute)).WithExperience(10_800).FromDB().Fours().WithGamesPlayed(19).Build()

		sessions := computeSessions(ctx, players, start, start.Add(24*time.Hour))

		expectedSessions := []domain.Session{
			{
				Start:       players[1],
				End:         players[3],
				Consecutive: true,
			},
			{
				Start:       players[10],
				End:         players[11],
				Consecutive: true,
			},
		}
		requireEqualSessions(t, expectedSessions, sessions)
	})

	t.Run("1 hr inactivity between sessions", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		computeSessions := app.BuildComputeSessions(nowFarFuture)
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

		players := make([]domain.PlayerPIT, 4)
		// Session 1
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(5*time.Minute)).WithExperience(9_200).FromDB().Fours().WithGamesPlayed(16).Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(30*time.Minute)).WithExperience(9_400).FromDB().Fours().WithGamesPlayed(17).Build()
		// Session 2
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(45*time.Minute)).WithExperience(9_400).FromDB().Fours().WithGamesPlayed(17).Build()
		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(31*time.Minute)).WithExperience(10_800).FromDB().Fours().WithGamesPlayed(18).Build()

		sessions := computeSessions(ctx, players, start, start.Add(24*time.Hour))

		expectedSessions := []domain.Session{
			{
				Start:       players[0],
				End:         players[1],
				Consecutive: true,
			},
			{
				Start:       players[2],
				End:         players[3],
				Consecutive: true,
			},
		}
		requireEqualSessions(t, expectedSessions, sessions)
	})

	t.Run("sessions before and after", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		computeSessions := app.BuildComputeSessions(nowFarFuture)
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

		players := make([]domain.PlayerPIT, 8)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-25*time.Hour).Add(5*time.Minute)).WithExperience(9_200).FromDB().Fours().WithGamesPlayed(16).Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-25*time.Hour).Add(30*time.Minute)).WithExperience(9_400).FromDB().Fours().WithGamesPlayed(17).Build()

		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-16*time.Hour).Add(5*time.Minute)).WithExperience(9_400).FromDB().Fours().WithGamesPlayed(17).Build()
		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-16*time.Hour).Add(30*time.Minute)).WithExperience(9_900).FromDB().Fours().WithGamesPlayed(18).Build()

		players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(25*time.Hour).Add(5*time.Minute)).WithExperience(9_900).FromDB().Fours().WithGamesPlayed(18).Build()
		players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(25*time.Hour).Add(30*time.Minute)).WithExperience(10_900).FromDB().Fours().WithGamesPlayed(19).Build()

		players[6] = domaintest.NewPlayerBuilder(playerUUID, start.Add(45*time.Hour).Add(5*time.Minute)).WithExperience(10_900).FromDB().Fours().WithGamesPlayed(19).Build()
		players[7] = domaintest.NewPlayerBuilder(playerUUID, start.Add(45*time.Hour).Add(30*time.Minute)).WithExperience(11_900).FromDB().Fours().WithGamesPlayed(20).Build()

		sessions := computeSessions(ctx, players, start, start.Add(24*time.Hour))

		expectedSessions := []domain.Session{}
		requireEqualSessions(t, expectedSessions, sessions)
	})

	t.Run("only xp change", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		computeSessions := app.BuildComputeSessions(nowFarFuture)
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2024, time.March, 24, 17, 37, 14, 987_654_321, time.FixedZone("UTC", 3600*9))

		players := make([]domain.PlayerPIT, 4)
		// Session 1
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(5*time.Minute)).WithExperience(9_200).FromDB().Fours().WithGamesPlayed(16).Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(30*time.Minute)).WithExperience(9_400).FromDB().Fours().WithGamesPlayed(16).Build()
		// Session 2
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(45*time.Minute)).WithExperience(9_400).FromDB().Fours().WithGamesPlayed(16).Build()
		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(31*time.Minute)).WithExperience(10_800).FromDB().Fours().WithGamesPlayed(16).Build()

		sessions := computeSessions(ctx, players, start, start.Add(24*time.Hour))

		expectedSessions := []domain.Session{
			{
				Start:       players[0],
				End:         players[1],
				Consecutive: true,
			},
			{
				Start:       players[2],
				End:         players[3],
				Consecutive: true,
			},
		}
		requireEqualSessions(t, expectedSessions, sessions)
	})

	t.Run("only games played change", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		computeSessions := app.BuildComputeSessions(nowFarFuture)
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2024, time.August, 2, 1, 47, 34, 987_654_321, time.FixedZone("UTC", 3600*3))

		players := make([]domain.PlayerPIT, 4)
		// Session 1
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(5*time.Minute)).WithExperience(9_200).FromDB().Fours().WithGamesPlayed(16).Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(30*time.Minute)).WithExperience(9_200).FromDB().Fours().WithGamesPlayed(17).Build()
		// Session 2
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(45*time.Minute)).WithExperience(9_200).FromDB().Fours().WithGamesPlayed(17).Build()
		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(31*time.Minute)).WithExperience(9_200).FromDB().Fours().WithGamesPlayed(18).Build()

		sessions := computeSessions(ctx, players, start, start.Add(24*time.Hour))

		expectedSessions := []domain.Session{
			{
				Start:       players[0],
				End:         players[1],
				Consecutive: true,
			},
			{
				Start:       players[2],
				End:         players[3],
				Consecutive: true,
			},
		}
		requireEqualSessions(t, expectedSessions, sessions)
	})

	t.Run("gaps in sessions", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		computeSessions := app.BuildComputeSessions(nowFarFuture)
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2022, time.November, 2, 13, 47, 34, 987_654_321, time.FixedZone("UTC", 3600*3))

		// Players not using the overlay, but getting queued by players using the overlay will have sporadic stat distributions
		// Their actual session may be split into multiple single stat entries, some of which may be
		// close enough together to be considered a single session. This can result in one actual session
		// turning into multiple calculated sessions.
		players := make([]domain.PlayerPIT, 10)

		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(5*time.Minute)).WithExperience(9_200).FromDB().Fours().WithGamesPlayed(16).Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(30*time.Minute)).WithExperience(9_200).FromDB().Fours().WithGamesPlayed(17).Build()

		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(45*time.Minute)).WithExperience(15_200).FromDB().Fours().WithGamesPlayed(20).Build()

		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(5*time.Hour).Add(45*time.Minute)).WithExperience(17_200).FromDB().Fours().WithGamesPlayed(23).Build()

		players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(7*time.Hour).Add(45*time.Minute)).WithExperience(19_200).FromDB().Fours().WithGamesPlayed(27).Build()
		players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(7*time.Hour).Add(55*time.Minute)).WithExperience(19_800).FromDB().Fours().WithGamesPlayed(28).Build()

		players[6] = domaintest.NewPlayerBuilder(playerUUID, start.Add(9*time.Hour).Add(15*time.Minute)).WithExperience(20_800).FromDB().Fours().WithGamesPlayed(30).Build()
		players[7] = domaintest.NewPlayerBuilder(playerUUID, start.Add(9*time.Hour).Add(55*time.Minute)).WithExperience(23_800).FromDB().Fours().WithGamesPlayed(33).Build()

		players[8] = domaintest.NewPlayerBuilder(playerUUID, start.Add(11*time.Hour).Add(15*time.Minute)).WithExperience(28_800).FromDB().Fours().WithGamesPlayed(35).Build()

		players[9] = domaintest.NewPlayerBuilder(playerUUID, start.Add(17*time.Hour).Add(15*time.Minute)).WithExperience(38_800).FromDB().Fours().WithGamesPlayed(44).Build()

		sessions := computeSessions(ctx, players, start, start.Add(24*time.Hour))

		expectedSessions := []domain.Session{
			{
				Start:       players[0],
				End:         players[1],
				Consecutive: true,
			},
			{
				Start:       players[4],
				End:         players[5],
				Consecutive: true,
			},
			{
				Start:       players[6],
				End:         players[7],
				Consecutive: false,
			},
		}
		requireEqualSessions(t, expectedSessions, sessions)
	})

	t.Run("end", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		computeSessions := app.BuildComputeSessions(nowFarFuture)
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2025, time.December, 9, 14, 13, 34, 987_654_321, time.FixedZone("UTC", 3600*0))

		players := make([]domain.PlayerPIT, 3)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(23*time.Hour).Add(5*time.Minute)).WithExperience(9_200).FromDB().Fours().WithGamesPlayed(16).Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(23*time.Hour).Add(40*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(17).Build()
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(24*time.Hour).Add(05*time.Minute)).WithExperience(9_900).FromDB().Fours().WithGamesPlayed(18).Build()

		sessions := computeSessions(ctx, players, start, start.Add(24*time.Hour))

		expectedSessions := []domain.Session{
			{
				Start:       players[0],
				End:         players[2],
				Consecutive: true,
			},
		}
		requireEqualSessions(t, expectedSessions, sessions)
	})

	t.Run("mostly consecutive", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		computeSessions := app.BuildComputeSessions(nowFarFuture)
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2025, time.February, 7, 4, 13, 34, 987_654_321, time.FixedZone("UTC", 3600*-10))

		players := make([]domain.PlayerPIT, 6)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(5*time.Minute)).WithExperience(9_200).FromDB().Fours().WithGamesPlayed(15).Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(40*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(16).Build()
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(05*time.Minute)).WithExperience(9_900).FromDB().Fours().WithGamesPlayed(17).Build()
		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(45*time.Minute)).WithExperience(10_900).FromDB().Fours().WithGamesPlayed(20).Build()
		players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(55*time.Minute)).WithExperience(11_900).FromDB().Fours().WithGamesPlayed(21).Build()
		players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(5*time.Hour).Add(15*time.Minute)).WithExperience(12_900).FromDB().Fours().WithGamesPlayed(22).Build()

		sessions := computeSessions(ctx, players, start, start.Add(24*time.Hour))

		expectedSessions := []domain.Session{
			{
				Start:       players[0],
				End:         players[5],
				Consecutive: false,
			},
		}
		requireEqualSessions(t, expectedSessions, sessions)
	})

	t.Run("short pauses", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		computeSessions := app.BuildComputeSessions(nowFarFuture)
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2025, time.December, 1, 7, 13, 34, 987_654_321, time.FixedZone("UTC", 3600*7))

		players := make([]domain.PlayerPIT, 6)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(5*time.Minute)).WithExperience(9_200).FromDB().Fours().WithGamesPlayed(16).Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(40*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(16).Build()
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(05*time.Minute)).WithExperience(9_600).FromDB().Fours().WithGamesPlayed(16).Build()
		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(45*time.Minute)).WithExperience(10_900).FromDB().Fours().WithGamesPlayed(17).Build()
		players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(55*time.Minute)).WithExperience(10_900).FromDB().Fours().WithGamesPlayed(17).Build()
		players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(15*time.Minute)).WithExperience(11_900).FromDB().Fours().WithGamesPlayed(17).Build()

		sessions := computeSessions(ctx, players, start, start.Add(24*time.Hour))

		expectedSessions := []domain.Session{
			{
				Start:       players[0],
				End:         players[5],
				Consecutive: true,
			},
		}
		requireEqualSessions(t, expectedSessions, sessions)
	})

	t.Run("2 gap -> still consecutive", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		computeSessions := app.BuildComputeSessions(nowFarFuture)
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2025, time.February, 7, 4, 13, 34, 987_654_321, time.FixedZone("UTC", 3600*-10))

		players := make([]domain.PlayerPIT, 6)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(5*time.Minute)).WithExperience(9_200).FromDB().Fours().WithGamesPlayed(16).Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(40*time.Minute)).WithExperience(9_500).FromDB().Fours().WithGamesPlayed(17).Build()
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(05*time.Minute)).WithExperience(9_900).FromDB().Fours().WithGamesPlayed(18).Build()
		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(45*time.Minute)).WithExperience(10_900).FromDB().Fours().WithGamesPlayed(20).Build()
		players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(55*time.Minute)).WithExperience(11_900).FromDB().Fours().WithGamesPlayed(21).Build()
		players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(5*time.Hour).Add(15*time.Minute)).WithExperience(12_900).FromDB().Fours().WithGamesPlayed(22).Build()

		sessions := computeSessions(ctx, players, start, start.Add(24*time.Hour))

		expectedSessions := []domain.Session{
			{
				Start:       players[0],
				End:         players[5],
				Consecutive: true,
			},
		}
		requireEqualSessions(t, expectedSessions, sessions)
	})

	t.Run("ongoing across stat additions", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		playerUUID := domaintest.NewUUID(t)
		refTime := time.Date(2025, time.January, 15, 11, 50, 0, 0, time.UTC)

		// 11:50, 10 games played
		statA := domaintest.NewPlayerBuilder(playerUUID, refTime).
			WithExperience(1_000).FromDB().Fours().WithGamesPlayed(10).
			Build()
		// 12:00, +1 game
		statB := domaintest.NewPlayerBuilder(playerUUID, refTime.Add(10*time.Minute)).
			WithExperience(1_300).FromDB().Fours().WithGamesPlayed(11).
			Build()
		// 12:10, identical to statB so it doesn't extend the session
		statC := domaintest.NewPlayerBuilder(playerUUID, refTime.Add(20*time.Minute)).
			WithExperience(1_300).FromDB().Fours().WithGamesPlayed(11).
			Build()
		// 13:05, +1 game — starts a new session
		statD := domaintest.NewPlayerBuilder(playerUUID, refTime.Add(75*time.Minute)).
			WithExperience(1_700).FromDB().Fours().WithGamesPlayed(12).
			Build()

		intervalStart := refTime.Add(-12 * time.Hour)
		intervalEnd := refTime.Add(12 * time.Hour)

		firstSession := domain.Session{Start: statA, End: statB, Consecutive: true}
		firstSessionOngoing := domain.Session{Start: statA, End: statB, Consecutive: true, Ongoing: true}
		secondSession := domain.Session{Start: statC, End: statD, Consecutive: true}
		secondSessionOngoing := domain.Session{Start: statC, End: statD, Consecutive: true, Ongoing: true}

		cases := []struct {
			name         string
			stats        []domain.PlayerPIT
			now          time.Time
			wantSessions []domain.Session
		}{
			{
				name:         "stats up to 12:00, now=12:01 -> ongoing",
				stats:        []domain.PlayerPIT{statA, statB},
				now:          refTime.Add(11 * time.Minute),
				wantSessions: []domain.Session{firstSessionOngoing},
			},
			{
				name:         "stats up to 12:00, now=12:09 -> ongoing",
				stats:        []domain.PlayerPIT{statA, statB},
				now:          refTime.Add(19 * time.Minute),
				wantSessions: []domain.Session{firstSessionOngoing},
			},
			{
				name:         "12:10 stat does not extend, now=12:10 -> ongoing",
				stats:        []domain.PlayerPIT{statA, statB, statC},
				now:          refTime.Add(20 * time.Minute),
				wantSessions: []domain.Session{firstSessionOngoing},
			},
			{
				name:         "12:10 stat does not extend, now=12:30 -> ongoing",
				stats:        []domain.PlayerPIT{statA, statB, statC},
				now:          refTime.Add(40 * time.Minute),
				wantSessions: []domain.Session{firstSessionOngoing},
			},
			{
				name:         "12:10 stat does not extend, now=12:59 -> ongoing",
				stats:        []domain.PlayerPIT{statA, statB, statC},
				now:          refTime.Add(69 * time.Minute),
				wantSessions: []domain.Session{firstSessionOngoing},
			},
			{
				name:         "12:10 stat does not extend, now=13:01 -> not ongoing",
				stats:        []domain.PlayerPIT{statA, statB, statC},
				now:          refTime.Add(71 * time.Minute),
				wantSessions: []domain.Session{firstSession},
			},
			{
				name:         "12:10 stat does not extend, now=13:04 -> not ongoing",
				stats:        []domain.PlayerPIT{statA, statB, statC},
				now:          refTime.Add(74 * time.Minute),
				wantSessions: []domain.Session{firstSession},
			},
			{
				name:         "13:05 starts second session, now=13:05 -> only second ongoing",
				stats:        []domain.PlayerPIT{statA, statB, statC, statD},
				now:          refTime.Add(75 * time.Minute),
				wantSessions: []domain.Session{firstSession, secondSessionOngoing},
			},
			{
				name:         "13:05 starts second session, now=13:30 -> only second ongoing",
				stats:        []domain.PlayerPIT{statA, statB, statC, statD},
				now:          refTime.Add(100 * time.Minute),
				wantSessions: []domain.Session{firstSession, secondSessionOngoing},
			},
			{
				name:         "13:05 starts second session, now=14:04 -> only second ongoing",
				stats:        []domain.PlayerPIT{statA, statB, statC, statD},
				now:          refTime.Add(134 * time.Minute),
				wantSessions: []domain.Session{firstSession, secondSessionOngoing},
			},
			{
				name:         "13:05 starts second session, now=14:06 -> neither ongoing",
				stats:        []domain.PlayerPIT{statA, statB, statC, statD},
				now:          refTime.Add(136 * time.Minute),
				wantSessions: []domain.Session{firstSession, secondSession},
			},
		}

		for _, c := range cases {
			t.Run(c.name, func(t *testing.T) {
				t.Parallel()
				nowFunc := func() time.Time { return c.now }
				computeSessions := app.BuildComputeSessions(nowFunc)
				got := computeSessions(ctx, c.stats, intervalStart, intervalEnd)
				requireEqualSessions(t, c.wantSessions, got)
			})
		}
	})

	// These tests cover edge cases that shouldn't happen, where the "now" time is
	// earlier than timestamps we have stored in the DB.
	t.Run("continuity errors", func(t *testing.T) {
		t.Run("now inside last session is ongoing", func(t *testing.T) {
			ctx := context.Background()
			t.Parallel()
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2025, time.March, 4, 11, 50, 0, 0, time.UTC)

			stats := []domain.PlayerPIT{
				domaintest.NewPlayerBuilder(playerUUID, start).
					WithExperience(1_000).FromDB().Fours().WithGamesPlayed(10).
					Build(),
				domaintest.NewPlayerBuilder(playerUUID, start.Add(10*time.Minute)).
					WithExperience(1_300).FromDB().Fours().WithGamesPlayed(11).
					Build(),
			}
			// now lands strictly between session.Start and session.End
			nowFunc := func() time.Time { return start.Add(5 * time.Minute) }
			computeSessions := app.BuildComputeSessions(nowFunc)

			sessions := computeSessions(ctx, stats, start.Add(-12*time.Hour), start.Add(12*time.Hour))

			requireEqualSessions(t, []domain.Session{
				{Start: stats[0], End: stats[1], Consecutive: true, Ongoing: true},
			}, sessions)
		})

		t.Run("now before last session is not ongoing", func(t *testing.T) {
			ctx := context.Background()
			t.Parallel()
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2025, time.April, 1, 11, 50, 0, 0, time.UTC)

			stats := []domain.PlayerPIT{
				domaintest.NewPlayerBuilder(playerUUID, start).
					WithExperience(1_000).FromDB().Fours().WithGamesPlayed(10).
					Build(),
				domaintest.NewPlayerBuilder(playerUUID, start.Add(10*time.Minute)).
					WithExperience(1_300).FromDB().Fours().WithGamesPlayed(11).
					Build(),
			}
			// now is before the session starts
			nowFunc := func() time.Time { return start.Add(-1 * time.Minute) }
			computeSessions := app.BuildComputeSessions(nowFunc)

			sessions := computeSessions(ctx, stats, start.Add(-12*time.Hour), start.Add(12*time.Hour))

			requireEqualSessions(t, []domain.Session{
				{Start: stats[0], End: stats[1], Consecutive: true},
			}, sessions)
		})
	})
}
