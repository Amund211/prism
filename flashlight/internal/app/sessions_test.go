package app_test

import (
	"context"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
	"github.com/stretchr/testify/require"
)

func TestComputeSessions(t *testing.T) {
	t.Parallel()

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
				}
			}
			return normalized
		}

		require.Equal(t, normalizeSessions(expected), normalizeSessions(actual))
	}

	t.Run("random clusters", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2022, time.February, 14, 0, 0, 0, 0, time.FixedZone("UTC", 3600*1))

		players := make([]domain.PlayerPIT, 26)
		// Ended session before the start
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-8*time.Hour).Add(-1*time.Minute)).WithGamesPlayed(10).WithExperience(1_000).FromDB().Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-8*time.Hour).Add(7*time.Minute)).WithGamesPlayed(11).WithExperience(1_300).FromDB().Build()
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-8*time.Hour).Add(17*time.Minute)).WithGamesPlayed(12).WithExperience(1_600).FromDB().Build()

		// Session starting just before the start
		// Some inactivity at the start of the session
		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(-37*time.Minute)).WithGamesPlayed(12).WithExperience(1_600).FromDB().Build()
		players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(-27*time.Minute)).WithGamesPlayed(12).WithExperience(1_600).FromDB().Build()
		players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(-17*time.Minute)).WithGamesPlayed(12).WithExperience(1_600).FromDB().Build()
		players[6] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(-12*time.Minute)).WithGamesPlayed(13).WithExperience(1_900).FromDB().Build()
		players[7] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(2*time.Minute)).WithGamesPlayed(14).WithExperience(2_200).FromDB().Build()
		// One hour space between entries
		players[8] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(38*time.Minute)).WithGamesPlayed(15).WithExperience(7_200).FromDB().Build()
		players[9] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(38*time.Minute)).WithGamesPlayed(16).WithExperience(7_900).FromDB().Build()
		// One hour space between stat change, with some inactivity events in between
		players[10] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(45*time.Minute)).WithGamesPlayed(17).WithExperience(8_900).FromDB().Build()
		players[11] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(55*time.Minute)).WithGamesPlayed(17).WithExperience(8_900).FromDB().Build()
		players[12] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(5*time.Minute)).WithGamesPlayed(17).WithExperience(8_900).FromDB().Build()
		players[13] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(15*time.Minute)).WithGamesPlayed(17).WithExperience(8_900).FromDB().Build()
		players[14] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(25*time.Minute)).WithGamesPlayed(17).WithExperience(8_900).FromDB().Build()
		players[15] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(35*time.Minute)).WithGamesPlayed(17).WithExperience(8_900).FromDB().Build()
		players[16] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(45*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).FromDB().Build()
		// Some inactivity at the end
		players[17] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(55*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).FromDB().Build()
		players[18] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(5*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).FromDB().Build()
		players[19] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(15*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).FromDB().Build()
		players[20] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(25*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).FromDB().Build()
		players[21] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(35*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).FromDB().Build()
		players[22] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(45*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).FromDB().Build()
		players[23] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(55*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).FromDB().Build()

		// New activity 71 minutes after the last entry -> new session
		players[24] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(56*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).FromDB().Build()
		players[25] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(16*time.Minute)).WithGamesPlayed(19).WithExperience(10_800).FromDB().Build()

		sessions := app.ComputeSessions(ctx, players, start, start.Add(24*time.Hour))

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
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))

		players := make([]domain.PlayerPIT, 1)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(6*time.Hour).Add(7*time.Minute)).WithGamesPlayed(11).WithExperience(1_300).FromDB().Build()

		sessions := app.ComputeSessions(ctx, players, start, start.Add(24*time.Hour))

		require.Len(t, sessions, 0)
	})

	t.Run("Single stat at the start", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))

		players := make([]domain.PlayerPIT, 3)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(6*time.Hour).Add(7*time.Minute)).WithGamesPlayed(9).WithExperience(1_000).FromDB().Build()

		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(8*time.Hour).Add(-1*time.Minute)).WithGamesPlayed(10).WithExperience(1_100).FromDB().Build()
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(8*time.Hour).Add(7*time.Minute)).WithGamesPlayed(11).WithExperience(1_300).FromDB().Build()

		sessions := app.ComputeSessions(ctx, players, start, start.Add(24*time.Hour))

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
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))

		players := make([]domain.PlayerPIT, 3)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(6*time.Hour).Add(-1*time.Minute)).WithGamesPlayed(10).WithExperience(1_000).FromDB().Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(6*time.Hour).Add(7*time.Minute)).WithGamesPlayed(11).WithExperience(1_300).FromDB().Build()

		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(8*time.Hour).Add(7*time.Minute)).WithGamesPlayed(12).WithExperience(1_600).FromDB().Build()

		sessions := app.ComputeSessions(ctx, players, start, start.Add(24*time.Hour))

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
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

		players := make([]domain.PlayerPIT, 4)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(5*time.Hour).Add(7*time.Minute)).WithGamesPlayed(9).WithExperience(1_000).FromDB().Build()

		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(8*time.Hour).Add(-1*time.Minute)).WithGamesPlayed(10).WithExperience(1_000).FromDB().Build()
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(8*time.Hour).Add(7*time.Minute)).WithGamesPlayed(11).WithExperience(1_300).FromDB().Build()

		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(10*time.Hour).Add(7*time.Minute)).WithGamesPlayed(12).WithExperience(1_600).FromDB().Build()

		sessions := app.ComputeSessions(ctx, players, start, start.Add(24*time.Hour))

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
		start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*10))

		players := make([]domain.PlayerPIT, 0)

		sessions := app.ComputeSessions(ctx, players, start, start.Add(24*time.Hour))

		require.Len(t, sessions, 0)
	})

	t.Run("inactivity between sessions", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

		players := make([]domain.PlayerPIT, 13)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(30*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).FromDB().Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(35*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).FromDB().Build()
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(45*time.Minute)).WithGamesPlayed(17).WithExperience(9_400).FromDB().Build()
		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(55*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).FromDB().Build()
		players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(5*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).FromDB().Build()
		players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(15*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).FromDB().Build()
		players[6] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(25*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).FromDB().Build()
		players[7] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(35*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).FromDB().Build()
		players[8] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(45*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).FromDB().Build()
		players[9] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(55*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).FromDB().Build()
		players[10] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(56*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).FromDB().Build()
		players[11] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(16*time.Minute)).WithGamesPlayed(19).WithExperience(10_800).FromDB().Build()
		players[12] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(20*time.Minute)).WithGamesPlayed(19).WithExperience(10_800).FromDB().Build()

		sessions := app.ComputeSessions(ctx, players, start, start.Add(24*time.Hour))

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
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

		players := make([]domain.PlayerPIT, 4)
		// Session 1
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(5*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).FromDB().Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(30*time.Minute)).WithGamesPlayed(17).WithExperience(9_400).FromDB().Build()
		// Session 2
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(45*time.Minute)).WithGamesPlayed(17).WithExperience(9_400).FromDB().Build()
		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(31*time.Minute)).WithGamesPlayed(18).WithExperience(10_800).FromDB().Build()

		sessions := app.ComputeSessions(ctx, players, start, start.Add(24*time.Hour))

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
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

		players := make([]domain.PlayerPIT, 8)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-25*time.Hour).Add(5*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).FromDB().Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-25*time.Hour).Add(30*time.Minute)).WithGamesPlayed(17).WithExperience(9_400).FromDB().Build()

		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-16*time.Hour).Add(5*time.Minute)).WithGamesPlayed(17).WithExperience(9_400).FromDB().Build()
		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-16*time.Hour).Add(30*time.Minute)).WithGamesPlayed(18).WithExperience(9_900).FromDB().Build()

		players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(25*time.Hour).Add(5*time.Minute)).WithGamesPlayed(18).WithExperience(9_900).FromDB().Build()
		players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(25*time.Hour).Add(30*time.Minute)).WithGamesPlayed(19).WithExperience(10_900).FromDB().Build()

		players[6] = domaintest.NewPlayerBuilder(playerUUID, start.Add(45*time.Hour).Add(5*time.Minute)).WithGamesPlayed(19).WithExperience(10_900).FromDB().Build()
		players[7] = domaintest.NewPlayerBuilder(playerUUID, start.Add(45*time.Hour).Add(30*time.Minute)).WithGamesPlayed(20).WithExperience(11_900).FromDB().Build()

		sessions := app.ComputeSessions(ctx, players, start, start.Add(24*time.Hour))

		expectedSessions := []domain.Session{}
		requireEqualSessions(t, expectedSessions, sessions)
	})

	t.Run("only xp change", func(t *testing.T) {
		ctx := context.Background()
		t.Parallel()
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2024, time.March, 24, 17, 37, 14, 987_654_321, time.FixedZone("UTC", 3600*9))

		players := make([]domain.PlayerPIT, 4)
		// Session 1
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(5*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).FromDB().Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(30*time.Minute)).WithGamesPlayed(16).WithExperience(9_400).FromDB().Build()
		// Session 2
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(45*time.Minute)).WithGamesPlayed(16).WithExperience(9_400).FromDB().Build()
		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(31*time.Minute)).WithGamesPlayed(16).WithExperience(10_800).FromDB().Build()

		sessions := app.ComputeSessions(ctx, players, start, start.Add(24*time.Hour))

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
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2024, time.August, 2, 1, 47, 34, 987_654_321, time.FixedZone("UTC", 3600*3))

		players := make([]domain.PlayerPIT, 4)
		// Session 1
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(5*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).FromDB().Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(30*time.Minute)).WithGamesPlayed(17).WithExperience(9_200).FromDB().Build()
		// Session 2
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(45*time.Minute)).WithGamesPlayed(17).WithExperience(9_200).FromDB().Build()
		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(31*time.Minute)).WithGamesPlayed(18).WithExperience(9_200).FromDB().Build()

		sessions := app.ComputeSessions(ctx, players, start, start.Add(24*time.Hour))

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
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2022, time.November, 2, 13, 47, 34, 987_654_321, time.FixedZone("UTC", 3600*3))

		// Players not using the overlay, but getting queued by players using the overlay will have sporadic stat distributions
		// Their actual session may be split into multiple single stat entries, some of which may be
		// close enough together to be considered a single session. This can result in one actual session
		// turning into multiple calculated sessions.
		players := make([]domain.PlayerPIT, 10)

		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(5*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).FromDB().Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(30*time.Minute)).WithGamesPlayed(17).WithExperience(9_200).FromDB().Build()

		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(45*time.Minute)).WithGamesPlayed(20).WithExperience(15_200).FromDB().Build()

		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(5*time.Hour).Add(45*time.Minute)).WithGamesPlayed(23).WithExperience(17_200).FromDB().Build()

		players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(7*time.Hour).Add(45*time.Minute)).WithGamesPlayed(27).WithExperience(19_200).FromDB().Build()
		players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(7*time.Hour).Add(55*time.Minute)).WithGamesPlayed(28).WithExperience(19_800).FromDB().Build()

		players[6] = domaintest.NewPlayerBuilder(playerUUID, start.Add(9*time.Hour).Add(15*time.Minute)).WithGamesPlayed(30).WithExperience(20_800).FromDB().Build()
		players[7] = domaintest.NewPlayerBuilder(playerUUID, start.Add(9*time.Hour).Add(55*time.Minute)).WithGamesPlayed(33).WithExperience(23_800).FromDB().Build()

		players[8] = domaintest.NewPlayerBuilder(playerUUID, start.Add(11*time.Hour).Add(15*time.Minute)).WithGamesPlayed(35).WithExperience(28_800).FromDB().Build()

		players[9] = domaintest.NewPlayerBuilder(playerUUID, start.Add(17*time.Hour).Add(15*time.Minute)).WithGamesPlayed(44).WithExperience(38_800).FromDB().Build()

		sessions := app.ComputeSessions(ctx, players, start, start.Add(24*time.Hour))

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
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2025, time.December, 9, 14, 13, 34, 987_654_321, time.FixedZone("UTC", 3600*0))

		players := make([]domain.PlayerPIT, 3)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(23*time.Hour).Add(5*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).FromDB().Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(23*time.Hour).Add(40*time.Minute)).WithGamesPlayed(17).WithExperience(9_500).FromDB().Build()
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(24*time.Hour).Add(05*time.Minute)).WithGamesPlayed(18).WithExperience(9_900).FromDB().Build()

		sessions := app.ComputeSessions(ctx, players, start, start.Add(24*time.Hour))

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
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2025, time.February, 7, 4, 13, 34, 987_654_321, time.FixedZone("UTC", 3600*-10))

		players := make([]domain.PlayerPIT, 6)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(5*time.Minute)).WithGamesPlayed(15).WithExperience(9_200).FromDB().Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(40*time.Minute)).WithGamesPlayed(16).WithExperience(9_500).FromDB().Build()
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(05*time.Minute)).WithGamesPlayed(17).WithExperience(9_900).FromDB().Build()
		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(45*time.Minute)).WithGamesPlayed(20).WithExperience(10_900).FromDB().Build()
		players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(55*time.Minute)).WithGamesPlayed(21).WithExperience(11_900).FromDB().Build()
		players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(5*time.Hour).Add(15*time.Minute)).WithGamesPlayed(22).WithExperience(12_900).FromDB().Build()

		sessions := app.ComputeSessions(ctx, players, start, start.Add(24*time.Hour))

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
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2025, time.December, 1, 7, 13, 34, 987_654_321, time.FixedZone("UTC", 3600*7))

		players := make([]domain.PlayerPIT, 6)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(5*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).FromDB().Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(40*time.Minute)).WithGamesPlayed(16).WithExperience(9_500).FromDB().Build()
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(05*time.Minute)).WithGamesPlayed(16).WithExperience(9_600).FromDB().Build()
		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(45*time.Minute)).WithGamesPlayed(17).WithExperience(10_900).FromDB().Build()
		players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(55*time.Minute)).WithGamesPlayed(17).WithExperience(10_900).FromDB().Build()
		players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(15*time.Minute)).WithGamesPlayed(17).WithExperience(11_900).FromDB().Build()

		sessions := app.ComputeSessions(ctx, players, start, start.Add(24*time.Hour))

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
		playerUUID := domaintest.NewUUID(t)
		start := time.Date(2025, time.February, 7, 4, 13, 34, 987_654_321, time.FixedZone("UTC", 3600*-10))

		players := make([]domain.PlayerPIT, 6)
		players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(5*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).FromDB().Build()
		players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(40*time.Minute)).WithGamesPlayed(17).WithExperience(9_500).FromDB().Build()
		players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(05*time.Minute)).WithGamesPlayed(18).WithExperience(9_900).FromDB().Build()
		players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(45*time.Minute)).WithGamesPlayed(20).WithExperience(10_900).FromDB().Build()
		players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(55*time.Minute)).WithGamesPlayed(21).WithExperience(11_900).FromDB().Build()
		players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(5*time.Hour).Add(15*time.Minute)).WithGamesPlayed(22).WithExperience(12_900).FromDB().Build()

		sessions := app.ComputeSessions(ctx, players, start, start.Add(24*time.Hour))

		expectedSessions := []domain.Session{
			{
				Start:       players[0],
				End:         players[5],
				Consecutive: true,
			},
		}
		requireEqualSessions(t, expectedSessions, sessions)
	})
}
