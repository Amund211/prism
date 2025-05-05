package app

import (
	"context"
	"fmt"
	"testing"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/adapters/playerrepository"
	"github.com/Amund211/flashlight/internal/domain"
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
	t.Run("stats are not created if they already exist", func(t *testing.T) {
		provider := &mockedPlayerProvider{
			t:      t,
			player: &domain.PlayerPIT{UUID: UUID, Experience: 500, Overall: domain.GamemodeStatsPIT{FinalKills: 0}},
			err:    nil,
		}
		panicProvider := &panicPlayerProvider{t: t}
		cache := cache.NewBasicCache[*domain.PlayerPIT]()

		_, err := BuildGetAndPersistPlayerWithCache(cache, provider, playerrepository.NewStubPlayerRepository())(context.Background(), UUID)
		require.NoError(t, err)

		_, err = BuildGetAndPersistPlayerWithCache(cache, panicProvider, playerrepository.NewStubPlayerRepository())(context.Background(), UUID)
		require.NoError(t, err)
	})

	t.Run("provider errors are passed through", func(t *testing.T) {
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

			_, err := BuildGetAndPersistPlayerWithCache(cache, provider, playerrepository.NewStubPlayerRepository())(context.Background(), "01234567-89ab-cdef-0123-456789abcdef")
			require.ErrorIs(t, err, providerErr)
		}
	})

	t.Run("invalid uuids should not be passed to get and persist with cache", func(t *testing.T) {
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
				_, err := BuildGetAndPersistPlayerWithCache(cache, provider, playerrepository.NewStubPlayerRepository())(context.Background(), uuid)
				require.Error(t, err)
			})
		}
	})
}
