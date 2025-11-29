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

type mockSessionsRepository struct {
	playerrepository.StubPlayerRepository
	sessions []domain.Session
	err      error
}

func (m *mockSessionsRepository) GetSessions(ctx context.Context, playerUUID string, start, end time.Time) ([]domain.Session, error) {
	return m.sessions, m.err
}

func newMockSessionsRepository(t *testing.T, sessions []domain.Session, err error) *mockSessionsRepository {
	if err == nil {
		require.NotNil(t, sessions)
	} else {
		require.Nil(t, sessions)
	}

	return &mockSessionsRepository{
		sessions: sessions,
		err:      err,
	}
}

func TestBuildGetSessions(t *testing.T) {
	t.Parallel()

	now := time.Now()

	t.Run("success", func(t *testing.T) {
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

		sessionsCases := []struct {
			name     string
			sessions []domain.Session
		}{
			{
				name:     "empty sessions",
				sessions: []domain.Session{},
			},
			{
				name: "non-empty sessions",
				sessions: []domain.Session{
					{
						Start:       domaintest.NewPlayerBuilder(uuid, now).WithExperience(500).Build(),
						End:         domaintest.NewPlayerBuilder(uuid, now).WithExperience(501).Build(),
						Consecutive: true,
					},
				},
			},
		}

		for _, timeCase := range timeCases {
			t.Run(timeCase.name, func(t *testing.T) {
				t.Parallel()
				for _, sessionsCase := range sessionsCases {
					t.Run(sessionsCase.name, func(t *testing.T) {
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

						getSessions := app.BuildGetSessions(
							newMockSessionsRepository(t, sessionsCase.sessions, nil),
							updatePlayerInInterval,
						)

						sessions, err := getSessions(t.Context(), uuid, timeCase.start, timeCase.end)
						require.NoError(t, err)
						require.Equal(t, sessionsCase.sessions, sessions)

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

		expectedSessions := []domain.Session{
			{
				Start:       domaintest.NewPlayerBuilder(uuid, now).WithExperience(500).Build(),
				End:         domaintest.NewPlayerBuilder(uuid, now).WithExperience(501).Build(),
				Consecutive: true,
			},
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

		getSessions := app.BuildGetSessions(
			newMockSessionsRepository(t, expectedSessions, nil),
			updatePlayerInInterval,
		)

		sessions, err := getSessions(t.Context(), uuid, start, end)
		// Should not error even if updatePlayerInInterval fails
		require.NoError(t, err)
		require.Equal(t, expectedSessions, sessions)

		require.True(t, updatePlayerInIntervalCalled)
	})
}
