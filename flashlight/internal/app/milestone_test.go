package app

import (
	"context"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
	"github.com/stretchr/testify/require"
)

type mockMilestoneRepository struct {
	t                  *testing.T
	expectedGamemode   domain.Gamemode
	expectedStat       domain.Stat
	expectedMilestones []int64
	achievements       []domain.MilestoneAchievement
	err                error
}

func (m *mockMilestoneRepository) FindMilestoneAchievements(ctx context.Context, playerUUID string, gamemode domain.Gamemode, stat domain.Stat, milestones []int64) ([]domain.MilestoneAchievement, error) {
	require.Equal(m.t, m.expectedGamemode, gamemode)
	require.Equal(m.t, m.expectedStat, stat)
	require.Equal(m.t, m.expectedMilestones, milestones)
	return m.achievements, m.err
}

func TestFindMilestoneAchievements(t *testing.T) {
	ctx := context.Background()
	playerUUID := domaintest.NewUUID(t)

	getAndPersistPlayerWithoutCache := func(ctx context.Context, playerUUIDArg string) (*domain.PlayerPIT, error) {
		require.Equal(t, playerUUID, playerUUIDArg)
		return nil, nil
	}

	t.Run("stars converted to experience", func(t *testing.T) {
		p1 := *domaintest.NewPlayerBuilder(playerUUID, time.Date(2024, time.January, 1, 12, 0, 0, 0, time.UTC)).WithExperience(550).Build()
		p2 := *domaintest.NewPlayerBuilder(playerUUID, time.Date(2024, time.January, 5, 15, 30, 0, 0, time.UTC)).WithExperience(3600).Build()
		p3 := *domaintest.NewPlayerBuilder(playerUUID, time.Date(2024, time.March, 5, 15, 30, 0, 0, time.UTC)).WithExperience(487_550).Build()

		starMilestones := []int64{1, 3, 100}
		expMilestones := []int64{domain.StarsToExperience(1), domain.StarsToExperience(3), domain.StarsToExperience(100)}

		mockRepo := &mockMilestoneRepository{
			t:                  t,
			expectedGamemode:   domain.GamemodeOverall,
			expectedStat:       domain.StatExperience,
			expectedMilestones: expMilestones,
			achievements: []domain.MilestoneAchievement{
				{
					Milestone: expMilestones[0],
					After:     &domain.MilestoneAchievementStats{Player: p1, Value: int64(p1.Experience)},
				},
				{
					Milestone: expMilestones[1],
					After:     &domain.MilestoneAchievementStats{Player: p2, Value: int64(p2.Experience)},
				},
				{
					Milestone: expMilestones[2],
					After:     &domain.MilestoneAchievementStats{Player: p3, Value: int64(p3.Experience)},
				},
			},
		}
		findMilestones := BuildFindMilestoneAchievements(mockRepo, getAndPersistPlayerWithoutCache)

		achievements, err := findMilestones(ctx, playerUUID, domain.GamemodeOverall, domain.StatStars, starMilestones)
		require.NoError(t, err)

		require.Equal(t, []domain.MilestoneAchievement{
			{
				Milestone: 1,
				After:     &domain.MilestoneAchievementStats{Player: p1, Value: 1},
			},
			{
				Milestone: 3,
				After:     &domain.MilestoneAchievementStats{Player: p2, Value: 3},
			},
			{
				Milestone: 100,
				After:     &domain.MilestoneAchievementStats{Player: p3, Value: 101},
			},
		}, achievements)
	})

	t.Run("experience milestones passed through", func(t *testing.T) {
		milestones := []int64{1000, 2000, 3000}

		p1 := *domaintest.NewPlayerBuilder(playerUUID, time.Date(2024, time.March, 01, 10, 0, 0, 0, time.UTC)).WithExperience(1050).Build()
		p2 := *domaintest.NewPlayerBuilder(playerUUID, time.Date(2024, time.March, 10, 16, 45, 0, 0, time.UTC)).WithExperience(3200).Build()

		mockRepo := &mockMilestoneRepository{
			t:                  t,
			expectedGamemode:   domain.GamemodeOverall,
			expectedStat:       domain.StatExperience,
			expectedMilestones: milestones,
			achievements: []domain.MilestoneAchievement{
				{
					Milestone: milestones[0],
					After: &domain.MilestoneAchievementStats{
						Player: p1,
						Value:  1050,
					},
				},
				{
					Milestone: milestones[2],
					After: &domain.MilestoneAchievementStats{
						Player: p2,
						Value:  3200,
					},
				},
			},
		}
		findMilestones := BuildFindMilestoneAchievements(mockRepo, getAndPersistPlayerWithoutCache)

		achievements, err := findMilestones(ctx, playerUUID, domain.GamemodeOverall, domain.StatExperience, milestones)
		require.NoError(t, err)

		require.Equal(t, []domain.MilestoneAchievement{
			{
				Milestone: 1000,
				After: &domain.MilestoneAchievementStats{
					Player: p1,
					Value:  1050,
				},
			},
			{
				Milestone: 3000,
				After: &domain.MilestoneAchievementStats{
					Player: p2,
					Value:  3200,
				},
			},
		}, achievements)

	})

	t.Run("invalid UUID", func(t *testing.T) {
		mockRepo := &mockMilestoneRepository{}
		findMilestones := BuildFindMilestoneAchievements(mockRepo, getAndPersistPlayerWithoutCache)

		_, err := findMilestones(ctx, "invalid-uuid", domain.GamemodeOverall, domain.StatStars, []int64{100})

		require.Error(t, err)
		require.Contains(t, err.Error(), "UUID is not normalized")
	})
}
