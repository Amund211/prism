package cache

import (
	"context"
	"log"

	"github.com/Amund211/flashlight/internal/logging"
)

func GetOrCreateCachedResponse(ctx context.Context, playerCache PlayerCache, uuid string, create func() ([]byte, int, error)) ([]byte, int, error) {
	logger := logging.FromContext(ctx)
	var invalid = cachedResponse{valid: false}

	// Clean up the cache if we store an invalid entry
	// This allows other requests to try again
	var storedInvalidCacheEntry = false
	defer func() {
		if storedInvalidCacheEntry {
			playerCache.delete(uuid)
		}
	}()

	for {
		value, existed := playerCache.getOrSet(uuid, invalid)

		if !existed {
			log.Println("Got cache miss")
			logger.Info("Getting player stats", "cache", "miss")
			storedInvalidCacheEntry = true

			data, statusCode, err := create()
			if err != nil {
				return []byte{}, -1, err
			}

			playerCache.set(uuid, data, statusCode)
			storedInvalidCacheEntry = false

			return data, statusCode, nil
		}

		if value.valid {
			// Cache hit
			log.Println("Got cache hit")
			logger.Info("Getting player stats", "cache", "hit")
			return value.data, value.statusCode, nil
		}

		logger.Info("Waiting for cache")
		playerCache.wait()
	}
}
