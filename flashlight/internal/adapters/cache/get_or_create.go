package cache

import (
	"context"

	"github.com/Amund211/flashlight/internal/logging"
)

func GetOrCreate[T any](ctx context.Context, cache Cache[T], key string, create func() (T, error)) (T, error) {
	logger := logging.FromContext(ctx)

	// Clean up the cache if we claim an entry, but don't set it
	// This allows other callers to try again
	claimed := false
	set := false
	defer func() {
		if claimed && !set {
			cache.delete(key)
		}
	}()

	for {
		result := cache.getOrClaim(key)

		if result.claimed {
			claimed = true

			logger.Info("Getting player stats", "cache", "miss")

			data, err := create()
			if err != nil {
				var empty T
				return empty, err
			}

			cache.set(key, data)
			set = true

			return data, nil
		}

		if result.valid {
			// Cache hit
			logger.Info("Getting player stats", "cache", "hit")
			return result.data, nil
		}

		logger.Info("Waiting for cache")
		cache.wait()
	}
}
