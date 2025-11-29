package playerrepository

import (
	"context"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
)

type PlayerRepository interface {
	StorePlayer(ctx context.Context, player *domain.PlayerPIT) error
	GetHistory(ctx context.Context, playerUUID string, start, end time.Time, limit int) ([]domain.PlayerPIT, error)
	GetPlayerPITs(ctx context.Context, playerUUID string, start, end time.Time) ([]domain.PlayerPIT, error)
	FindMilestoneAchievements(ctx context.Context, playerUUID string, gamemode domain.Gamemode, stat domain.Stat, milestones []int64) ([]domain.MilestoneAchievement, error)
}
