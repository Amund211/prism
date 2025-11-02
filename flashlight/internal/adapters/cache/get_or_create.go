package cache

import (
	"context"
	"fmt"

	"github.com/Amund211/flashlight/internal/logging"
)

// Returns data, created, error
func GetOrCreate[T any](ctx context.Context, cache Cache[T], key string, create func() (T, error)) (T, bool, error) {
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

			logging.FromContext(ctx).InfoContext(ctx, "Getting player stats", "cache", "miss")

			data, err := create()
			if err != nil {
				var empty T
				return empty, false, fmt.Errorf("failed to create cache entry: %w", err)
			}

			cache.set(key, data)
			set = true

			return data, true, nil
		}

		if result.valid {
			// Cache hit
			logging.FromContext(ctx).InfoContext(ctx, "Getting player stats", "cache", "hit")
			return result.data, false, nil
		}

		logging.FromContext(ctx).InfoContext(ctx, "Waiting for cache")
		cache.wait()
	}
}
