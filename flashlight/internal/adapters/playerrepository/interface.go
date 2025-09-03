package playerrepository

import (
	"context"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
)

type PlayerRepository interface {
	StorePlayer(ctx context.Context, player *domain.PlayerPIT) error
	GetHistory(ctx context.Context, playerUUID string, start, end time.Time, limit int) ([]domain.PlayerPIT, error)
	GetSessions(ctx context.Context, playerUUID string, start, end time.Time) ([]domain.Session, error)
	FindMilestoneAchievements(ctx context.Context, playerUUID string, gamemode domain.Gamemode, stat domain.Stat, milestones []int64) ([]domain.MilestoneAchievement, error)
}
