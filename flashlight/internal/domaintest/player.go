package domaintest

import (
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/domain"
)

type playerBuilder struct {
	player                       *domain.PlayerPIT
	solo, doubles, threes, fours *statsBuilder
	overallWinstreak             *int
	// Whether the player should get a random db id on Build()
	fromDB bool
}

func (pb *playerBuilder) Solo() *statsBuilder    { return pb.solo }
func (pb *playerBuilder) Doubles() *statsBuilder { return pb.doubles }
func (pb *playerBuilder) Threes() *statsBuilder  { return pb.threes }
func (pb *playerBuilder) Fours() *statsBuilder   { return pb.fours }

func (pb *playerBuilder) WithExperience(exp int64) *playerBuilder {
	pb.player.Experience = exp
	return pb
}

func (pb *playerBuilder) WithDBID(dbID *string) *playerBuilder {
	if pb.fromDB {
		panic("WithDBID() cannot be used with FromDB()")
	}
	pb.player.DBID = dbID
	return pb
}

func (pb *playerBuilder) FromDB() *playerBuilder {
	if pb.player.DBID != nil {
		panic("FromDB() cannot be used with WithDBID()")
	}
	pb.fromDB = true
	return pb
}

func (pb *playerBuilder) WithOverallWinstreak(winstreak int) *playerBuilder {
	pb.overallWinstreak = &winstreak
	return pb
}

func (pb *playerBuilder) Build() domain.PlayerPIT {
	player := *pb.player

	// Clone every pointer field so later builder mutations can't reach
	// already-built players through shared pointers.
	player.DBID = clonePtr(player.DBID)
	player.Displayname = clonePtr(player.Displayname)
	player.LastLogin = clonePtr(player.LastLogin)
	player.LastLogout = clonePtr(player.LastLogout)
	player.Solo.Winstreak = clonePtr(player.Solo.Winstreak)
	player.Doubles.Winstreak = clonePtr(player.Doubles.Winstreak)
	player.Threes.Winstreak = clonePtr(player.Threes.Winstreak)
	player.Fours.Winstreak = clonePtr(player.Fours.Winstreak)

	if pb.fromDB {
		uuidv7, err := uuid.NewV7()
		if err != nil {
			panic("failed to generate UUIDv7 for player DBID")
		}
		dbID := uuidv7.String()
		player.DBID = &dbID
	}

	winstreakAPIEnabled := pb.solo.stats.Winstreak != nil ||
		pb.doubles.stats.Winstreak != nil ||
		pb.threes.stats.Winstreak != nil ||
		pb.fours.stats.Winstreak != nil ||
		pb.overallWinstreak != nil

	if winstreakAPIEnabled {
		// Winstreak API enablement is all or nothing.
		// If one gamemode had a winstreak, but another didn't, that gamemode
		// actually had winstreak 0.
		if player.Solo.Winstreak == nil {
			player.Solo.Winstreak = new(0)
		}
		if player.Doubles.Winstreak == nil {
			player.Doubles.Winstreak = new(0)
		}
		if player.Threes.Winstreak == nil {
			player.Threes.Winstreak = new(0)
		}
		if player.Fours.Winstreak == nil {
			player.Fours.Winstreak = new(0)
		}
	}

	player.Overall = computeOverallStats(player.Solo, player.Doubles, player.Threes, player.Fours)

	if pb.overallWinstreak != nil {
		player.Overall.Winstreak = pb.overallWinstreak
	}

	return player
}

func clonePtr[T any](p *T) *T {
	if p == nil {
		return nil
	}
	v := *p
	return &v
}

func (pb *playerBuilder) BuildPtr() *domain.PlayerPIT {
	// Make a copy, so further mutations to the builder don't affect the returned player
	player := pb.Build()
	return &player
}

func computeOverallStats(modes ...domain.GamemodeStatsPIT) domain.GamemodeStatsPIT {
	var overall domain.GamemodeStatsPIT

	for _, m := range modes {
		overall.GamesPlayed += m.GamesPlayed
		overall.Wins += m.Wins
		overall.Losses += m.Losses
		overall.BedsBroken += m.BedsBroken
		overall.BedsLost += m.BedsLost
		overall.FinalKills += m.FinalKills
		overall.FinalDeaths += m.FinalDeaths
		overall.Kills += m.Kills
		overall.Deaths += m.Deaths
		if m.Winstreak != nil {
			// Overall winstreak is not uniquely determined by gamemode winstreaks
			// The set of possible values are
			//     [min(gamemode winstreaks), sum(gamemode winstreaks)]
			// Doing min here.
			if overall.Winstreak == nil || *m.Winstreak < *overall.Winstreak {
				overall.Winstreak = m.Winstreak
			}
		}
	}

	return overall
}

