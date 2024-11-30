package getstats

import (
	"context"
	"testing"

	"github.com/Amund211/flashlight/internal/cache"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/processing"
	"github.com/Amund211/flashlight/internal/storage"
	"github.com/stretchr/testify/assert"
)

const UUID = "01234567-89AB---CDEF-0123-456789abcdef"
const NORMALIZED_UUID = "01234567-89ab-cdef-0123-456789abcdef"

type panicHypixelAPI struct {
	t *testing.T
}

func (p *panicHypixelAPI) GetPlayerData(ctx context.Context, uuid string) ([]byte, int, error) {
	p.t.Helper()
	p.t.Fatal("should not be called")
	panic("unreachable")
}

type mockedHypixelAPI struct {
	t          *testing.T
	data       []byte
	statusCode int
	err        error
}

func (m *mockedHypixelAPI) GetPlayerData(ctx context.Context, uuid string) ([]byte, int, error) {
	m.t.Helper()

	assert.Equal(m.t, NORMALIZED_UUID, uuid)

	return m.data, m.statusCode, m.err
}

func TestGetOrCreateProcessedPlayerData(t *testing.T) {
	t.Run("Test GetStats", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			t:          t,
			data:       []byte(`{"success":true,"player":{"stats":{"Bedwars":{"Experience":0}}}}`),
			statusCode: 200,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		data, statusCode, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, storage.NewStubPersistor(), UUID)
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
			t:          t,
			data:       []byte(`{}`),
			statusCode: 200,
			err:        nil,
		}
		panicHypixelAPI := &panicHypixelAPI{t: t}
		cache := cache.NewMockedPlayerCache()

		GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, storage.NewStubPersistor(), UUID)

		GetOrCreateProcessedPlayerData(context.Background(), cache, panicHypixelAPI, storage.NewStubPersistor(), UUID)
	})

	t.Run("cache keys are normalized", func(t *testing.T) {
		// Requesting abcdef12-... and then ABCDEF12-... should only go to Hypixel once
		hypixelAPI := &mockedHypixelAPI{
			t:          t,
			data:       []byte(`{}`),
			statusCode: 200,
			err:        nil,
		}
		panicHypixelAPI := &panicHypixelAPI{t: t}
		cache := cache.NewMockedPlayerCache()

		GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, storage.NewStubPersistor(), "01234567-89ab-cdef-0123-456789abcdef")

		GetOrCreateProcessedPlayerData(context.Background(), cache, panicHypixelAPI, storage.NewStubPersistor(), "01---23456789aBCDef0123456789aBcdef")
	})

	t.Run("error from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			t:          t,
			data:       []byte(``),
			statusCode: -1,
			err:        assert.AnError,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, storage.NewStubPersistor(), UUID)

		assert.ErrorIs(t, err, assert.AnError)

		// Errors from the Hypixel API are passed through
		assert.NotErrorIs(t, err, e.APIServerError)
		assert.NotErrorIs(t, err, e.RetriableError)
	})

	t.Run("html from hypixel", func(t *testing.T) {
		// This can happen with gateway errors, giving us cloudflare html
		// We now pass through gateway errors, so I've altered this test to return 200
		hypixelAPI := &mockedHypixelAPI{
			t:          t,
			data:       []byte(`<!DOCTYPE html>`),
			statusCode: 200,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, storage.NewStubPersistor(), UUID)

		assert.ErrorIs(t, err, e.APIServerError)
		assert.ErrorIs(t, err, e.RetriableError)
	})

	t.Run("invalid JSON from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			t:          t,
			data:       []byte(`something went wrong`),
			statusCode: 200,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, storage.NewStubPersistor(), UUID)

		assert.ErrorIs(t, err, e.APIServerError)
		assert.NotErrorIs(t, err, e.RetriableError)
	})

	t.Run("weird data format from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			t:          t,
			data:       []byte(`{"success":true,"player":{"stats":{"Bedwars":{"final_kills_bedwars":"string"}}}}`),
			statusCode: 200,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, storage.NewStubPersistor(), UUID)

		assert.ErrorIs(t, err, e.APIServerError)
		assert.NotErrorIs(t, err, e.RetriableError)
	})

	t.Run("invalid uuid", func(t *testing.T) {
		hypixelAPI := &panicHypixelAPI{t: t}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, storage.NewStubPersistor(), "invalid")

		assert.ErrorIs(t, err, e.APIClientError)
		assert.NotErrorIs(t, err, e.RetriableError)

		_, _, err = GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, storage.NewStubPersistor(), "01234567-89ab-xxxx-0123-456789abcdef")

		assert.ErrorIs(t, err, e.APIClientError)
		assert.NotErrorIs(t, err, e.RetriableError)
	})

	t.Run("missing uuid", func(t *testing.T) {
		hypixelAPI := &panicHypixelAPI{t: t}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, storage.NewStubPersistor(), "")

		assert.ErrorIs(t, err, e.APIClientError)
		assert.NotErrorIs(t, err, e.RetriableError)
	})

	t.Run("403 from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			t:          t,
			data:       []byte(`{"success":false,"cause":"Invalid API key"}`),
			statusCode: 403,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, storage.NewStubPersistor(), UUID)

		assert.ErrorIs(t, err, e.APIServerError)
		assert.NotErrorIs(t, err, e.RetriableError)
	})

	t.Run("bad gateway from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			t:          t,
			data:       []byte(`<!DOCTYPE html>`),
			statusCode: 502,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, storage.NewStubPersistor(), UUID)

		assert.ErrorIs(t, err, e.APIServerError)
		assert.ErrorIs(t, err, e.RetriableError)
	})

	t.Run("service unavailable from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			t:          t,
			data:       []byte(`<!DOCTYPE html>`),
			statusCode: 503,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, storage.NewStubPersistor(), UUID)

		assert.ErrorIs(t, err, e.APIServerError)
		assert.ErrorIs(t, err, e.RetriableError)
	})

	t.Run("gateway timeout from hypixel", func(t *testing.T) {
		hypixelAPI := &mockedHypixelAPI{
			t:          t,
			data:       []byte(`<!DOCTYPE html>`),
			statusCode: 504,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateProcessedPlayerData(context.Background(), cache, hypixelAPI, storage.NewStubPersistor(), UUID)

		assert.ErrorIs(t, err, e.APIServerError)
		assert.ErrorIs(t, err, e.RetriableError)
	})
}
