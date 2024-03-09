package getstats

import (
	"encoding/json"
	"errors"
	"testing"

	"github.com/Amund211/flashlight/internal/cache"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/parsing"
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
		t.Parallel()
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`{"success":true,"player":{"stats":{"Bedwars":{"Experience":0}}}}`),
			statusCode: 200,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		data, statusCode, err := GetOrCreateMinifiedPlayerData(cache, hypixelAPI, uuid)
		if err != nil {
			t.Errorf("Error: %v", err)
		}

		var playerData parsing.HypixelAPIResponse

		err = json.Unmarshal(data, &playerData)

		if err != nil {
			t.Errorf("Can't unmarshal minified playerdata: %v", err)
		}

		if statusCode != 200 {
			t.Errorf("Expected 200, got %v", statusCode)
		}

		if playerData.Cause != nil {
			t.Errorf("Expected nil, got %v", playerData.Cause)
		}

		if playerData.Success != true {
			t.Errorf("Expected true, got %v", playerData.Success)
		}

		experience := *playerData.Player.Stats.Bedwars.Experience
		if experience != 0 {
			t.Errorf("Expected 0, got %v", experience)
		}

		finals := playerData.Player.Stats.Bedwars.FinalKills
		if finals != nil {
			t.Errorf("Expected nil, got %v", finals)
		}
	})

	t.Run("stats are not created if they already exist", func(t *testing.T) {
		t.Parallel()
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`{}`),
			statusCode: 200,
			err:        nil,
		}
		panicHypixelAPI := &panicHypixelAPI{}
		cache := cache.NewMockedPlayerCache()

		GetOrCreateMinifiedPlayerData(cache, hypixelAPI, uuid)

		GetOrCreateMinifiedPlayerData(cache, panicHypixelAPI, uuid)
	})

	t.Run("error from hypixel", func(t *testing.T) {
		t.Parallel()
		error := errors.New("error")
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(``),
			statusCode: -1,
			err:        error,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateMinifiedPlayerData(cache, hypixelAPI, uuid)

		if !errors.Is(err, error) {
			t.Errorf("Expected error, got %v", err)
		}
	})

	t.Run("html from hypixel", func(t *testing.T) {
		t.Parallel()
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`<!DOCTYPE html>`),
			statusCode: 504,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateMinifiedPlayerData(cache, hypixelAPI, uuid)

		if !errors.Is(err, e.APIServerError) {
			t.Errorf("Expected server error, got %v", err)
		}
	})

	t.Run("invalid JSON from hypixel", func(t *testing.T) {
		t.Parallel()
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`something went wrong`),
			statusCode: 504,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateMinifiedPlayerData(cache, hypixelAPI, uuid)

		if !errors.Is(err, e.APIServerError) {
			t.Errorf("Expected server error, got %v", err)
		}
	})

	t.Run("weird data format from hypixel", func(t *testing.T) {
		t.Parallel()
		hypixelAPI := &mockedHypixelAPI{
			data:       []byte(`{"success":true,"player":{"stats":{"Bedwars":{"final_kills_bedwars":"string"}}}}`),
			statusCode: 200,
			err:        nil,
		}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateMinifiedPlayerData(cache, hypixelAPI, uuid)

		if !errors.Is(err, e.APIServerError) {
			t.Errorf("Expected server error, got %v", err)
		}
	})

	t.Run("invalid uuid", func(t *testing.T) {
		t.Parallel()
		hypixelAPI := &panicHypixelAPI{}
		cache := cache.NewMockedPlayerCache()

		_, _, err := GetOrCreateMinifiedPlayerData(cache, hypixelAPI, "invalid")

		if !errors.Is(err, e.APIClientError) {
			t.Errorf("Expected server error, got %v", err)
		}
	})
}
