package playerprovider_test

import (
	"context"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/playerprovider"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

const UUID = "01234567-89ab-cdef-0123-456789abcdef"

type mockedHypixelAPI struct {
	t          *testing.T
	data       []byte
	statusCode int
	queriedAt  time.Time
	err        error
}

func (m *mockedHypixelAPI) GetPlayerData(ctx context.Context, uuid string) ([]byte, int, time.Time, error) {
	m.t.Helper()

	require.Equal(m.t, UUID, uuid)

	return m.data, m.statusCode, m.queriedAt, m.err
}

func TestHypixelPlayerProvider(t *testing.T) {
	now := time.Now()

	t.Run("GetPlayer", func(t *testing.T) {
		t.Run("basic", func(t *testing.T) {
			hypixelAPI := &mockedHypixelAPI{
				t:          t,
				data:       []byte(`{"success":true,"player":{"uuid":"0123456789abcdef0123456789abcdef","stats":{"Bedwars":{"Experience":0}}}}`),
				statusCode: 200,
				queriedAt:  now,
				err:        nil,
			}
			provider := playerprovider.NewHypixelPlayerProvider(hypixelAPI)
			player, err := provider.GetPlayer(context.Background(), UUID)
			require.NoError(t, err)

			require.NotNil(t, player)
			require.Equal(t, UUID, player.UUID)
			require.Equal(t, 0.0, player.Experience) // Weird case - don't expect hypixel api to return `"Experience": 0`
			require.Equal(t, 0, player.Overall.FinalKills)
		})

		t.Run("input uuid is normalized", func(t *testing.T) {
			hypixelAPI := &mockedHypixelAPI{
				t:          t,
				data:       []byte(`{"success":true,"player":{"uuid":"0123456789abcdef0123456789abcdef"}}`),
				statusCode: 200,
				queriedAt:  now,
				err:        nil,
			}

			provider := playerprovider.NewHypixelPlayerProvider(hypixelAPI)
			player, err := provider.GetPlayer(context.Background(), "0123456789abcdef0123456789abcdef")
			require.NoError(t, err)

			require.NotNil(t, player)
			require.Equal(t, UUID, player.UUID)
		})

		t.Run("error from hypixel", func(t *testing.T) {
			hypixelAPI := &mockedHypixelAPI{
				t:          t,
				data:       []byte(``),
				statusCode: -1,
				queriedAt:  time.Time{},
				err:        assert.AnError,
			}
			provider := playerprovider.NewHypixelPlayerProvider(hypixelAPI)
			player, err := provider.GetPlayer(context.Background(), UUID)
			require.Error(t, err)
			require.Nil(t, player)

			require.ErrorIs(t, err, assert.AnError)
		})

		t.Run("html from hypixel", func(t *testing.T) {
			// This can happen with gateway errors, giving us cloudflare html
			// We now pass through gateway errors, so I've altered this test to return 200
			hypixelAPI := &mockedHypixelAPI{
				t:          t,
				data:       []byte(`<!DOCTYPE html>`),
				statusCode: 200,
				queriedAt:  time.Time{},
				err:        nil,
			}
			provider := playerprovider.NewHypixelPlayerProvider(hypixelAPI)
			player, err := provider.GetPlayer(context.Background(), UUID)
			require.Error(t, err)
			require.Nil(t, player)

			// TODO: Use errors specific to the provider
			require.ErrorIs(t, err, e.APIServerError)
			require.ErrorIs(t, err, e.RetriableError)
		})

		t.Run("invalid JSON from hypixel", func(t *testing.T) {
			hypixelAPI := &mockedHypixelAPI{
				t:          t,
				data:       []byte(`something went wrong`),
				statusCode: 200,
				queriedAt:  time.Time{},
				err:        nil,
			}
			provider := playerprovider.NewHypixelPlayerProvider(hypixelAPI)
			player, err := provider.GetPlayer(context.Background(), UUID)
			require.Error(t, err)
			require.Nil(t, player)

			require.ErrorIs(t, err, e.APIServerError)
			require.NotErrorIs(t, err, e.RetriableError)
		})

		t.Run("weird data format from hypixel", func(t *testing.T) {
			hypixelAPI := &mockedHypixelAPI{
				t:          t,
				data:       []byte(`{"success":true,"player":{"uuid":"0123456789abcdef0123456789abcdef","stats":{"Bedwars":{"final_kills_bedwars":"string"}}}}`),
				statusCode: 200,
				queriedAt:  now,
				err:        nil,
			}
			provider := playerprovider.NewHypixelPlayerProvider(hypixelAPI)
			player, err := provider.GetPlayer(context.Background(), UUID)
			require.Error(t, err)
			require.Nil(t, player)

			require.ErrorIs(t, err, e.APIServerError)
			require.NotErrorIs(t, err, e.RetriableError)
		})

		t.Run("403 from hypixel", func(t *testing.T) {
			hypixelAPI := &mockedHypixelAPI{
				t:          t,
				data:       []byte(`{"success":false,"cause":"Invalid API key"}`),
				statusCode: 403,
				queriedAt:  now,
				err:        nil,
			}
			provider := playerprovider.NewHypixelPlayerProvider(hypixelAPI)
			player, err := provider.GetPlayer(context.Background(), UUID)
			require.Error(t, err)
			require.Nil(t, player)

			require.ErrorIs(t, err, e.APIServerError)
			require.NotErrorIs(t, err, e.RetriableError)
		})

		t.Run("bad gateway from hypixel", func(t *testing.T) {
			hypixelAPI := &mockedHypixelAPI{
				t:          t,
				data:       []byte(`<!DOCTYPE html>`),
				statusCode: 502,
				queriedAt:  now,
				err:        nil,
			}
			provider := playerprovider.NewHypixelPlayerProvider(hypixelAPI)
			player, err := provider.GetPlayer(context.Background(), UUID)
			require.Error(t, err)
			require.Nil(t, player)

			require.ErrorIs(t, err, e.APIServerError)
			require.ErrorIs(t, err, e.RetriableError)
		})

		t.Run("service unavailable from hypixel", func(t *testing.T) {
			hypixelAPI := &mockedHypixelAPI{
				t:          t,
				data:       []byte(`<!DOCTYPE html>`),
				statusCode: 503,
				queriedAt:  now,
				err:        nil,
			}
			provider := playerprovider.NewHypixelPlayerProvider(hypixelAPI)
			player, err := provider.GetPlayer(context.Background(), UUID)
			require.Error(t, err)
			require.Nil(t, player)

			require.ErrorIs(t, err, e.APIServerError)
			require.ErrorIs(t, err, e.RetriableError)
		})

		t.Run("gateway timeout from hypixel", func(t *testing.T) {
			hypixelAPI := &mockedHypixelAPI{
				t:          t,
				data:       []byte(`<!DOCTYPE html>`),
				statusCode: 504,
				queriedAt:  now,
				err:        nil,
			}
			provider := playerprovider.NewHypixelPlayerProvider(hypixelAPI)
			player, err := provider.GetPlayer(context.Background(), UUID)
			require.Error(t, err)
			require.Nil(t, player)

			require.ErrorIs(t, err, e.APIServerError)
			require.ErrorIs(t, err, e.RetriableError)
		})
	})
}
