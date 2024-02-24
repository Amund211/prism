package getstats

import (
	"fmt"
	"log"

	"github.com/Amund211/flashlight/internal/cache"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/hypixel"
	"github.com/Amund211/flashlight/internal/parsing"
)

func getMinifiedPlayerData(hypixelAPI hypixel.HypixelAPI, uuid string) ([]byte, int, error) {
	playerData, statusCode, err := hypixelAPI.GetPlayerData(uuid)
	if err != nil {
		return []byte{}, -1, err
	}

	if len(playerData) > 0 && playerData[0] == '<' {
		log.Println("Hypixel returned HTML")
		return []byte{}, -1, fmt.Errorf("%w: Hypixel returned HTML", e.APIServerError)
	}

	minifiedPlayerData, err := parsing.MinifyPlayerData(playerData)
	if err != nil {
		return []byte{}, -1, fmt.Errorf("%w: %w", e.APIServerError, err)
	}

	return minifiedPlayerData, statusCode, nil
}

func GetOrCreateMinifiedPlayerData(playerCache cache.PlayerCache, hypixelAPI hypixel.HypixelAPI, uuid string) ([]byte, int, error) {
	uuidLength := len(uuid)
	if uuidLength < 10 || uuidLength > 100 {
		return []byte{}, -1, fmt.Errorf("%w: Invalid uuid (length=%d)", e.APIClientError, uuidLength)
	}

	minifiedPlayerData, statusCode, err := cache.GetOrCreateCachedResponse(playerCache, uuid, func() ([]byte, int, error) {
		return getMinifiedPlayerData(hypixelAPI, uuid)
	})

	if err != nil {
		return []byte{}, -1, err
	}

	return minifiedPlayerData, statusCode, nil
}
