package playerrepository

import (
	"context"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
)

type PlayerRepository interface {
	StorePlayer(ctx context.Context, player *domain.PlayerPIT) error
	// GetPlayer returns the most recently stored PlayerPIT for the given UUID.
	// Returns domain.ErrPlayerNotFound if no stats are stored for the UUID.
	GetPlayer(ctx context.Context, playerUUID string) (*domain.PlayerPIT, error)
	// CountStats returns the number of stored stat records for the given UUID.
	CountStats(ctx context.Context, playerUUID string) (int, error)
	GetHistory(ctx context.Context, playerUUID string, start, end time.Time, limit int) ([]domain.PlayerPIT, error)
	GetPlayerPITs(ctx context.Context, playerUUID string, start, end time.Time) ([]domain.PlayerPIT, error)
	FindMilestoneAchievements(ctx context.Context, playerUUID string, gamemode domain.Gamemode, stat domain.Stat, milestones []int64) ([]domain.MilestoneAchievement, error)
}
