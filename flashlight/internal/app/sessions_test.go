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

func newGetAndPersistPlayerWithCacheForSessions(err error) app.GetAndPersistPlayerWithCache {
	return func(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
		// NOTE: We don't read the value in GetHistory, only the error
		return &domain.PlayerPIT{
			UUID: uuid,
		}, err
	}
}

func TestBuildGetSessions(t *testing.T) {
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
						// NOTE: Stub players
						Start: domain.PlayerPIT{
							UUID:       uuid,
							Experience: 500,
						},
						End: domain.PlayerPIT{
							UUID:       uuid,
							Experience: 501,
						},
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

						getSessions := app.BuildGetSessions(
							newMockSessionsRepository(t, sessionsCase.sessions, nil),
							newGetAndPersistPlayerWithCacheForSessions(nil),
							nowFunc,
						)

						sessions, err := getSessions(context.Background(), uuid, timeCase.start, timeCase.end)
						require.NoError(t, err)
						require.Equal(t, sessionsCase.sessions, sessions)
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
						// NOTE: Stub players
						Start: domain.PlayerPIT{
							UUID:       uuid,
							Experience: 500,
						},
						End: domain.PlayerPIT{
							UUID:       uuid,
							Experience: 501,
						},
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

						getAndPersistPlayerWithCache := func(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
							t.Log("should not call getAndPersistPlayerWithCache when now is outside range")
							t.FailNow()
							return nil, nil
						}

						getSessions := app.BuildGetSessions(
							newMockSessionsRepository(t, sessionsCase.sessions, nil),
							getAndPersistPlayerWithCache,
							nowFunc,
						)

						sessions, err := getSessions(context.Background(), uuid, timeCase.start, timeCase.end)
						require.NoError(t, err)
						require.Equal(t, sessionsCase.sessions, sessions)
					})
				}
			})
		}
	})
}
