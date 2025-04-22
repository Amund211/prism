package getstats

import (
	"context"
	"testing"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/adapters/playerrepository"
	"github.com/Amund211/flashlight/internal/domain"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/stretchr/testify/require"
)

const UUID = "01234567-89AB---CDEF-0123-456789abcdef"
const NORMALIZED_UUID = "01234567-89ab-cdef-0123-456789abcdef"

type panicPlayerProvider struct {
	t *testing.T
}

func (p *panicPlayerProvider) GetPlayer(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
	p.t.Helper()
	p.t.Fatal("should not be called")
	panic("unreachable")
}

type mockedPlayerProvider struct {
	t      *testing.T
	player *domain.PlayerPIT
	err    error
}

func (m *mockedPlayerProvider) GetPlayer(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
	m.t.Helper()

	require.Equal(m.t, NORMALIZED_UUID, uuid)

	return m.player, m.err
}

func TestGetOrCreateProcessedPlayerData(t *testing.T) {
	t.Run("stats are not created if they already exist", func(t *testing.T) {
		provider := &mockedPlayerProvider{
			t:      t,
			player: &domain.PlayerPIT{UUID: UUID, Experience: 500, Overall: domain.GamemodeStatsPIT{FinalKills: 0}},
			err:    nil,
		}
		panicProvider := &panicPlayerProvider{t: t}
		cache := cache.NewBasicCache[*domain.PlayerPIT]()

		_, err := GetOrCreateProcessedPlayerData(context.Background(), cache, provider, playerrepository.NewStubPlayerRepository(), UUID)
		require.NoError(t, err)

		_, err = GetOrCreateProcessedPlayerData(context.Background(), cache, panicProvider, playerrepository.NewStubPlayerRepository(), UUID)
		require.NoError(t, err)
	})

	t.Run("cache keys are normalized", func(t *testing.T) {
		// Requesting abcdef12-... and then ABCDEF12-... should only go to Hypixel once
		provider := &mockedPlayerProvider{
			t:      t,
			player: &domain.PlayerPIT{UUID: UUID, Experience: 500, Overall: domain.GamemodeStatsPIT{FinalKills: 0}},
			err:    nil,
		}
		panicProvider := &panicPlayerProvider{t: t}
		cache := cache.NewBasicCache[*domain.PlayerPIT]()

		_, err := GetOrCreateProcessedPlayerData(context.Background(), cache, provider, playerrepository.NewStubPlayerRepository(), "01234567-89ab-cdef-0123-456789abcdef")
		require.NoError(t, err)

		_, err = GetOrCreateProcessedPlayerData(context.Background(), cache, panicProvider, playerrepository.NewStubPlayerRepository(), "01---23456789aBCDef0123456789aBcdef")
		require.NoError(t, err)
	})

	t.Run("invalid uuid", func(t *testing.T) {
		provider := &panicPlayerProvider{t: t}
		cache := cache.NewBasicCache[*domain.PlayerPIT]()

		_, err := GetOrCreateProcessedPlayerData(context.Background(), cache, provider, playerrepository.NewStubPlayerRepository(), "invalid")

		require.ErrorIs(t, err, e.APIClientError)
		require.NotErrorIs(t, err, e.RetriableError)

		_, err = GetOrCreateProcessedPlayerData(context.Background(), cache, provider, playerrepository.NewStubPlayerRepository(), "01234567-89ab-xxxx-0123-456789abcdef")

		require.ErrorIs(t, err, e.APIClientError)
		require.NotErrorIs(t, err, e.RetriableError)
	})

	t.Run("missing uuid", func(t *testing.T) {
		provider := &panicPlayerProvider{t: t}
		cache := cache.NewBasicCache[*domain.PlayerPIT]()

		_, err := GetOrCreateProcessedPlayerData(context.Background(), cache, provider, playerrepository.NewStubPlayerRepository(), "")

		require.ErrorIs(t, err, e.APIClientError)
		require.NotErrorIs(t, err, e.RetriableError)
	})
}
