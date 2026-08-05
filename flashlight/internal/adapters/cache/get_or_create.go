package cache

import (
	"context"
	"errors"
	"fmt"

	"github.com/Amund211/flashlight/internal/logging"
)

// maxWaitAttempts bounds the wait for whoever holds the claim. Without it a
// waiter can starve indefinitely: later callers race for the claim on equal
// terms. Counted in attempts because the length of a wait is the cache
// implementation's; at the 50ms of defaultWaitInterval this is ~30s, i.e. the
// server's WriteTimeout, past which nobody is left to answer.
const maxWaitAttempts = 600

var ErrGaveUpWaiting = errors.New("gave up waiting for another caller to create the cache entry")

// Returns data, created, error. The error is create()'s, or — for a caller
// that did not get the claim — ctx.Err(), or ErrGaveUpWaiting.
func GetOrCreate[T any](ctx context.Context, cache Cache[T], key string, create func() (T, error)) (T, bool, error) {
	var empty T

	// Clean up the cache if we claim an entry, but don't set it
	// This allows other callers to try again
	claimed := false
	set := false
	defer func() {
		if claimed && !set {
			cache.delete(key)
		}
	}()

	for attempt := 0; ; attempt++ {
		// Nobody reads what we produce once the client has hung up or the
		// deadline has passed.
		if err := ctx.Err(); err != nil {
			return empty, false, fmt.Errorf("context done while waiting for cache entry: %w", err)
		}

		if attempt >= maxWaitAttempts {
			logging.FromContext(ctx).WarnContext(ctx, "Gave up waiting for cache entry", "attempts", attempt)
			return empty, false, fmt.Errorf("%w: %d attempts", ErrGaveUpWaiting, attempt)
		}

		result := cache.getOrClaim(key)

		if result.claimed {
			claimed = true

			logging.FromContext(ctx).InfoContext(ctx, "Cache lookup", "cache", "miss")

			data, err := create()
			if err != nil {
				return empty, false, fmt.Errorf("failed to create cache entry: %w", err)
			}

			cache.set(key, data)
			set = true

			return data, true, nil
		}

		if result.valid {
			// Cache hit
			logging.FromContext(ctx).InfoContext(ctx, "Cache lookup", "cache", "hit")
			return result.data, false, nil
		}

		logging.FromContext(ctx).InfoContext(ctx, "Waiting for cache")
		cache.wait(ctx)
	}
}
