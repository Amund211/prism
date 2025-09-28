package app

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/adapters/playerrepository"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

const UUID = "01234567-89ab-cdef-0123-456789abcdef"

type panicPlayerProvider struct {
	t *testing.T
}

func (p *panicPlayerProvider) GetPlayer(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
	p.t.Helper()
	p.t.Fatal("should not be called")
	return nil, nil
}

type mockedPlayerProvider struct {
	t      *testing.T
	player *domain.PlayerPIT
	err    error
}

func (m *mockedPlayerProvider) GetPlayer(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
	m.t.Helper()

	require.Equal(m.t, UUID, uuid)

	return m.player, m.err
}

func TestGetAndPersistPlayer(t *testing.T) {
	t.Parallel()

	now := time.Now()
	t.Run("stats are not created if they already exist", func(t *testing.T) {
		t.Parallel()

		provider := &mockedPlayerProvider{
			t:      t,
			player: domaintest.NewPlayerBuilder(UUID, now).WithExperience(500).BuildPtr(),
			err:    nil,
		}
		panicProvider := &panicPlayerProvider{t: t}
		cache := cache.NewBasicCache[*domain.PlayerPIT]()

		_, err := BuildGetAndPersistPlayerWithCache(cache, provider, playerrepository.NewStubPlayerRepository())(t.Context(), UUID)
		require.NoError(t, err)

		_, err = BuildGetAndPersistPlayerWithCache(cache, panicProvider, playerrepository.NewStubPlayerRepository())(t.Context(), UUID)
		require.NoError(t, err)
	})

	t.Run("provider errors are passed through", func(t *testing.T) {
		t.Parallel()

		for _, providerErr := range []error{
			domain.ErrPlayerNotFound,
			domain.ErrTemporarilyUnavailable,
		} {
			provider := &mockedPlayerProvider{
				t:      t,
				player: nil,
				err:    providerErr,
			}
			cache := cache.NewBasicCache[*domain.PlayerPIT]()

			_, err := BuildGetAndPersistPlayerWithCache(cache, provider, playerrepository.NewStubPlayerRepository())(t.Context(), "01234567-89ab-cdef-0123-456789abcdef")
			require.ErrorIs(t, err, providerErr)
		}
	})

	t.Run("invalid uuids should not be passed to get and persist with cache", func(t *testing.T) {
		t.Parallel()

		provider := &panicPlayerProvider{t: t}
		cache := cache.NewBasicCache[*domain.PlayerPIT]()

		for _, uuid := range []string{
			"",
			"invalid",
			"01234567-89ab-xxxx-0123-456789abcdef",
			"01234567-89ab-cdef-0123-456789abcde",
			"01234567-89ab-cdef-0123-456789abcdefg",
			"01234567-89ab-cdef-0123-456789abcdefg",
			"01234567-89ab-cdef-0123-456789abcdefg1234",
			"01---23456789aBCDef0123456789aBcdef",
		} {
			t.Run(fmt.Sprintf("UUID: '%s'", uuid), func(t *testing.T) {
				t.Parallel()

				_, err := BuildGetAndPersistPlayerWithCache(cache, provider, playerrepository.NewStubPlayerRepository())(t.Context(), uuid)
				require.Error(t, err)
			})
		}
	})
}

func TestUpdatePlayerInInterval(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name         string
		start        time.Time
		end          time.Time
		now          time.Time
		shouldUpdate bool
	}{
		{
			name:         "current interval",
			start:        time.Date(2024, time.March, 12, 0, 0, 0, 0, time.UTC),
			end:          time.Date(2024, time.March, 26, 23, 59, 59, 999_999_999, time.UTC),
			now:          time.Date(2024, time.March, 17, 12, 0, 0, 0, time.UTC),
			shouldUpdate: true,
		},
		{
			name:         "interval in the past",
			start:        time.Date(2023, time.January, 1, 0, 0, 0, 0, time.UTC),
			end:          time.Date(2023, time.January, 2, 0, 0, 0, 0, time.UTC),
			now:          time.Date(2023, time.January, 3, 0, 0, 0, 0, time.UTC),
			shouldUpdate: false,
		},
		{
			name:         "interval in the future",
			start:        time.Date(2023, time.January, 12, 0, 0, 0, 0, time.UTC),
			end:          time.Date(2023, time.January, 13, 0, 0, 0, 0, time.UTC),
			now:          time.Date(2023, time.January, 1, 0, 0, 0, 0, time.UTC),
			shouldUpdate: false,
		},
		{
			name:         "start=now",
			start:        time.Date(2023, time.January, 1, 0, 0, 0, 0, time.UTC),
			end:          time.Date(2023, time.January, 2, 0, 0, 0, 0, time.UTC),
			now:          time.Date(2023, time.January, 1, 0, 0, 0, 0, time.UTC),
			shouldUpdate: true,
		},
		{
			name:  "end=now",
			start: time.Date(2023, time.January, 1, 0, 0, 0, 0, time.UTC),
			end:   time.Date(2023, time.January, 2, 0, 0, 0, 0, time.UTC),
			now:   time.Date(2023, time.January, 2, 0, 0, 0, 0, time.UTC),
			// NOTE: Not really any point in updating, as the time will be outside the interval by the time the new stats come in
			shouldUpdate: true,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			testUUID := "01234567-9999-9999-0123-456789abcdef"

			updated := false
			getAndPersist := func(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
				t.Helper()
				require.Equal(t, testUUID, uuid)
				updated = true
				return nil, nil
			}

			updatePlayerInInterval := BuildUpdatePlayerInInterval(getAndPersist, func() time.Time { return tc.now })

			err := updatePlayerInInterval(t.Context(), testUUID, tc.start, tc.end)
			require.NoError(t, err)

			require.Equal(t, tc.shouldUpdate, updated)
		})
	}

	t.Run("getAndPersist errors", func(t *testing.T) {
		t.Parallel()

		now := time.Now()
		start := now.Add(-time.Hour)
		end := now.Add(time.Hour)

		testUUID := "01234567-0000-9999-0123-456789abcdef"

		called := false
		getAndPersist := func(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
			t.Helper()
			require.Equal(t, testUUID, uuid)
			called = true
			return nil, assert.AnError
		}

		updatePlayerInInterval := BuildUpdatePlayerInInterval(getAndPersist, func() time.Time { return now })

		err := updatePlayerInInterval(t.Context(), testUUID, start, end)
		require.ErrorIs(t, err, assert.AnError)

		require.True(t, called)
	})
}