func NewPlayerBuilder(uuid string, queriedAt time.Time) *playerBuilder {
	player := &domain.PlayerPIT{
		QueriedAt:  queriedAt,
		UUID:       uuid,
		Experience: 500,
	}
	pb := &playerBuilder{player: player}
	pb.solo = &statsBuilder{stats: &player.Solo, parent: pb}
	pb.doubles = &statsBuilder{stats: &player.Doubles, parent: pb}
	pb.threes = &statsBuilder{stats: &player.Threes, parent: pb}
	pb.fours = &statsBuilder{stats: &player.Fours, parent: pb}
	return pb
}

// statsBuilder mutates a single gamemode's stats on its parent
// playerBuilder. Build/BuildPtr delegate to the parent so chains like
// NewPlayerBuilder(...).Fours().WithGamesPlayed(10).Build() work inline.
type statsBuilder struct {
	stats  *domain.GamemodeStatsPIT
	parent *playerBuilder
}

func (sb *statsBuilder) WithWinstreak(winstreak int) *statsBuilder {
	sb.stats.Winstreak = &winstreak
	return sb
}

func (sb *statsBuilder) WithGamesPlayed(gamesPlayed int) *statsBuilder {
	sb.stats.GamesPlayed = gamesPlayed
	return sb
}

func (sb *statsBuilder) WithWins(wins int) *statsBuilder {
	sb.stats.Wins = wins
	return sb
}

func (sb *statsBuilder) WithLosses(losses int) *statsBuilder {
	sb.stats.Losses = losses
	return sb
}

func (sb *statsBuilder) WithBedsBroken(bedsBroken int) *statsBuilder {
	sb.stats.BedsBroken = bedsBroken
	return sb
}

func (sb *statsBuilder) WithBedsLost(bedsLost int) *statsBuilder {
	sb.stats.BedsLost = bedsLost
	return sb
}

func (sb *statsBuilder) WithFinalKills(finalKills int) *statsBuilder {
	sb.stats.FinalKills = finalKills
	return sb
}

func (sb *statsBuilder) WithFinalDeaths(finalDeaths int) *statsBuilder {
	sb.stats.FinalDeaths = finalDeaths
	return sb
}

func (sb *statsBuilder) WithKills(kills int) *statsBuilder {
	sb.stats.Kills = kills
	return sb
}

func (sb *statsBuilder) WithDeaths(deaths int) *statsBuilder {
	sb.stats.Deaths = deaths
	return sb
}

// Navigation to other gamemodes on the parent player, so chains like
// Fours().WithGamesPlayed(10).Threes().WithFinalKills(5).Build() flow inline.
func (sb *statsBuilder) Solo() *statsBuilder    { return sb.parent.solo }
func (sb *statsBuilder) Doubles() *statsBuilder { return sb.parent.doubles }
func (sb *statsBuilder) Threes() *statsBuilder  { return sb.parent.threes }
func (sb *statsBuilder) Fours() *statsBuilder   { return sb.parent.fours }

func (sb *statsBuilder) Build() domain.PlayerPIT     { return sb.parent.Build() }
func (sb *statsBuilder) BuildPtr() *domain.PlayerPIT { return sb.parent.BuildPtr() }

func RequireEqualStats(t *testing.T, expected, actual domain.GamemodeStatsPIT) {
	t.Helper()

	if expected.Winstreak == nil {
		require.Nil(t, actual.Winstreak)
	} else {
		require.NotNil(t, actual.Winstreak)
		require.Equal(t, *expected.Winstreak, *actual.Winstreak)
	}

	require.Equal(t, expected.GamesPlayed, actual.GamesPlayed)
	require.Equal(t, expected.Wins, actual.Wins)
	require.Equal(t, expected.Losses, actual.Losses)
	require.Equal(t, expected.BedsBroken, actual.BedsBroken)
	require.Equal(t, expected.BedsLost, actual.BedsLost)
	require.Equal(t, expected.FinalKills, actual.FinalKills)
	require.Equal(t, expected.FinalDeaths, actual.FinalDeaths)
	require.Equal(t, expected.Kills, actual.Kills)
	require.Equal(t, expected.Deaths, actual.Deaths)
}
