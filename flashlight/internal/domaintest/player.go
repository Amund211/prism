package domaintest

import (
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/google/uuid"
	"github.com/stretchr/testify/require"
)

type playerBuilder struct {
	player *domain.PlayerPIT
}

// Utility method for setting only the GamesPlayed field in Overall stats
func (pb *playerBuilder) WithGamesPlayed(gamesPlayed int) *playerBuilder {
	pb.player.Overall.GamesPlayed = gamesPlayed
	return pb
}

func (pb *playerBuilder) WithExperience(exp int64) *playerBuilder {
	pb.player.Experience = exp
	return pb
}

func (pb *playerBuilder) WithOverallStats(stats domain.GamemodeStatsPIT) *playerBuilder {
	pb.player.Overall = stats
	return pb
}

func (pb *playerBuilder) WithDBID(dbID *string) *playerBuilder {
	pb.player.DBID = dbID
	return pb
}

func (pb *playerBuilder) FromDB() *playerBuilder {
	uuidv7, err := uuid.NewV7()
	if err != nil {
		panic("failed to generate UUIDv7 for player DBID")
	}
	dbID := uuidv7.String()
	return pb.WithDBID(&dbID)
}

func (pb *playerBuilder) Build() domain.PlayerPIT {
	return *pb.player
}

func (pb *playerBuilder) BuildPtr() *domain.PlayerPIT {
	// Make a copy, so further mutations to the builder don't affect the returned player
	player := pb.Build()
	return &player
}

func NewPlayerBuilder(uuid string, queriedAt time.Time) *playerBuilder {
	player := &domain.PlayerPIT{
		QueriedAt:  queriedAt,
		UUID:       uuid,
		Experience: 500,
	}
	return &playerBuilder{
		player: player,
	}
}

type statsBuilder struct {
	stats *domain.GamemodeStatsPIT
}

func (sb *statsBuilder) WithGamesPlayed(gamesPlayed int) *statsBuilder {
	sb.stats.GamesPlayed = gamesPlayed
	return sb
}

func (sb *statsBuilder) WithFinalKills(finalKills int) *statsBuilder {
	sb.stats.FinalKills = finalKills
	return sb
}

func (sb *statsBuilder) Build() domain.GamemodeStatsPIT {
	return *sb.stats
}

func NewStatsBuilder() *statsBuilder {
	return &statsBuilder{
		stats: &domain.GamemodeStatsPIT{},
	}
}

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
