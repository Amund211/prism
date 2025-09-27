package app_test

import (
	"context"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/playerrepository"
	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type mockHistoryRepository struct {
	playerrepository.StubPlayerRepository
	history []domain.PlayerPIT
	err     error
}

func (m *mockHistoryRepository) GetHistory(ctx context.Context, playerUUID string, start, end time.Time, limit int) ([]domain.PlayerPIT, error) {
	return m.history, m.err
}

func newMockHistoryRepository(t *testing.T, history []domain.PlayerPIT, err error) *mockHistoryRepository {
	if err == nil {
		require.NotNil(t, history)
	} else {
		require.Nil(t, history)
	}

	return &mockHistoryRepository{
		history: history,
		err:     err,
	}
}

func newGetAndPersistPlayerWithCacheForHistory(err error) app.GetAndPersistPlayerWithCache {
	return func(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
		// NOTE: We don't read the value in GetHistory, only the error
		player := domaintest.NewPlayerBuilder(uuid, time.Now()).BuildPtr()
		return player, err
	}
}

func TestBuildGetHistory(t *testing.T) {
	t.Parallel()

	now := time.Now()

	t.Run("now within range", func(t *testing.T) {
		t.Parallel()

		uuid := "12345678-1234-1234-1234-123456789012"

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
		}

		historyCases := []struct {
			name    string
			history []domain.PlayerPIT
		}{
			{
				name:    "empty history",
				history: []domain.PlayerPIT{},
			},
			{
				name: "non-empty history",
				history: []domain.PlayerPIT{
					domaintest.NewPlayerBuilder(uuid, now).WithExperience(500).Build(),
					domaintest.NewPlayerBuilder(uuid, now).WithExperience(501).Build(),
				},
			},
		}

		for _, timeCase := range timeCases {
			t.Run(timeCase.name, func(t *testing.T) {
				t.Parallel()
				for _, historyCase := range historyCases {
					t.Run(historyCase.name, func(t *testing.T) {
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

						getHistory := app.BuildGetHistory(
							newMockHistoryRepository(t, historyCase.history, nil),
							updatePlayerInInterval,
						)

						history, err := getHistory(t.Context(), uuid, timeCase.start, timeCase.end, 10)
						require.NoError(t, err)
						require.Equal(t, historyCase.history, history)

						require.True(t, updatePlayerInIntervalCalled)
					})
				}
			})
		}
	})

	t.Run("now outside range", func(t *testing.T) {
		t.Parallel()

		uuid := "12345678-1234-1234-1234-123456789012"

		timeCases := []struct {
			name  string
			start time.Time
			end   time.Time
		}{
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

		historyCases := []struct {
			name    string
			history []domain.PlayerPIT
		}{
			{
				name:    "empty history",
				history: []domain.PlayerPIT{},
			},
			{
				name: "non-empty history",
				history: []domain.PlayerPIT{
					domaintest.NewPlayerBuilder(uuid, now).WithExperience(500).Build(),
					domaintest.NewPlayerBuilder(uuid, now).WithExperience(501).Build(),
				},
			},
		}

		for _, timeCase := range timeCases {
			t.Run(timeCase.name, func(t *testing.T) {
				t.Parallel()
				for _, historyCase := range historyCases {
					t.Run(historyCase.name, func(t *testing.T) {
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

						getHistory := app.BuildGetHistory(
							newMockHistoryRepository(t, historyCase.history, nil),
							updatePlayerInInterval,
						)

						history, err := getHistory(t.Context(), uuid, timeCase.start, timeCase.end, 10)
						require.NoError(t, err)
						require.Equal(t, historyCase.history, history)

						require.True(t, updatePlayerInIntervalCalled)
					})
				}
			})
		}
	})

	t.Run("update player in interval fails", func(t *testing.T) {
		t.Parallel()

		uuid := "12345678-1234-1234-1234-123456789012"

		start := time.Date(2024, time.March, 1, 0, 0, 0, 0, time.UTC)
		end := time.Date(2024, time.March, 31, 23, 59, 59, 999_999_999, time.UTC)

		expectedHistory := []domain.PlayerPIT{
			domaintest.NewPlayerBuilder(uuid, now).WithExperience(500).Build(),
			domaintest.NewPlayerBuilder(uuid, now).WithExperience(501).Build(),
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

		getHistory := app.BuildGetHistory(
			newMockHistoryRepository(t, expectedHistory, nil),
			updatePlayerInInterval,
		)

		history, err := getHistory(t.Context(), uuid, start, end, 10)
		// Should not error even if updatePlayerInInterval fails
		require.NoError(t, err)
		require.Equal(t, expectedHistory, history)

		require.True(t, updatePlayerInIntervalCalled)
	})
}
