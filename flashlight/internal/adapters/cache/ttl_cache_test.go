package cache

import (
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestTTLCache(t *testing.T) {
	t.Run("Set and get", func(t *testing.T) {
		t.Parallel()

		cache := NewTTLCache[Data](1000 * time.Second)

		cache.set("key", "data")

		result := cache.getOrClaim("key")
		require.False(t, result.claimed, "Expected entry to exist")
		require.Equal(t, "data", string(result.data))
	})

	t.Run("getOrClaim claims when missing", func(t *testing.T) {
		t.Parallel()

		cache := NewTTLCache[Data](1000 * time.Second)

		result := cache.getOrClaim("key")
		require.True(t, result.claimed, "Expected entry to not exist and get claimed")

		result = cache.getOrClaim("key")
		require.False(t, result.claimed, "Expected entry to exist and not get claimed")
		require.False(t, result.valid, "Expected entry to be invalid")
	})

	t.Run("delete", func(t *testing.T) {
		t.Parallel()

		cache := NewTTLCache[Data](1000 * time.Second)
		cache.set("key", "data")

		cache.delete("key")

		result := cache.getOrClaim("key")
		require.True(t, result.claimed, "Expected to not find a value")
	})

	t.Run("delete missing entry", func(t *testing.T) {
		t.Parallel()

		cache := NewTTLCache[Data](1000 * time.Second)

		cache.delete("key")

		result := cache.getOrClaim("key")
		require.True(t, result.claimed, "Expected to not find a value")
	})

	t.Run("wait", func(t *testing.T) {
		t.Parallel()

		cache := NewTTLCache[Data](1000 * time.Second)
		cache.wait()
	})
}
