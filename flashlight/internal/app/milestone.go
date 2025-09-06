package app

import (
	"context"
	"fmt"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

type milestonePlayerRepository interface {
	FindMilestoneAchievements(ctx context.Context, playerUUID string, gamemode domain.Gamemode, stat domain.Stat, milestones []int64) ([]domain.MilestoneAchievement, error)
}

type FindMilestoneAchievements func(ctx context.Context, playerUUID string, gamemode domain.Gamemode, stat domain.Stat, milestones []int64) ([]domain.MilestoneAchievement, error)

func BuildFindMilestoneAchievements(
	repo milestonePlayerRepository,
	getAndPersistPlayerWithCache GetAndPersistPlayerWithCache,
) FindMilestoneAchievements {
	return func(ctx context.Context, playerUUID string, gamemode domain.Gamemode, stat domain.Stat, milestones []int64) ([]domain.MilestoneAchievement, error) {
		if !strutils.UUIDIsNormalized(playerUUID) {
			err := fmt.Errorf("UUID is not normalized")
			reporting.Report(ctx, err, map[string]string{
				"uuid": playerUUID,
			})
			return nil, err
		}

		// Ensure the repository is updated with the latest data
		// NOTE: GetAndPersistPlayerWithCache implementations handle their own error reporting
		getAndPersistPlayerWithCache(ctx, playerUUID)

		// Convert star milestones to experience milestones
		var convertedMilestones []int64
		originalStat := stat
		if stat == domain.StatStars {
			convertedMilestones = make([]int64, len(milestones))
			for i, starMilestone := range milestones {
				convertedMilestones[i] = domain.StarsToExperience(int(starMilestone))
			}
			// Change stat to experience since that's what the repository supports
			stat = domain.StatExperience
		} else {
			convertedMilestones = milestones
		}

		achievements, err := repo.FindMilestoneAchievements(ctx, playerUUID, gamemode, stat, convertedMilestones)
		if err != nil {
			return nil, fmt.Errorf("failed to find milestone achievements: %w", err)
		}

		// Convert experience back to stars if needed
		var convertedAchievements []domain.MilestoneAchievement
		if originalStat == domain.StatStars {
			convertedAchievements = make([]domain.MilestoneAchievement, len(achievements))
			for i, achievement := range achievements {
				convertedAchievements[i] = domain.MilestoneAchievement{
					Milestone: int64(domain.ExperienceToStars(achievement.Milestone)),
					After: func() *domain.MilestoneAchievementStats {
						if achievement.After == nil {
							return nil
						}
						return &domain.MilestoneAchievementStats{
							Player: achievement.After.Player,
							Value:  int64(domain.ExperienceToStars(achievement.After.Value)),
						}
					}(),
				}
			}
		} else {
			convertedAchievements = achievements
		}

		return convertedAchievements, nil
	}
}
