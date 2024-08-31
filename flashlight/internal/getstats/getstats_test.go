package getstats

import (
	"context"
	"testing"

	"github.com/Amund211/flashlight/internal/cache"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/processing"
	"github.com/stretchr/testify/assert"
)

const uuid = "uuid-has-to-be-a-certain-length"

type panicHypixelAPI struct{}

func (p *panicHypixelAPI) GetPlayerData(ctx context.Context, uuid string) ([]byte, int, error) {
	panic("Should not be called")
}

type mockedHypixelAPI struct {
	data       []byte
	statusCode int
	err        error
}

func (m *mockedHypixelAPI) GetPlayerData(ctx context.Context, uuid string) ([]byte, int, error) {
	return m.data, m.statusCode, m.err
}

func TestGetOrCreateProcessedPlayerData(t *testing.T) {
	t.Run("Test GetStats", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`{"success":true,"player":{"stats":{"Bedwars":{"Experience":0}}}}`),
			statusCode: 200,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		data, statusCode, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, uuid)
		assert.Nil(t, err)

		playerData, err := processing.ParsePlayerData(context.Background(), data)

		assert.Nil(t, err, "Can't parse processed playerdata '%s'", data)
		assert.Equal(t, 200, statusCode)
		assert.Nil(t, playerData.Cause)
		assert.True(t, playerData.Success)
		assert.Equal(t, 0.0, *playerData.Player.Stats.Bedwars.Experience)
		assert.Nil(t, playerData.Player.Stats.Bedwars.FinalKills)
	})

	t.Run("stats are not created if they already exist", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`{}`),
			statusCode: 200,
			err:        nil,
		}
		panicHypixelAPI := &panicHypixelAPI{}
		cache := cache.NewMockedPlayerCache()

		GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, uuid)

		GetOrCreateProcessedPlayerData(context.Background(), cache, panicHypixelAPI, uuid)
	})

	t.Run("error from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(``),
			statusCode: -1,
			err:        assert.AnError,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, uuid)

		assert.ErrorIs(t, err, assert.AnError)

		// Errors from the Hypixel API are passed through
		assert.NotErrorIs(t, err, e.APIServerError)
		assert.NotErrorIs(t, err, e.RetriableError)
	})

	t.Run("html from hypixel", func(t *testing.T) {
		// This can happen with gateway errors, giving us cloudflare html
		// We now pass through gateway errors, so I've altered this test to return 200
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`<!DOCTYPE html>`),
			statusCode: 200,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, uuid)

		assert.ErrorIs(t, err, e.APIServerError)
		assert.ErrorIs(t, err, e.RetriableError)
	})

	t.Run("invalid JSON from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`something went wrong`),
			statusCode: 200,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, uuid)

		assert.ErrorIs(t, err, e.APIServerError)
		assert.NotErrorIs(t, err, e.RetriableError)
	})

	t.Run("weird data format from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`{"success":true,"player":{"stats":{"Bedwars":{"final_kills_bedwars":"string"}}}}`),
			statusCode: 200,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, uuid)

		assert.ErrorIs(t, err, e.APIServerError)
		assert.NotErrorIs(t, err, e.RetriableError)
	})

	t.Run("invalid uuid", func(t *testing.T) {
		hypixelAPI := &panicHypixelAPI{}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, "invalid")

		assert.ErrorIs(t, err, e.APIClientError)
		assert.NotErrorIs(t, err, e.RetriableError)
	})

	t.Run("missing uuid", func(t *testing.T) {
		hypixelAPI := &panicHypixelAPI{}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, "")

		assert.ErrorIs(t, err, e.APIClientError)
		assert.NotErrorIs(t, err, e.RetriableError)
	})

	t.Run("403 from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`{"success":false,"cause":"Invalid API key"}`),
			statusCode: 403,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, uuid)

		assert.ErrorIs(t, err, e.APIServerError)
		assert.NotErrorIs(t, err, e.RetriableError)
	})

	t.Run("bad gateway from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`<!DOCTYPE html>`),
			statusCode: 502,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, uuid)

		assert.ErrorIs(t, err, e.APIServerError)
		assert.ErrorIs(t, err, e.RetriableError)
	})

	t.Run("service unavailable from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`<!DOCTYPE html>`),
			statusCode: 503,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, uuid)

		assert.ErrorIs(t, err, e.APIServerError)
		assert.ErrorIs(t, err, e.RetriableError)
	})

	t.Run("gateway timeout from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`<!DOCTYPE html>`),
			statusCode: 504,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, uuid)

		assert.ErrorIs(t, err, e.APIServerError)
		assert.ErrorIs(t, err, e.RetriableError)
	})
}
