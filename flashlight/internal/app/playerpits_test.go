package app_test

import (
	"context"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type mockPlayerPITsRepository struct {
	playerPITs []domain.PlayerPIT
	err        error
}

func (m *mockPlayerPITsRepository) GetPlayerPITs(ctx context.Context, playerUUID string, start, end time.Time) ([]domain.PlayerPIT, error) {
	return m.playerPITs, m.err
}

func newMockPlayerPITsRepository(t *testing.T, playerPITs []domain.PlayerPIT, err error) *mockPlayerPITsRepository {
	if err == nil {
		require.NotNil(t, playerPITs)
	} else {
		require.Nil(t, playerPITs)
	}

	return &mockPlayerPITsRepository{
		playerPITs: playerPITs,
		err:        err,
	}
}

func TestBuildGetPlayerPITs(t *testing.T) {
	t.Parallel()

	now := time.Now().Truncate(time.Millisecond)

	t.Run("success", func(t *testing.T) {
		t.Parallel()

		uuid := domaintest.NewUUID(t)

		timeCases := []struct {
			name  string
			start time.Time
			end   time.Time
		}{
			{
				name:  "-1hr, +1hr",
				start: now.Add(-1 * time.Hour),
				end:   now.Add(1 * time.Hour),
			},
			{
				name:  "-0hr, +1hr",
				start: now,
				end:   now.Add(1 * time.Hour),
			},
			{
				name:  "-1hr, +0hr",
				start: now.Add(-1 * time.Hour),
				end:   now,
			},
			{
				name:  "-1dy, +1dy",
				start: now.Add(-24 * time.Hour),
				end:   now.Add(24 * time.Hour),
			},
			{
				name:  "-2hr, -1hr",
				start: now.Add(-2 * time.Hour),
				end:   now.Add(-1 * time.Hour),
			},
			{
				name:  "+1ms, +1hr",
				start: now.Add(1 * time.Millisecond),
				end:   now.Add(1 * time.Hour),
			},
			{
				name:  "-1hr, -1s",
				start: now.Add(-1 * time.Hour),
				end:   now.Add(-1 * time.Second),
			},
			{
				name:  "-30dy, -15dy",
				start: now.Add(-30 * 24 * time.Hour),
				end:   now.Add(-15 * 24 * time.Hour),
			},
		}

		playerPITsCases := []struct {
			name       string
			playerPITs []domain.PlayerPIT
		}{
			{
				name:       "no data",
				playerPITs: []domain.PlayerPIT{},
			},
			{
				name: "data",
				playerPITs: []domain.PlayerPIT{
					domaintest.NewPlayerBuilder(uuid, now).FromDB().WithExperience(500).Build(),
					domaintest.NewPlayerBuilder(uuid, now.Add(1*time.Minute)).FromDB().WithExperience(501).Build(),
					domaintest.NewPlayerBuilder(uuid, now.Add(2*time.Minute)).FromDB().WithExperience(502).Build(),
				},
			},
		}

		for _, timeCase := range timeCases {
			t.Run(timeCase.name, func(t *testing.T) {
				t.Parallel()
				for _, playerPITCase := range playerPITsCases {
					t.Run(playerPITCase.name, func(t *testing.T) {
						t.Parallel()

						updatePlayerInIntervalCalled := false
						updatePlayerInInterval := func(ctx context.Context, updateUUID string, start, end time.Time) error {
							t.Helper()
							require.Equal(t, uuid, updateUUID)
							require.WithinDuration(t, timeCase.start, start, 0)
							require.WithinDuration(t, timeCase.end, end, 0)
							updatePlayerInIntervalCalled = true
							return nil
						}

						getPlayerPITs := app.BuildGetPlayerPITs(
							newMockPlayerPITsRepository(t, playerPITCase.playerPITs, nil),
							updatePlayerInInterval,
						)

						playerPITs, err := getPlayerPITs(t.Context(), uuid, timeCase.start, timeCase.end)
						require.NoError(t, err)
						require.Equal(t, playerPITCase.playerPITs, playerPITs)

						require.True(t, updatePlayerInIntervalCalled)
					})
				}
			})
		}
	})

	t.Run("update player in interval fails", func(t *testing.T) {
		t.Parallel()

		uuid := domaintest.NewUUID(t)

		start := time.Date(2024, time.March, 1, 0, 0, 0, 0, time.UTC)
		end := time.Date(2024, time.March, 31, 23, 59, 59, 999_999_999, time.UTC)

		expectedPlayerPITs := []domain.PlayerPIT{
			domaintest.NewPlayerBuilder(uuid, now).FromDB().WithExperience(500).Build(),
			domaintest.NewPlayerBuilder(uuid, now).FromDB().WithExperience(501).Build(),
		}

		updatePlayerInIntervalCalled := false
		updatePlayerInInterval := func(ctx context.Context, updateUUID string, updateStart, updateEnd time.Time) error {
			t.Helper()
			require.Equal(t, uuid, updateUUID)
			require.WithinDuration(t, start, updateStart, 0)
			require.WithinDuration(t, end, updateEnd, 0)
			updatePlayerInIntervalCalled = true
			return assert.AnError
		}

		getPlayerPITs := app.BuildGetPlayerPITs(
			newMockPlayerPITsRepository(t, expectedPlayerPITs, nil),
			updatePlayerInInterval,
		)

		playerPITs, err := getPlayerPITs(t.Context(), uuid, start, end)
		// Should not error even if updatePlayerInInterval fails
		require.NoError(t, err)
		require.Equal(t, expectedPlayerPITs, playerPITs)

		require.True(t, updatePlayerInIntervalCalled)
	})
}
