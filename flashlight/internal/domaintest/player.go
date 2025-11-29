package domaintest

import (
	"time"

	"github.com/Amund211/flashlight/internal/domain"
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
