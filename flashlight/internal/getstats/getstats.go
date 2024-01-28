package getstats

import (
    "fmt"
    "log"

    "github.com/Amund211/flashlight/internal/cache"
    "github.com/Amund211/flashlight/internal/hypixel"
    "github.com/Amund211/flashlight/internal/parsing"
    e "github.com/Amund211/flashlight/internal/errors"
)

func GetMinifiedPlayerData(playerCache cache.PlayerCache, hypixelAPI hypixel.HypixelAPI, uuid string) ([]byte, int, error) {
	uuidLength := len(uuid)
	if uuidLength < 10 || uuidLength > 100 {
		return []byte{}, -1, fmt.Errorf("%w: Invalid uuid (length=%d)", e.APIClientError, uuidLength)
	}

	cachedResponse := cache.GetOrCreateCachedResponse(playerCache, uuid)
	if cachedResponse.Valid {
		return cachedResponse.Data, cachedResponse.StatusCode, nil
	}

	// GetOrCreateCachedResponse inserts an invalid cache entry if it doesn't exist
	// If we fail to store a valid cache entry, we must delete the invalid one so another request can try again
	var storedInvalidCacheEntry = true
	defer func() {
		if storedInvalidCacheEntry {
			playerCache.Delete(uuid)
		}
	}()

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

	playerCache.Set(uuid, minifiedPlayerData, statusCode, true)
	storedInvalidCacheEntry = false

	return minifiedPlayerData, statusCode, nil
}

