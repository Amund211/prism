package cache

import (
	"context"

	"github.com/Amund211/flashlight/internal/logging"
)

func GetOrCreateCachedResponse(ctx context.Context, playerCache PlayerCache, uuid string, create func() ([]byte, int, error)) ([]byte, int, error) {
	logger := logging.FromContext(ctx)

	// Clean up the cache if we claim an entry, but don't set it
	// This allows other requests to try again
	claimed := false
	set := false
	defer func() {
		if claimed && !set {
			playerCache.delete(uuid)
		}
	}()

	for {
		result := playerCache.getOrClaim(uuid)

		if result.claimed {
			claimed = true

			logger.Info("Getting player stats", "cache", "miss")

			data, statusCode, err := create()
			if err != nil {
				return []byte{}, -1, err
			}

			playerCache.set(uuid, playerResponse{
				data:       data,
				statusCode: statusCode,
			})
			set = true

			return data, statusCode, nil
		}

		if result.valid {
			// Cache hit
			logger.Info("Getting player stats", "cache", "hit")
			return result.data.data, result.data.statusCode, nil
		}

		logger.Info("Waiting for cache")
		playerCache.wait()
	}
}
