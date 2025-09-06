package domaintest

import (
	"time"

	"github.com/Amund211/flashlight/internal/domain"
)

type playerBuilder struct {
	player *domain.PlayerPIT
}

func (pb *playerBuilder) WithGamesPlayed(gamesPlayed int) *playerBuilder {
	pb.player.Overall.GamesPlayed = gamesPlayed
	return pb
}

func (pb *playerBuilder) WithExperience(exp float64) *playerBuilder {
	pb.player.Experience = exp
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
