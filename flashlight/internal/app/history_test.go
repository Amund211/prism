package app_test

import (
	"context"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/playerrepository"
	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
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

func newGetAndPersistPlayerWithCache(err error) app.GetAndPersistPlayerWithCache {
	return func(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
		// NOTE: We don't read the value in GetHistory, only the error
		return &domain.PlayerPIT{
			UUID: uuid,
		}, err
	}
}

func TestBuildGetHistory(t *testing.T) {
	t.Parallel()

	now := time.Now()

	nowFunc := func() time.Time {
		return now
	}

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
					// NOTE: Stub players
					{
						UUID:       uuid,
						Experience: 500,
					},
					{
						UUID:       uuid,
						Experience: 501,
					},
				},
			},
		}

		for _, timeCase := range timeCases {
			t.Run(timeCase.name, func(t *testing.T) {
				t.Parallel()
				for _, historyCase := range historyCases {
					t.Run(historyCase.name, func(t *testing.T) {
						t.Parallel()

						getHistory := app.BuildGetHistory(
							newMockHistoryRepository(t, historyCase.history, nil),
							newGetAndPersistPlayerWithCache(nil),
							nowFunc,
						)

						history, err := getHistory(context.Background(), uuid, timeCase.start, timeCase.end, 10)
						require.NoError(t, err)
						require.Equal(t, historyCase.history, history)
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
					// NOTE: Stub players
					{
						UUID:       uuid,
						Experience: 500,
					},
					{
						UUID:       uuid,
						Experience: 501,
					},
				},
			},
		}

		for _, timeCase := range timeCases {
			t.Run(timeCase.name, func(t *testing.T) {
				t.Parallel()
				for _, historyCase := range historyCases {
					t.Run(historyCase.name, func(t *testing.T) {
						t.Parallel()

						getAndPersistPlayerWithCache := func(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
							t.Log("should not call getAndPersistPlayerWithCache when now is outside range")
							t.FailNow()
							return nil, nil
						}

						getHistory := app.BuildGetHistory(
							newMockHistoryRepository(t, historyCase.history, nil),
							getAndPersistPlayerWithCache,
							nowFunc,
						)

						history, err := getHistory(context.Background(), uuid, timeCase.start, timeCase.end, 10)
						require.NoError(t, err)
						require.Equal(t, historyCase.history, history)
					})
				}
			})
		}
	})
}
