package getstats

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/Amund211/flashlight/internal/cache"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/parsing"
	"github.com/stretchr/testify/assert"
)

const uuid = "uuid-has-to-be-a-certain-length"

type panicHypixelAPI struct{}

func (p *panicHypixelAPI) GetPlayerData(uuid string) ([]byte, int, error) {
	panic("Should not be called")
}

type mockedHypixelAPI struct {
	data       []byte
	statusCode int
	err        error
}

func (m *mockedHypixelAPI) GetPlayerData(uuid string) ([]byte, int, error) {
	return m.data, m.statusCode, m.err
}

func TestGetOrCreateMinifiedPlayerData(t *testing.T) {
	t.Run("Test GetStats", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`{"success":true,"player":{"stats":{"Bedwars":{"Experience":0}}}}`),
			statusCode: 200,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		data, statusCode, err := GetOrCreateMinifiedPlayerData(context.Background(), cache, hypixelAPI, uuid)
		assert.Nil(t, err)

		var playerData parsing.HypixelAPIResponse

		err = json.Unmarshal(data, &playerData)

		assert.Nil(t, err, "Can't unmarshal minified playerdata '%s'", data)
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

		GetOrCreateMinifiedPlayerData(context.Background(), cache, hypixelAPI, uuid)

		GetOrCreateMinifiedPlayerData(context.Background(), cache, panicHypixelAPI, uuid)
	})

	t.Run("error from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(``),
			statusCode: -1,
			err:        assert.AnError,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateMinifiedPlayerData(context.Background(), cache, hypixelAPI, uuid)

		assert.ErrorIs(t, err, assert.AnError)
	})

	t.Run("html from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`<!DOCTYPE html>`),
			statusCode: 504,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateMinifiedPlayerData(context.Background(), cache, hypixelAPI, uuid)

		assert.ErrorIs(t, err, e.APIServerError)
	})

	t.Run("invalid JSON from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`something went wrong`),
			statusCode: 504,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateMinifiedPlayerData(context.Background(), cache, hypixelAPI, uuid)

		assert.ErrorIs(t, err, e.APIServerError)
	})

	t.Run("weird data format from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`{"success":true,"player":{"stats":{"Bedwars":{"final_kills_bedwars":"string"}}}}`),
			statusCode: 200,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateMinifiedPlayerData(context.Background(), cache, hypixelAPI, uuid)

		assert.ErrorIs(t, err, e.APIServerError)
	})

	t.Run("invalid uuid", func(t *testing.T) {
		hypixelAPI := &panicHypixelAPI{}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateMinifiedPlayerData(context.Background(), cache, hypixelAPI, "invalid")

		assert.ErrorIs(t, err, e.APIClientError)
	})

	t.Run("missing uuid", func(t *testing.T) {
		hypixelAPI := &panicHypixelAPI{}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateMinifiedPlayerData(context.Background(), cache, hypixelAPI, "")

		assert.ErrorIs(t, err, e.APIClientError)
	})

	t.Run("403 from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`{"success":false,"cause":"Invalid API key"}`),
			statusCode: 403,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateMinifiedPlayerData(context.Background(), cache, hypixelAPI, uuid)

		assert.ErrorIs(t, err, e.APIServerError)
	})
}
